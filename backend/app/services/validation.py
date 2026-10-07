"""
Document validation service.
Checks for missing fields, VAT inconsistencies, low confidence,
duplicate detection, and other data-quality issues.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Optional
from sqlalchemy.orm import Session

from app.models.document import Document

logger = logging.getLogger(__name__)

# ── Warning codes & severities ──────────────────────────────────────

WARNING_SEVERITY_ERROR = "error"
WARNING_SEVERITY_WARNING = "warning"
WARNING_SEVERITY_INFO = "info"


def validate_document(doc: Document) -> list[dict]:
    """
    Return a list of validation warnings for a single document.

    Each warning: {"code": str, "message": str, "severity": str, "field": str|None}
    """
    warnings: list[dict] = []

    # Missing vendor
    if not doc.vendor_name:
        warnings.append({
            "code": "missing_vendor",
            "message": "Nome do fornecedor em falta",
            "severity": WARNING_SEVERITY_WARNING,
            "field": "vendor_name",
        })

    # Missing date
    if not doc.document_date:
        warnings.append({
            "code": "missing_date",
            "message": "Data do documento em falta",
            "severity": WARNING_SEVERITY_WARNING,
            "field": "document_date",
        })

    # Missing gross amount
    if not doc.gross_amount:
        warnings.append({
            "code": "missing_amount",
            "message": "Valor total em falta",
            "severity": WARNING_SEVERITY_ERROR,
            "field": "gross_amount",
        })

    # Missing VAT amount
    if doc.vat_amount is None:
        warnings.append({
            "code": "missing_vat",
            "message": "Valor do IVA em falta",
            "severity": WARNING_SEVERITY_WARNING,
            "field": "vat_amount",
        })

    # VAT inconsistency: vat_amount should ≈ gross - net (if both are present)
    if doc.gross_amount and doc.net_amount and doc.vat_amount is not None:
        expected_vat = doc.gross_amount - doc.net_amount
        tolerance = Decimal("0.05")  # 5 cents
        diff = abs(expected_vat - doc.vat_amount)
        if diff > tolerance:
            warnings.append({
                "code": "vat_inconsistency",
                "message": f"IVA ({doc.vat_amount}) não corresponde a Bruto-Líquido ({expected_vat})",
                "severity": WARNING_SEVERITY_WARNING,
                "field": "vat_amount",
            })

    # Low OCR confidence
    if doc.ocr_confidence is not None and doc.ocr_confidence < 65:
        warnings.append({
            "code": "low_confidence",
            "message": f"Confiança OCR baixa ({doc.ocr_confidence}%)",
            "severity": WARNING_SEVERITY_WARNING,
            "field": None,
        })

    # Uncategorized
    if not doc.expense_category or doc.expense_category == "other":
        warnings.append({
            "code": "uncategorized",
            "message": "Categoria de despesa não atribuída",
            "severity": WARNING_SEVERITY_INFO,
            "field": "expense_category",
        })

    return warnings


def _same_receipt(a: Document, b: Document, tolerance: Decimal) -> bool:
    """Same vendor NIF + invoice number, or same vendor + date + amount (within tolerance)."""
    if a.vendor_nif and a.invoice_number and a.vendor_nif == b.vendor_nif:
        return (b.invoice_number or "").strip().lower() == a.invoice_number.strip().lower()
    if not (a.vendor_name and b.vendor_name and a.document_date and a.gross_amount is not None):
        return False
    return (
        a.vendor_name.strip().lower() == b.vendor_name.strip().lower()
        and a.document_date == b.document_date
        and b.gross_amount is not None
        and abs(a.gross_amount - b.gross_amount) <= tolerance
    )


def detect_duplicates(
    db: Session,
    user_id: str,
    doc: Document,
    tolerance: Decimal = Decimal("0.50"),
) -> list[dict]:
    """
    Find possible duplicates of *doc* among the same user's documents.

    A match is the same vendor NIF + invoice number, or (when there is no
    invoice number) the same vendor name + date + gross amount within tolerance.
    """
    if not ((doc.vendor_nif and doc.invoice_number) or (doc.vendor_name and doc.document_date)):
        return []

    candidates = db.query(Document).filter(
        Document.user_id == user_id,
        Document.id != doc.id,
        Document.deleted_at.is_(None),
    )
    if doc.vendor_nif and doc.invoice_number:
        candidates = candidates.filter(Document.vendor_nif == doc.vendor_nif)
    else:
        candidates = candidates.filter(Document.document_date == doc.document_date)

    warnings: list[dict] = []
    for other in candidates.all():
        if not _same_receipt(doc, other, tolerance):
            continue
        when = other.document_date.strftime("%d/%m/%Y") if other.document_date else "sem data"
        warnings.append({
            "code": "possible_duplicate",
            "message": f"Possível duplicado de {other.vendor_name or other.original_filename} ({when})",
            "severity": WARNING_SEVERITY_WARNING,
            "field": None,
            "duplicate_id": other.id,
        })
    return warnings


def count_duplicates(documents: list[Document], tolerance: Decimal = Decimal("0.50")) -> int:
    """Number of documents in the list that repeat an earlier one."""
    repeats = 0
    for index, doc in enumerate(documents):
        if any(_same_receipt(doc, earlier, tolerance) for earlier in documents[:index]):
            repeats += 1
    return repeats


def validate_period_documents(
    db: Session,
    user_id: str,
    documents: list[Document],
) -> list[dict]:
    """
    Aggregate-level validation for a whole period (used by summary endpoint).
    Returns warnings that apply to the period as a whole.
    """
    warnings: list[dict] = []

    needs_review = [d for d in documents if d.status == "needs_review"]
    failed = [d for d in documents if d.status == "failed"]
    processing = [d for d in documents if d.status == "processing"]
    valid = [d for d in documents if d.status in ("ready", "needs_review", "accountant_review")]

    if needs_review:
        warnings.append({
            "code": "needs_review",
            "message": f"{len(needs_review)} documento(s) precisam de revisão",
            "severity": WARNING_SEVERITY_WARNING,
        })

    if failed:
        warnings.append({
            "code": "failed_processing",
            "message": f"{len(failed)} documento(s) falharam no processamento",
            "severity": WARNING_SEVERITY_ERROR,
        })

    if processing:
        warnings.append({
            "code": "still_processing",
            "message": f"{len(processing)} documento(s) ainda em processamento",
            "severity": WARNING_SEVERITY_INFO,
        })

    no_vat = [d for d in valid if d.vat_amount is None or d.vat_amount == 0]
    if no_vat:
        warnings.append({
            "code": "missing_vat_amounts",
            "message": f"{len(no_vat)} documento(s) sem valor de IVA",
            "severity": WARNING_SEVERITY_WARNING,
        })

    uncategorized = [d for d in valid if not d.expense_category or d.expense_category == "other"]
    if uncategorized:
        warnings.append({
            "code": "uncategorized_documents",
            "message": f"{len(uncategorized)} documento(s) sem categoria atribuída",
            "severity": WARNING_SEVERITY_INFO,
        })

    missing_date = [d for d in valid if not d.document_date]
    if missing_date:
        warnings.append({
            "code": "missing_dates",
            "message": f"{len(missing_date)} documento(s) sem data",
            "severity": WARNING_SEVERITY_WARNING,
        })

    duplicates = count_duplicates(valid)
    if duplicates:
        warnings.append({
            "code": "possible_duplicates",
            "message": f"{duplicates} possível(is) recibo(s) duplicado(s) — confirme antes de enviar",
            "severity": WARNING_SEVERITY_WARNING,
        })

    return warnings

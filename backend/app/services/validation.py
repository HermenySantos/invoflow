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


def detect_duplicates(
    db: Session,
    user_id: str,
    doc: Document,
    tolerance: Decimal = Decimal("0.50"),
) -> list[dict]:
    """
    Find potential duplicates for *doc* among the same user's documents.

    Criteria: same vendor name (case-insensitive) + same date + gross_amount within tolerance.
    Returns a list of warning dicts pointing to the duplicate document IDs.
    """
    if not doc.vendor_name or not doc.document_date or not doc.gross_amount:
        return []

    potential = (
        db.query(Document)
        .filter(
            Document.user_id == user_id,
            Document.id != doc.id,
            Document.document_date == doc.document_date,
            Document.vendor_name.ilike(doc.vendor_name),
        )
        .all()
    )

    warnings: list[dict] = []
    for other in potential:
        if other.gross_amount is not None:
            diff = abs(other.gross_amount - doc.gross_amount)
            if diff <= tolerance:
                warnings.append({
                    "code": "possible_duplicate",
                    "message": f"Possível duplicado: {other.vendor_name} {other.document_date} ({other.gross_amount}€) — id {other.id[:8]}…",
                    "severity": WARNING_SEVERITY_WARNING,
                    "field": None,
                    "duplicate_id": other.id,
                })

    return warnings


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

    return warnings

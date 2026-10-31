"""
Background receipt reading.

The upload request only stores the document (status "processing") and
returns; OCR, categorisation and the audit entries happen here afterwards,
so a slow photo never holds the request open. Each run opens its own
database session from the factory it is given.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Callable

from sqlalchemy.orm import Session

from app.models.document import Document
from app.schemas.document import drop_accepted_series_mismatch
from app.services.audit import log_auto_categorize, log_ocr_extraction
from app.services.categorization import categorize_document
from app.services.ocr import get_ocr_service
from app.services.storage import get_storage_service

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], Session]


async def read_receipt(session_factory: SessionFactory, document_id: str) -> None:
    """Run OCR for one document and store the result. Never raises."""
    db = session_factory()
    try:
        document = db.get(Document, document_id)
        if document is None or document.status != "processing":
            return
        await _read_into(db, document)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception(f"Reading receipt {document_id} failed")
        try:
            document = db.get(Document, document_id)
            if document is not None and document.status == "processing":
                document.status = "failed"
                document.ocr_raw_response = "Processing error"
                db.commit()
        except Exception:
            db.rollback()
    finally:
        db.close()


async def _read_into(db: Session, document: Document) -> None:
    ocr = get_ocr_service()
    file_content = get_storage_service().get_file(document.storage_key)
    if not file_content and ocr.backend != "mock":
        document.status = "failed"
        document.ocr_raw_response = "File content not available for OCR processing"
        return

    result = await ocr.process_document(file_content or b"mock_content", document.mime_type)
    document.vendor_name = result.vendor_name
    document.vendor_nif = result.vendor_nif
    document.invoice_number = result.invoice_number
    document.document_type = result.document_type or "unclassified"
    document.suggested_type = result.suggested_type
    document.suggested_invoice_number = result.suggested_invoice_number
    document.at_document_type = result.at_document_type
    document.document_date = result.document_date
    document.net_amount = result.net_amount
    document.vat_amount = result.vat_amount
    document.gross_amount = result.gross_amount
    document.vat_rate = result.vat_rate
    document.ocr_confidence = result.confidence
    document.ocr_raw_response = _with_file_hash(result.raw_response, file_content)
    document.expense_category, document.irs_sector = categorize_document(
        result.vendor_name, result.vendor_nif
    )

    if result.error:
        document.status = "failed"
    else:
        document.status = "needs_review" if result.needs_review else "ready"
    # A QR that arrives after a printed-pair acceptance retires that acceptance.
    if _result_has_at_pair(result):
        drop_accepted_series_mismatch(
            document, result.at_document_type or result.document_type
        )
    if result.error:
        return

    log_ocr_extraction(
        db,
        document_id=document.id,
        user_id=document.user_id,
        extracted_fields={
            "vendor_name": document.vendor_name,
            "vendor_nif": document.vendor_nif,
            "invoice_number": document.invoice_number,
            "document_date": document.document_date,
            "net_amount": document.net_amount,
            "vat_amount": document.vat_amount,
            "gross_amount": document.gross_amount,
            "vat_rate": document.vat_rate,
        },
    )
    if document.expense_category:
        log_auto_categorize(
            db,
            document_id=document.id,
            user_id=document.user_id,
            expense_category=document.expense_category,
            irs_sector=document.irs_sector or "geral",
        )


def _result_has_at_pair(result) -> bool:
    """True when this read carried a QR payload or an AT document code."""
    if getattr(result, "at_document_type", None):
        return True
    raw = getattr(result, "raw_response", None)
    if not raw:
        return False
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return False
    qr = payload.get("qr") if isinstance(payload, dict) else None
    return isinstance(qr, dict) and bool(qr.get("payload"))


def _with_file_hash(raw: str | None, file_content: bytes | None) -> str | None:
    if not file_content:
        return raw
    try:
        payload = json.loads(raw) if raw else {}
        if not isinstance(payload, dict):
            payload = {"ocr": raw}
    except json.JSONDecodeError:
        payload = {"ocr": raw}
    payload["file_sha256"] = hashlib.sha256(file_content).hexdigest()
    return json.dumps(payload, ensure_ascii=False)


def stuck_document_ids(db: Session) -> list[str]:
    """Documents left in "processing" (e.g. the server restarted mid-read)."""
    rows = (
        db.query(Document.id)
        .filter(Document.status == "processing", Document.deleted_at.is_(None))
        .all()
    )
    return [row.id for row in rows]

"""
Audit logging service.
Creates immutable audit records for document lifecycle events:
  create, ocr_extract, auto_categorize, update (user edits), delete.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.schemas.document import crosses_credit_boundary

logger = logging.getLogger(__name__)


def log_event(
    db: Session,
    *,
    entity_type: str,
    entity_id: str,
    user_id: str,
    action: str,
    source: str = "user",
    changes: Optional[dict[str, Any]] = None,
) -> AuditLog:
    """
    Write a single audit row.

    `changes` should be a dict of field names → {"old": ..., "new": ...}.
    """
    entry = AuditLog(
        entity_type=entity_type,
        entity_id=entity_id,
        user_id=user_id,
        action=action,
        source=source,
        changes_json=json.dumps(changes, default=str) if changes else None,
    )
    db.add(entry)
    # Don't commit here — let the caller decide when to commit.
    return entry


def log_document_create(db: Session, *, document_id: str, user_id: str) -> AuditLog:
    """Record that a document was uploaded / created."""
    return log_event(
        db,
        entity_type="document",
        entity_id=document_id,
        user_id=user_id,
        action="create",
        source="user",
    )


def log_ocr_extraction(
    db: Session,
    *,
    document_id: str,
    user_id: str,
    extracted_fields: dict[str, Any],
) -> AuditLog:
    """Record the fields that OCR populated."""
    changes = {k: {"old": None, "new": v} for k, v in extracted_fields.items() if v is not None}
    return log_event(
        db,
        entity_type="document",
        entity_id=document_id,
        user_id=user_id,
        action="ocr_extract",
        source="ocr",
        changes=changes,
    )


def log_auto_categorize(
    db: Session,
    *,
    document_id: str,
    user_id: str,
    expense_category: str,
    irs_sector: str,
) -> AuditLog:
    """Record the auto-assigned categories."""
    return log_event(
        db,
        entity_type="document",
        entity_id=document_id,
        user_id=user_id,
        action="auto_categorize",
        source="system",
        changes={
            "expense_category": {"old": None, "new": expense_category},
            "irs_sector": {"old": None, "new": irs_sector},
        },
    )


def log_document_update(
    db: Session,
    *,
    document_id: str,
    user_id: str,
    before: dict[str, Any],
    after: dict[str, Any],
) -> Optional[AuditLog]:
    """
    Record user edits.  Only logs if at least one field actually changed.
    `before` and `after` should contain the same keys.
    """
    changes: dict[str, Any] = {}
    for key in after:
        old_val = before.get(key)
        new_val = after[key]
        if str(old_val) != str(new_val):
            changes[key] = {"old": old_val, "new": new_val}

    if not changes:
        return None

    return log_event(
        db,
        entity_type="document",
        entity_id=document_id,
        user_id=user_id,
        action="update",
        source="user",
        changes=changes,
    )


def log_series_mismatch_accepted(
    db: Session,
    *,
    document_id: str,
    user_id: str,
    document_type: Optional[str],
    invoice_number: Optional[str],
    previous_accepted: bool,
    previous_type: Optional[str],
    previous_number: Optional[str],
) -> AuditLog:
    """Record that this user accepted a printed pair whose series does not match.

    The row is entity_id. The user is user_id. created_at is the timestamp.
    """
    accepted_at = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    return log_event(
        db,
        entity_type="document",
        entity_id=document_id,
        user_id=user_id,
        action="series_mismatch_accepted",
        source="user",
        changes={
            "series_mismatch_accepted": {"old": previous_accepted, "new": True},
            "document_type": {"old": previous_type, "new": document_type},
            "invoice_number": {"old": previous_number, "new": invoice_number},
            "accepted_at": {"old": None, "new": accepted_at},
        },
    )


def log_series_mismatch_cleared(
    db: Session,
    *,
    document_id: str,
    user_id: str,
    source: str,
    document_type: Optional[str],
    invoice_number: Optional[str],
) -> AuditLog:
    """Record that an accepted printed pair stopped being accepted.

    source is "user" for an edit, "qr" for a QR read, "efatura" for an e-Fatura link.
    """
    cleared_at = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    return log_event(
        db,
        entity_type="document",
        entity_id=document_id,
        user_id=user_id,
        action="series_mismatch_cleared",
        source=source,
        changes={
            "series_mismatch_accepted": {"old": True, "new": False},
            "document_type": {"old": None, "new": document_type},
            "invoice_number": {"old": None, "new": invoice_number},
            "cleared_at": {"old": None, "new": cleared_at},
        },
    )


def drop_accepted_series_mismatch(
    db: Session, document, arriving_type: Optional[str], *, source: str
) -> None:
    """A QR or e-Fatura pair ends a printed-pair acceptance.

    The acceptance entry stays, and a cleared entry is added when the flag was set.
    A confirmed row whose type now crosses the credit/invoice boundary against
    the arriving AT type goes back to review.
    """
    if document.series_mismatch_accepted:
        log_series_mismatch_cleared(
            db,
            document_id=document.id,
            user_id=document.user_id,
            source=source,
            document_type=document.document_type,
            invoice_number=document.invoice_number,
        )
    document.series_mismatch_accepted = False
    if document.status in ("ready", "accountant_review") and crosses_credit_boundary(
        arriving_type, document.document_type
    ):
        document.status = "needs_review"


def log_document_delete(db: Session, *, document_id: str, user_id: str) -> AuditLog:
    """Record that a document was deleted."""
    return log_event(
        db,
        entity_type="document",
        entity_id=document_id,
        user_id=user_id,
        action="delete",
        source="user",
    )


def get_entity_audit_trail(
    db: Session,
    entity_type: str,
    entity_id: str,
    limit: int = 50,
) -> list[AuditLog]:
    """Fetch the audit history for an entity, newest first."""
    return (
        db.query(AuditLog)
        .filter(AuditLog.entity_type == entity_type, AuditLog.entity_id == entity_id)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
        .all()
    )

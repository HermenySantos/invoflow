"""
Audit logging service.
Creates immutable audit records for document lifecycle events:
  create, ocr_extract, auto_categorize, update (user edits), delete.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog

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

"""
Audit trail API endpoints.
Read-only access to the audit history of documents and other entities.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user, CurrentUser
from app.schemas.audit_log import AuditLogEntry, AuditTrailResponse
from app.services.audit import get_entity_audit_trail
from app.api.documents import get_or_create_user
from app.models.document import Document

router = APIRouter()


@router.get("/documents/{document_id}", response_model=AuditTrailResponse)
async def get_document_audit_trail(
    document_id: str,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Get the full audit trail for a document.
    Shows OCR extractions, user edits, category changes, etc.
    """
    user = get_or_create_user(db, current_user)
    owns_document = (
        db.query(Document.id)
        .filter(Document.id == document_id, Document.user_id == user.id)
        .first()
    )
    if not owns_document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    entries = get_entity_audit_trail(db, "document", document_id, limit=limit)

    return AuditTrailResponse(
        entity_type="document",
        entity_id=document_id,
        entries=[
            AuditLogEntry(
                id=e.id,
                entity_type=e.entity_type,
                entity_id=e.entity_id,
                user_id=e.user_id,
                action=e.action,
                source=e.source,
                changes_json=e.changes_json,
                created_at=e.created_at,
            )
            for e in entries
        ],
        total=len(entries),
    )

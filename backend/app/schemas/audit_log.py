"""Pydantic schemas for the audit log API."""

from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class AuditLogEntry(BaseModel):
    """Single audit trail entry returned to the client."""
    id: str
    entity_type: str
    entity_id: str
    user_id: str
    action: str          # create, update, delete, ocr_extract, auto_categorize
    source: str          # ocr, user, system
    changes_json: Optional[str] = None   # JSON string of changes
    created_at: datetime

    class Config:
        from_attributes = True


class AuditTrailResponse(BaseModel):
    """Paginated audit trail for an entity."""
    entity_type: str
    entity_id: str
    entries: list[AuditLogEntry]
    total: int

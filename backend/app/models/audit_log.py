"""
Audit log model — tracks all changes to documents and other entities.
Records OCR extractions, user edits, status changes, and deletions.
"""

import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Text, Index
from app.core.database import Base


class AuditLog(Base):
    """Immutable audit trail for all entity changes."""

    __tablename__ = "audit_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # What was changed
    entity_type = Column(String(50), nullable=False)   # "document", "vat_sales"
    entity_id = Column(String(36), nullable=False)

    # Who changed it
    user_id = Column(String(36), nullable=False)

    # What happened
    action = Column(String(50), nullable=False)  # "create", "update", "delete", "ocr_extract", "auto_categorize"
    source = Column(String(50), nullable=False, default="user")  # "ocr", "user", "system"

    # Change details (JSON: {"field": {"old": ..., "new": ...}, ...})
    changes_json = Column(Text, nullable=True)

    # When
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_audit_entity", "entity_type", "entity_id"),
        Index("ix_audit_user", "user_id"),
    )

    def __repr__(self) -> str:
        return f"<AuditLog {self.action} {self.entity_type}:{self.entity_id}>"

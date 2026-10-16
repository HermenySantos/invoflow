"""e-Fatura identity for one account.

The payable reads documents. These tables hold the taxpayer NIF and the AT
snapshot so a pull can be repeated without a second expense.
"""

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, String, Text, UniqueConstraint

from app.core.database import Base


class EfaturaSubject(Base):
    """The taxpayer NIF this account pulls for. No password column."""

    __tablename__ = "efatura_subjects"

    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    taxpayer_nif = Column(String(9), nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:
        return f"<EfaturaSubject {self.user_id} {self.taxpayer_nif}>"


class EfaturaLink(Base):
    """One consultation row. source_key is the idempotency key. No money columns."""

    __tablename__ = "efatura_links"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    source_key = Column(String(200), nullable=False)
    role = Column(String(16), nullable=False)
    outcome = Column(String(32), nullable=False)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=True, index=True)
    fiscal_status = Column(String(20), nullable=False)
    warning = Column(Text, nullable=True)
    payload_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "source_key", name="uq_efatura_link_source"),
    )

    def __repr__(self) -> str:
        return f"<EfaturaLink {self.source_key} {self.outcome}>"

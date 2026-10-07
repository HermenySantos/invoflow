"""
VAT on Sales model — manual entry for the output-side of the IVA equation.

For MVP the user enters a single "total VAT on sales" for each period.
IVA payable = VAT on sales − deductible VAT on expenses.
"""

import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Integer, Numeric, Text, ForeignKey, UniqueConstraint
from app.core.database import Base


class VatSalesEntry(Base):
    """
    One record per user per period.
    period_type + year + period_value together define the period.
    """

    __tablename__ = "vat_sales_entries"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Period identification
    period_type = Column(String(10), nullable=False)   # "month" or "quarter"
    year = Column(Integer, nullable=False)
    period_value = Column(Integer, nullable=False)      # month 1-12 or quarter 1-4

    # Amount
    vat_amount = Column(Numeric(12, 2), nullable=False, default=0)

    # Optional note (e.g. "estimated from POS totals")
    notes = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "period_type", "year", "period_value", name="uq_vat_sales_period"),
    )

    def __repr__(self) -> str:
        return f"<VatSalesEntry {self.period_type}:{self.year}-{self.period_value} = {self.vat_amount}>"

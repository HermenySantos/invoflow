import uuid
from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import Boolean, Column, Index, String, DateTime, Date, Numeric, ForeignKey, Text, Integer, false as sql_false
from sqlalchemy.orm import relationship
from app.core.database import Base


class Document(Base):
    """
    Document model - represents a receipt or invoice.
    Stores both the file reference and extracted OCR data.
    """
    
    __tablename__ = "documents"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Status: pending, processing, ready, needs_review, failed
    status = Column(String(50), default="pending", nullable=False, index=True)
    
    # File storage
    storage_key = Column(String(500), nullable=False)  # R2 object key
    original_filename = Column(String(255), nullable=False)
    mime_type = Column(String(100), nullable=False)
    file_size = Column(Integer, nullable=True)  # bytes
    
    # Extracted data (nullable - filled by OCR)
    vendor_name = Column(String(255), nullable=True)
    vendor_nif = Column(String(20), nullable=True)  # Portuguese tax ID
    invoice_number = Column(String(100), nullable=True)
    # FT, FS, FR, NC, ND, or unclassified. Amounts stay non-negative; NC is the minus.
    # A missing type is unclassified, which is left out of the IVA totals.
    document_type = Column(
        String(20), nullable=False, default="unclassified", server_default="unclassified"
    )
    # Prefill for the review screen. Never used for netting or confirmation.
    suggested_type = Column(String(20), nullable=True)
    suggested_invoice_number = Column(String(100), nullable=True)
    # Raw AT code when the QR or e-Fatura type is not one we confirm (PF, OR, RG, GT, …).
    at_document_type = Column(String(16), nullable=True)
    document_date = Column(Date, nullable=True)
    
    # Amounts (in EUR)
    net_amount = Column(Numeric(12, 2), nullable=True)
    vat_amount = Column(Numeric(12, 2), nullable=True)
    gross_amount = Column(Numeric(12, 2), nullable=True)
    vat_rate = Column(Numeric(5, 2), nullable=True)  # e.g., 23.00 for 23%
    
    # OCR metadata
    ocr_confidence = Column(Numeric(5, 2), nullable=True)  # 0-100
    ocr_raw_response = Column(Text, nullable=True)  # JSON string
    
    # Review workflow
    review_notes = Column(Text, nullable=True)  # Notes for accountant or reviewer
    
    # Categorization
    expense_category = Column(String(50), nullable=True, index=True)  # Business: food, travel, utilities...
    irs_sector = Column(String(50), nullable=True, index=True)  # Tax: saude, educacao, geral...
    # User-set VAT deductible % (0-100), e.g. 0 for a passenger-car repair
    # (CIVA art. 21(1)(a)). None means use the category rule.
    deductible_pct_override = Column(Integer, nullable=True)
    # The user kept a printed FT/FS/FR pair whose series does not match the type.
    # Only when the row has no QR pair, no e-Fatura link and no stored AT type.
    # Cleared when a QR or e-Fatura pair arrives. Downgrading migration 010
    # drops this column; the audit log keeps the acceptance. Listed in exports.
    series_mismatch_accepted = Column(
        Boolean, nullable=False, default=False, server_default=sql_false()
    )
    # Set on an e-Fatura document: nif|type|number. Empty on scans.
    # One live or deleted value per user, so a restore cannot insert a second copy.
    at_invoice_identity = Column(String(200), nullable=True)
    
    # Timestamps
    # Set instead of deleting: invoices must be kept (10 years in Portugal), so
    # a "deleted" receipt is only hidden and its original file stays in storage.
    deleted_at = Column(DateTime, nullable=True, index=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index(
            "uq_documents_at_invoice_identity",
            "user_id",
            "at_invoice_identity",
            unique=True,
        ),
    )

    # Relationships
    user = relationship("User", back_populates="documents")
    
    def __repr__(self):
        return f"<Document {self.id} - {self.vendor_name or 'Unknown'}>"
    
    @property
    def period_tag(self) -> str:
        """Return YYYY-MM format for the document date."""
        if self.document_date:
            return self.document_date.strftime("%Y-%m")
        return self.created_at.strftime("%Y-%m")
    
    @property
    def quarter_tag(self) -> str:
        """Return YYYY-QX format for the document date."""
        dt = self.document_date or self.created_at.date()
        quarter = (dt.month - 1) // 3 + 1
        return f"{dt.year}-Q{quarter}"

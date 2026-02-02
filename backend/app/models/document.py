import uuid
from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import Column, String, DateTime, Date, Numeric, ForeignKey, Text, Integer
from sqlalchemy.orm import relationship
from app.core.database import Base


class Document(Base):
    """
    Document model - represents a receipt or invoice.
    Stores both the file reference and extracted OCR data.
    """
    
    __tablename__ = "documents"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
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
    document_date = Column(Date, nullable=True)
    
    # Amounts (in EUR)
    net_amount = Column(Numeric(12, 2), nullable=True)
    vat_amount = Column(Numeric(12, 2), nullable=True)
    gross_amount = Column(Numeric(12, 2), nullable=True)
    vat_rate = Column(Numeric(5, 2), nullable=True)  # e.g., 23.00 for 23%
    
    # OCR metadata
    ocr_confidence = Column(Numeric(5, 2), nullable=True)  # 0-100
    ocr_raw_response = Column(Text, nullable=True)  # JSON string
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
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

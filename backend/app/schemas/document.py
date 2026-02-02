from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, date
from decimal import Decimal


class UploadUrlRequest(BaseModel):
    """Request for a presigned upload URL."""
    filename: str = Field(..., min_length=1, max_length=255)
    content_type: str = Field(..., pattern=r"^(image|application)/.+$")


class UploadUrlResponse(BaseModel):
    """Response with presigned upload URL."""
    upload_url: str
    storage_key: str
    expires_in: int = 900  # 15 minutes


class DocumentCreate(BaseModel):
    """Create a new document after file upload."""
    storage_key: str = Field(..., min_length=1)
    original_filename: str = Field(..., min_length=1, max_length=255)
    mime_type: str = Field(..., pattern=r"^(image|application)/.+$")
    file_size: Optional[int] = None


class DocumentUpdate(BaseModel):
    """Update extracted document fields."""
    vendor_name: Optional[str] = Field(None, max_length=255)
    vendor_nif: Optional[str] = Field(None, max_length=20)
    invoice_number: Optional[str] = Field(None, max_length=100)
    document_date: Optional[date] = None
    net_amount: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    vat_amount: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    gross_amount: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    vat_rate: Optional[Decimal] = Field(None, ge=0, le=100, decimal_places=2)
    status: Optional[str] = Field(None, pattern=r"^(pending|processing|ready|needs_review|failed)$")


class DocumentResponse(BaseModel):
    """Document response with all fields."""
    id: str
    user_id: str
    status: str
    storage_key: str
    original_filename: str
    mime_type: str
    file_size: Optional[int]
    
    # Extracted data
    vendor_name: Optional[str]
    vendor_nif: Optional[str]
    invoice_number: Optional[str]
    document_date: Optional[date]
    net_amount: Optional[Decimal]
    vat_amount: Optional[Decimal]
    gross_amount: Optional[Decimal]
    vat_rate: Optional[Decimal]
    ocr_confidence: Optional[Decimal]
    
    # Computed
    period_tag: str
    quarter_tag: str
    
    # URLs
    file_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    
    # Timestamps
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class DocumentListResponse(BaseModel):
    """Paginated list of documents."""
    documents: list[DocumentResponse]
    total: int
    page: int
    page_size: int
    has_more: bool

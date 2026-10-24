from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional
from datetime import datetime, date
from decimal import Decimal, ROUND_HALF_UP


class UploadUrlRequest(BaseModel):
    """Request for a presigned upload URL."""
    filename: str = Field(..., min_length=1, max_length=255)
    content_type: str = Field(..., pattern=r"^(image/[A-Za-z0-9.+-]+|application/pdf)$")


class UploadUrlResponse(BaseModel):
    """Response with presigned upload URL."""
    upload_url: str
    storage_key: str
    expires_in: int = 900  # 15 minutes


class DocumentCreate(BaseModel):
    """Create a new document after file upload."""
    storage_key: str = Field(..., min_length=1, max_length=500)
    original_filename: str = Field(..., min_length=1, max_length=255)
    mime_type: str = Field(..., pattern=r"^(image/[A-Za-z0-9.+-]+|application/pdf)$")
    file_size: Optional[int] = None


_AMOUNT_TOLERANCE = Decimal("0.01")
_CENT = Decimal("0.01")
AMOUNT_MISMATCH_DETAIL = "O valor líquido mais o IVA tem de ser igual ao total."
TYPE_REQUIRED_DETAIL = "Indique o tipo de documento antes de o marcar como pronto."
NULL_TYPE_DETAIL = "O tipo de documento não pode ficar vazio."
CONCRETE_DOCUMENT_TYPES = ("FT", "FR", "FS", "ND", "NC")
DOCUMENT_TYPES = (*CONCRETE_DOCUMENT_TYPES, "unclassified")


def _round_cents(value):
    if value is None or value == "":
        return None
    return Decimal(str(value)).quantize(_CENT, rounding=ROUND_HALF_UP)


def amounts_are_consistent(net: Optional[Decimal], vat: Optional[Decimal], gross: Optional[Decimal]) -> bool:
    """Gross, net and IVA are non-negative. When all three are present, net + IVA matches gross.

    When net is missing, IVA cannot exceed gross (the implied net would be negative).
    """
    for amount in (net, vat, gross):
        if amount is not None and amount < 0:
            return False
    if net is None:
        if vat is not None and gross is not None and vat > gross:
            return False
        return True
    if vat is None or gross is None:
        return True
    return abs((net + vat) - gross) <= _AMOUNT_TOLERANCE


class DocumentUpdate(BaseModel):
    """Update extracted document fields."""
    vendor_name: Optional[str] = Field(None, max_length=255)
    vendor_nif: Optional[str] = Field(None, max_length=20)
    invoice_number: Optional[str] = Field(None, max_length=100)
    document_type: Optional[str] = Field(None, pattern=r"^(FT|FR|FS|ND|NC|unclassified)$")
    document_date: Optional[date] = None
    net_amount: Optional[Decimal] = Field(None, ge=0)
    vat_amount: Optional[Decimal] = Field(None, ge=0)
    gross_amount: Optional[Decimal] = Field(None, ge=0)
    vat_rate: Optional[Decimal] = Field(None, ge=0, le=100)
    status: Optional[str] = Field(None, pattern=r"^(pending|processing|ready|needs_review|accountant_review|failed)$")
    review_notes: Optional[str] = Field(None, max_length=1000)
    expense_category: Optional[str] = Field(None, max_length=50)
    irs_sector: Optional[str] = Field(None, max_length=50)
    # 0-100; send null to go back to the category rule.
    deductible_pct_override: Optional[int] = Field(None, ge=0, le=100)

    @field_validator("net_amount", "vat_amount", "gross_amount", mode="before")
    @classmethod
    def round_money(cls, value):
        return _round_cents(value)

    @model_validator(mode="after")
    def amounts_match(self) -> "DocumentUpdate":
        # A partial edit may leave the stored row inconsistent. Sending all
        # three amounts that do not add up is a complete, rejected triple.
        if not amounts_are_consistent(self.net_amount, self.vat_amount, self.gross_amount):
            raise ValueError(AMOUNT_MISMATCH_DETAIL)
        return self


class FieldConfidence(BaseModel):
    """Per-field OCR confidence scores."""
    vendor_name: Optional[float] = None
    vendor_nif: Optional[float] = None
    invoice_number: Optional[float] = None
    document_date: Optional[float] = None
    net_amount: Optional[float] = None
    vat_amount: Optional[float] = None
    gross_amount: Optional[float] = None
    vat_rate: Optional[float] = None


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
    document_type: Optional[str] = None
    suggested_type: Optional[str] = None
    suggested_invoice_number: Optional[str] = None
    at_document_type: Optional[str] = None
    document_date: Optional[date]
    net_amount: Optional[Decimal]
    vat_amount: Optional[Decimal]
    gross_amount: Optional[Decimal]
    vat_rate: Optional[Decimal]
    ocr_confidence: Optional[Decimal]
    
    # Per-field confidence (parsed from ocr_raw_response)
    field_confidence: Optional[FieldConfidence] = None
    
    # Review workflow
    review_notes: Optional[str] = None
    
    # Categorization
    expense_category: Optional[str] = None
    irs_sector: Optional[str] = None
    deductible_pct: int = 0                         # what the estimate uses
    deductible_pct_override: Optional[int] = None   # user-set, if any
    
    # Validation warnings (populated per-request)
    validation_warnings: list[dict] = []
    fictional: bool = False
    
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

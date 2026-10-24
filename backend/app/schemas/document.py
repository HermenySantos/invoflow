import re
import unicodedata
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
SERIES_MISMATCH_DETAIL = "O n.º do documento não corresponde ao tipo indicado."
CONCRETE_DOCUMENT_TYPES = ("FT", "FR", "FS", "ND", "NC")
DOCUMENT_TYPES = (*CONCRETE_DOCUMENT_TYPES, "unclassified")
# A series token, then a boundary. "frete", "fr001", "FS2026/12" and "FRA2026/12" are not one.
_SERIES_TOKEN = re.compile(r"^(?P<code>FT|FS|FR|NC|ND)(?=[\s/.\-]|$)", re.IGNORECASE)
# "NCA/5": the code, one extra letter, then a separator.
_SERIES_GLUED_LETTER = re.compile(
    r"^(?P<code>FT|FS|FR|NC|ND)[A-Za-z](?=[\s/.\-])",
    re.IGNORECASE,
)
# "N/C", "N.C", "N-C", "N C A/5", "N.C. A/5".
_SERIES_SPLIT = re.compile(
    r"^(?P<c1>[A-Za-z])[\s./\-]+(?P<c2>[A-Za-z])(?=[\s/.\-]|$)",
)
# Cyrillic and Greek letters that stand in for the Latin series codes.
# U+041D (Н) folds to N so "НC" is the NC series.
_CONFUSABLES = str.maketrans(
    {
        chr(code): latin
        for code, latin in (
            (0x0391, "A"), (0x03B1, "a"),  # Greek alpha
            (0x0392, "B"), (0x03B2, "b"),
            (0x0395, "E"), (0x03B5, "e"),
            (0x0396, "Z"), (0x03B6, "z"),
            (0x0397, "H"), (0x03B7, "h"),
            (0x0399, "I"), (0x03B9, "i"),
            (0x039A, "K"), (0x03BA, "k"),
            (0x039C, "M"), (0x03BC, "m"),
            (0x039D, "N"), (0x03BD, "n"),
            (0x039F, "O"), (0x03BF, "o"),
            (0x03A1, "P"), (0x03C1, "p"),
            (0x03A4, "T"), (0x03C4, "t"),
            (0x03A5, "Y"), (0x03C5, "y"),
            (0x03A7, "X"), (0x03C7, "x"),
            (0x0410, "A"), (0x0430, "a"),  # Cyrillic a
            (0x0412, "B"), (0x0432, "b"),
            (0x0415, "E"), (0x0435, "e"),
            (0x041A, "K"), (0x043A, "k"),
            (0x041C, "M"), (0x043C, "m"),
            (0x041D, "N"), (0x043D, "n"),  # Н, the H-shaped letter, read here as N
            (0x041E, "O"), (0x043E, "o"),
            (0x0420, "P"), (0x0440, "p"),
            (0x0421, "C"), (0x0441, "c"),
            (0x0422, "T"), (0x0442, "t"),
            (0x0423, "Y"), (0x0443, "y"),
            (0x0425, "X"), (0x0445, "x"),
            (0x0406, "I"), (0x0456, "i"),
            (0x0407, "I"), (0x0457, "i"),
            (0x0408, "J"), (0x0458, "j"),
        )
    }
)


def fold_series_text(value: Optional[str]) -> str:
    """NFKC, then the small confusables fold. Empty when there is nothing to read."""
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value)).translate(_CONFUSABLES)
    return text.strip()


def invoice_series_prefix(number: Optional[str]) -> Optional[str]:
    """FT, FS, FR, NC or ND as a token at the start of a document number.

    'NC-A/5', 'NCA/5', 'N/C' and 'N C A/5' count. 'frete 12', 'fr001',
    'FS2026/12' and 'FRA2026/12' do not. A number with no recognisable
    prefix is allowed with any type.
    """
    text = fold_series_text(number)
    if not text:
        return None
    token = _SERIES_TOKEN.match(text)
    if token:
        return token.group("code").upper()
    glued = _SERIES_GLUED_LETTER.match(text)
    if glued:
        return glued.group("code").upper()
    split = _SERIES_SPLIT.match(text)
    if not split:
        return None
    code = (split.group("c1") + split.group("c2")).upper()
    if code not in CONCRETE_DOCUMENT_TYPES:
        return None
    return code


def _norm_type(value: Optional[str]) -> str:
    return fold_series_text(value).upper()


def _norm_number(value: Optional[str]) -> str:
    return fold_series_text(value).casefold()


def series_fields_changed(
    stored_type: Optional[str],
    stored_number: Optional[str],
    update: dict,
) -> bool:
    """True when this write changes the type or the number compared with the stored row."""
    if "document_type" in update and _norm_type(update.get("document_type")) != _norm_type(stored_type):
        return True
    if "invoice_number" in update and _norm_number(update.get("invoice_number")) != _norm_number(stored_number):
        return True
    return False


def keeps_at_issued_pair(
    merged_type: Optional[str],
    merged_number: Optional[str],
    issued: Optional[tuple],
) -> bool:
    """True when the saved type and number are still the pair AT supplied."""
    if not issued:
        return False
    at_type, at_number = issued
    return _norm_type(merged_type) == _norm_type(at_type) and _norm_number(merged_number) == _norm_number(at_number)


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
    at_invoice_number: Optional[str] = None
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

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
SERIES_OVERRIDE_WARNING = (
    "O n.º não corresponde ao tipo. Confirme só se for o par impresso no documento."
)
CONCRETE_DOCUMENT_TYPES = ("FT", "FR", "FS", "ND", "NC")
DOCUMENT_TYPES = (*CONCRETE_DOCUMENT_TYPES, "unclassified")
# The printed-pair flag may only cross codes inside this family.
INVOICE_FAMILY = frozenset({"FT", "FS", "FR"})
# A series token, then a boundary. A dot counts only when a letter follows
# ("NC.A/5", "fr.a"). A dot then a digit is an abbreviation ("Fr.12", "Nc.12").
_SERIES_TOKEN = re.compile(
    r"^(?P<code>FT|FS|FR|NC|ND)(?=[\s/\-]|$|\.(?=[A-Za-z]))",
    re.IGNORECASE,
)
# "NCA/5": the code, one extra letter, then / . or -. Whitespace does not count,
# so "FRA 2026/12" is vendor numbering.
_SERIES_GLUED_LETTER = re.compile(
    r"^(?P<code>FT|FS|FR|NC|ND)[A-Za-z](?=[/.\-])",
    re.IGNORECASE,
)
# "NC2026/5". Glued digits are a series only when / . or - follows them.
# "NC1" has no separator, so it stays vendor numbering.
_SERIES_GLUED_DIGIT = re.compile(r"^(?P<code>NC|ND)\d+(?=[/.\-])", re.IGNORECASE)
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
            (0x0274, "N"),  # ɴ small capital n
            (0x1D04, "C"),  # ᴄ small capital c
            (0xA730, "F"),  # ꜰ
            (0x1D1B, "T"),  # ᴛ
            (0xA731, "S"),  # ꜱ
            (0x0280, "R"),  # ʀ
            (0x1D05, "D"),  # ᴅ
            (0xA4E0, "N"),  # ꓠ Lisu na, the N lookalike
            (0xA4DA, "C"),  # ꓚ Lisu ca, the C lookalike
        )
    }
)
# Unicode hyphens and slashes that should be the ASCII series separators.
_HYPHEN_SLASH = str.maketrans(
    {
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2015": "-",
        "\u2212": "-",
        "\ufe58": "-",
        "\ufe63": "-",
        "\uff0d": "-",
        "\u2044": "/",
        "\u2215": "/",
        "\u29f8": "/",
        "\uff0f": "/",
    }
)


def fold_series_text(value: Optional[str]) -> str:
    """Normalise a document number before the series token is read.

    NFKC, then format characters (zero-width space, BOM, soft hyphen) are
    dropped. Greek, Cyrillic, small-cap and Lisu lookalikes fold to Latin.
    Accents fold away (Ń/Ć). Unicode hyphens and slashes become ASCII.
    """
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Cf")
    text = text.translate(_CONFUSABLES)
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.translate(_HYPHEN_SLASH)
    return text.strip()


def invoice_series_prefix(number: Optional[str]) -> Optional[str]:
    """FT, FS, FR, NC or ND as a token at the start of a document number.

    Counts: 'NC-A/5', 'NCA/5', 'N/C', 'N C A/5', 'NC.A/5', 'fr.a', 'NC2026/5'.
    A dot then a letter is a series. A dot then a digit is not ('Fr.12',
    'Fs.12', 'Nc.12', 'nd.2026'). Glued NC/ND digits count only when a
    separator follows ('NC2026/5'), so 'NC1' does not.
    Does not count: 'frete 12', 'fr001', 'FS2026/12', 'FT2026/1',
    'FRA2026/12', 'Fr. 12', 'FRA 2026/12'. A number with no recognisable
    prefix is allowed with any type.
    """
    text = fold_series_text(number)
    if not text:
        return None
    token = _SERIES_TOKEN.match(text)
    if token:
        return token.group("code").upper()
    glued_digit = _SERIES_GLUED_DIGIT.match(text)
    if glued_digit:
        return glued_digit.group("code").upper()
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


def series_disagrees(document_type: Optional[str], invoice_number: Optional[str]) -> bool:
    """True when a concrete type and the number's series token are different codes."""
    if document_type not in CONCRETE_DOCUMENT_TYPES:
        return False
    series = invoice_series_prefix(invoice_number)
    return series is not None and series != document_type


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


def series_override_allowed(
    document_type: Optional[str],
    invoice_number: Optional[str],
    issued: Optional[tuple],
) -> bool:
    """The printed-pair flag applies only with no AT pair, and only inside {FT, FS, FR}.

    A QR pair or an e-Fatura pair makes ``issued`` set, and the flag is ignored.
    NC or ND on either side crosses the credit/debit boundary and is refused.
    """
    if issued is not None:
        return False
    if document_type not in INVOICE_FAMILY:
        return False
    prefix = invoice_series_prefix(invoice_number)
    return prefix in INVOICE_FAMILY and prefix != document_type


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
    # Not a column. Honoured only when the row has no QR pair and no e-Fatura
    # pair, and only for a mismatch inside {FT, FS, FR}. The stored flag is
    # series_mismatch_accepted.
    accept_series_mismatch: bool = False

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
    series_mismatch_accepted: bool = False
    
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

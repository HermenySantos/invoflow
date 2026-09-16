"""
Portuguese receipt/invoice field extraction from OCR text.

Adapted as ideas (not copied code) from the TaxHacker OSS pipeline:
OCR/text first, then a structured schema (vendor, tax id, date, amounts).
This module is regex/heuristic only — no paid APIs.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional


PT_VAT_RATES = (Decimal("23.00"), Decimal("13.00"), Decimal("6.00"), Decimal("0.00"))

NIF_LABELED = re.compile(
    r"(?:NIF|NIPC|N\.?\s*I\.?\s*F\.?|Contribuinte|N\.?\s*Contribuinte)"
    r"[:\s]*([PT]{0,2}\s*\d{9})",
    re.IGNORECASE,
)
NIF_BARE = re.compile(r"\b(?:PT)?(\d{9})\b")
DATE_DMY = re.compile(
    r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})\b"
)
DATE_YMD = re.compile(
    r"\b(\d{4})[./-](\d{1,2})[./-](\d{1,2})\b"
)
INVOICE_NO = re.compile(
    r"(?:FT|FR|FS|NC|ND|Fatura|Factura|Recibo|Invoice)[:\s#º°]*([A-Z0-9][A-Z0-9/.\-]{2,20})",
    re.IGNORECASE,
)
MONEY = re.compile(
    r"(?<!\d)(\d{1,3}(?:[.\s]\d{3})*(?:,\d{2})|\d+,\d{2}|\d+\.\d{2})(?!\d)"
)
VAT_LINE = re.compile(
    r"(?:IVA|I\.V\.A\.|VAT)\s*(?:\(?(6|13|23|0)\s*%?\)?)?[:\s]*"
    r"(?:EUR|€)?\s*(\d{1,3}(?:[.\s]\d{3})*,\d{2}|\d+[.,]\d{2})",
    re.IGNORECASE,
)
TOTAL_LINE = re.compile(
    r"(?:Total(?:\s+(?:a\s+pagar|geral|il[ií]quido|l[ií]quido))?|Valor\s+total|"
    r"Gross|Amount\s+due)[:\s]*(?:EUR|€)?\s*"
    r"(\d{1,3}(?:[.\s]\d{3})*,\d{2}|\d+[.,]\d{2})",
    re.IGNORECASE,
)
NET_LINE = re.compile(
    r"(?:Incid[eê]ncia|Base|Net(?:o)?|Il[ií]quido|Taxable)[:\s]*(?:EUR|€)?\s*"
    r"(\d{1,3}(?:[.\s]\d{3})*,\d{2}|\d+[.,]\d{2})",
    re.IGNORECASE,
)
SKIP_VENDOR = re.compile(
    r"^(nif|nipc|contribuinte|fatura|factura|recibo|total|iva|data|tel|www|"
    r"http|email|rua|av\.|avenida|pt-|portugal)\b",
    re.IGNORECASE,
)


@dataclass
class ExtractedFields:
    vendor_name: Optional[str] = None
    vendor_nif: Optional[str] = None
    invoice_number: Optional[str] = None
    document_date: Optional[date] = None
    net_amount: Optional[Decimal] = None
    vat_amount: Optional[Decimal] = None
    gross_amount: Optional[Decimal] = None
    vat_rate: Optional[Decimal] = None
    confidence: float = 0.0
    needs_review: bool = True

    def to_raw_dict(self) -> dict:
        data = asdict(self)
        for key in ("net_amount", "vat_amount", "gross_amount", "vat_rate"):
            if data[key] is not None:
                data[key] = str(data[key])
        if data["document_date"] is not None:
            data["document_date"] = data["document_date"].isoformat()
        return data


def parse_pt_amount(raw: str) -> Optional[Decimal]:
    """Parse a PT/EU money string (1.234,56 or 12,50 or 12.50)."""
    if not raw:
        return None
    cleaned = raw.strip().replace(" ", "").replace("€", "").replace("EUR", "")
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        return None
    if value < 0 or value > Decimal("1000000"):
        return None
    return value.quantize(Decimal("0.01"))


def extract_portuguese_nif(text: str) -> Optional[str]:
    if not text:
        return None
    labeled = NIF_LABELED.search(text)
    if labeled:
        digits = re.sub(r"\D", "", labeled.group(1))
        if _looks_like_nif(digits):
            return digits
    for match in NIF_BARE.finditer(text):
        digits = match.group(1)
        if _looks_like_nif(digits):
            return digits
    return None


def _looks_like_nif(nif: str) -> bool:
    return len(nif) == 9 and nif[0] in "12356789"


def _parse_date(text: str) -> Optional[date]:
    for match in DATE_YMD.finditer(text):
        year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
        parsed = _safe_date(year, month, day)
        if parsed:
            return parsed
    for match in DATE_DMY.finditer(text):
        day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
        if year < 100:
            year += 2000
        parsed = _safe_date(year, month, day)
        if parsed:
            return parsed
    return None


def _safe_date(year: int, month: int, day: int) -> Optional[date]:
    try:
        parsed = date(year, month, day)
    except ValueError:
        return None
    if parsed.year < 1990 or parsed > date.today():
        return None
    return parsed


def _guess_vendor(lines: list[str]) -> Optional[str]:
    for line in lines[:12]:
        cleaned = re.sub(r"\s+", " ", line).strip(" -·•|")
        if len(cleaned) < 3 or len(cleaned) > 80:
            continue
        if SKIP_VENDOR.match(cleaned):
            continue
        if re.fullmatch(r"[\d\s./:-]+", cleaned):
            continue
        if MONEY.search(cleaned) and not re.search(r"[A-Za-zÀ-ú]{3,}", cleaned):
            continue
        return cleaned[:255]
    return None


def _nearest_vat_rate(rate: Decimal) -> Optional[Decimal]:
    for official in PT_VAT_RATES:
        if abs(rate - official) <= Decimal("0.50"):
            return official
    return None


def extract_fields(text: str) -> ExtractedFields:
    """Turn raw OCR/PDF text into invoice fields. Always review-friendly."""
    result = ExtractedFields()
    if not text or not text.strip():
        result.confidence = 0
        result.needs_review = True
        return result

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    result.vendor_name = _guess_vendor(lines)
    result.vendor_nif = extract_portuguese_nif(text)
    result.document_date = _parse_date(text)

    invoice = INVOICE_NO.search(text)
    if invoice:
        result.invoice_number = invoice.group(0).strip()[:100]

    vat_match = VAT_LINE.search(text)
    if vat_match:
        if vat_match.group(1):
            result.vat_rate = Decimal(vat_match.group(1)).quantize(Decimal("0.01"))
        result.vat_amount = parse_pt_amount(vat_match.group(2))

    total_match = TOTAL_LINE.search(text)
    if total_match:
        result.gross_amount = parse_pt_amount(total_match.group(1))

    net_match = NET_LINE.search(text)
    if net_match:
        result.net_amount = parse_pt_amount(net_match.group(1))

    if result.gross_amount is None:
        amounts = [parse_pt_amount(m.group(1)) for m in MONEY.finditer(text)]
        amounts = [a for a in amounts if a and a >= Decimal("0.50")]
        if amounts:
            result.gross_amount = max(amounts)

    if result.gross_amount and result.vat_amount and result.net_amount is None:
        result.net_amount = result.gross_amount - result.vat_amount
    if result.gross_amount and result.net_amount and result.vat_amount is None:
        vat = result.gross_amount - result.net_amount
        if vat >= 0:
            result.vat_amount = vat

    if result.net_amount and result.vat_amount and result.net_amount > 0 and result.vat_rate is None:
        guessed = (result.vat_amount / result.net_amount * 100).quantize(Decimal("0.01"))
        result.vat_rate = _nearest_vat_rate(guessed) or guessed

    filled = sum(
        1
        for value in (
            result.vendor_name,
            result.vendor_nif,
            result.document_date,
            result.gross_amount,
            result.vat_amount,
        )
        if value is not None
    )
    result.confidence = min(95.0, 20.0 * filled)
    result.needs_review = (
        result.confidence < 85
        or not result.vendor_name
        or not result.gross_amount
        or not result.document_date
    )
    return result


def extracted_to_json(fields: ExtractedFields, extra: Optional[dict] = None) -> str:
    payload = {"extractor": "oss-pt", "fields": fields.to_raw_dict()}
    if extra:
        payload.update(extra)
    return json.dumps(payload, ensure_ascii=False)

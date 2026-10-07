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


# Standard / intermediate / reduced rates, then exempt.
PT_VAT_RATES = tuple(
    Decimal(rate)
    for rate in (
        "23.00", "13.00", "6.00",   # Mainland
        "22.00", "12.00", "5.00",   # Madeira
        "16.00", "9.00", "4.00",    # Azores
        "0.00",
    )
)

NIF_LABELED = re.compile(
    r"(?:NIF|NIPC|N\.?\s*I\.?\s*F\.?|Contribuinte|N\.?\s*Contribuinte)"
    r"[:\s]*([PT]{0,2}\s*\d{9})",
    re.IGNORECASE,
)
CUSTOMER_LABEL = re.compile(r"cliente|adquirente|consumidor|customer", re.IGNORECASE)
NIF_BARE = re.compile(r"\b(?:PT)?(\d{9})\b")
DATE_DMY = re.compile(
    r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})\b"
)
DATE_YMD = re.compile(
    r"\b(\d{4})[./-](\d{1,2})[./-](\d{1,2})\b"
)
INVOICE_NO = re.compile(
    r"(?<![A-Za-z])(?:FT|FR|FS|NC|ND|Fatura|Factura|Recibo|Invoice)"
    r"[:\s#º°]+(?=\S*\d)([A-Z0-9][A-Z0-9/.\-]{1,30})",
    re.IGNORECASE,
)
MONEY = re.compile(
    r"(?<!\d)\$?\s*(\d{1,3}(?:[.\s]\d{3})*(?:,\s*\d{2})|\d+,\s*\d{2}|\d+\.\d{2})(?!\d)"
)
DATE_BROKEN_YEAR = re.compile(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{2})\s+(\d{2})(?!\d|:)")
VAT_LABEL = re.compile(
    r"\b(?:IVA|I\.V\.A\.|VAT|MwSt\.?|Sales\s+tax|Imposta)\b",
    re.IGNORECASE,
)
VAT_SKIP = re.compile(r"senkung|reduction", re.IGNORECASE)
RATE_IN_LINE = re.compile(r"\b(\d{1,2})(?:[.,]\d+)?\s*%")
SKIP_TOTAL_LINE = re.compile(
    r"r[uüú]ckgeld|troco|previous\s+balance|total\s+due|amount\s+due|"
    r"\bbar\b|numer[aá]rio|subtotal|senkung",
    re.IGNORECASE,
)
STRONG_TOTAL = re.compile(
    r"\b(?:total(?:e)?|summe|somma|valor\s+total)\b",
    re.IGNORECASE,
)
PAYMENT_TOTAL = re.compile(
    r"\b(?:importo\s+pagato|pagamento|to\s*pay)\b",
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
    # One entry per VAT rate when the receipt has more than one; rate is then None.
    vat_breakdown: Optional[list[dict]] = None
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
    cleaned = _normalise_separators(cleaned)
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        return None
    if value < 0 or value > Decimal("1000000"):
        return None
    return value.quantize(Decimal("0.01"))


def _normalise_separators(number: str) -> str:
    """Make the decimal separator a dot and drop thousands separators.

    The last separator is the decimal one, unless exactly three digits follow
    it (1.234 / 1,234), which is a thousands group.
    """
    last = max(number.rfind("."), number.rfind(","))
    if last == -1:
        return number
    decimals = number[last + 1 :]
    integer = number[:last].replace(".", "").replace(",", "")
    if len(decimals) == 3:
        return integer + decimals
    return f"{integer}.{decimals}"


def extract_portuguese_nif(text: str) -> Optional[str]:
    if not text:
        return None
    customer_nifs: set[str] = set()
    vendor_nif: Optional[str] = None
    for labeled in NIF_LABELED.finditer(text):
        digits = re.sub(r"\D", "", labeled.group(1))
        if not _looks_like_nif(digits):
            continue
        if _is_customer_label(text, labeled.start()):
            customer_nifs.add(digits)
        elif vendor_nif is None:
            vendor_nif = digits
    if vendor_nif:
        return vendor_nif
    for match in NIF_BARE.finditer(text):
        digits = match.group(1)
        if digits not in customer_nifs and _looks_like_nif(digits):
            return digits
    return None


def _is_customer_label(text: str, start: int) -> bool:
    """True when the words just before a NIF label name the buyer, not the seller."""
    line_start = text.rfind("\n", 0, start) + 1
    before = text[max(line_start, start - 30) : start]
    before = re.split(r"[/|;]", before)[-1]
    return bool(CUSTOMER_LABEL.search(before))


def _looks_like_nif(nif: str) -> bool:
    if len(nif) != 9 or not nif.isdigit() or nif[0] not in "12356789":
        return False
    # Mod-11 check digit.
    total = sum(int(digit) * weight for digit, weight in zip(nif[:8], range(9, 1, -1)))
    check = 11 - total % 11
    return (0 if check >= 10 else check) == int(nif[8])


def _money_amounts(line: str) -> list[Decimal]:
    """Money tokens on one line. A number followed by % is a rate, not an amount."""
    amounts: list[Decimal] = []
    for match in MONEY.finditer(line):
        if line[match.end() :].lstrip().startswith("%"):
            continue
        amount = parse_pt_amount(match.group(1))
        if amount is not None and amount > 0:
            amounts.append(amount)
    return amounts


def _last_labeled_amount(lines: list[str], label: re.Pattern[str]) -> Optional[Decimal]:
    found: Optional[Decimal] = None
    for line in lines:
        if SKIP_TOTAL_LINE.search(line):
            continue
        if not label.search(line):
            continue
        amounts = _money_amounts(line)
        if amounts:
            found = amounts[-1]
    return found


def _largest_labeled_amount(lines: list[str], label: re.Pattern[str]) -> Optional[Decimal]:
    found: list[Decimal] = []
    for line in lines:
        if SKIP_TOTAL_LINE.search(line):
            continue
        if not label.search(line):
            continue
        amounts = _money_amounts(line)
        if amounts:
            found.append(amounts[-1])
    return max(found) if found else None


def _extract_vat(
    lines: list[str],
) -> tuple[Optional[Decimal], Optional[Decimal], Optional[Decimal], list[dict]]:
    """Return (rate, vat amount, net, per-rate breakdown) from the tax summary.

    Receipts with several rates list one line per rate ("IVA 6% 10,00 0,60");
    those lines are summed. The rate is None when they differ.
    """
    rate: Optional[Decimal] = None
    vat_amount: Optional[Decimal] = None
    net_amount: Optional[Decimal] = None
    breakdown: list[dict] = []
    for line in lines:
        if VAT_SKIP.search(line) or not VAT_LABEL.search(line):
            continue
        amounts = _money_amounts(line)
        rate_match = RATE_IN_LINE.search(line)
        if not amounts and not rate_match:
            continue
        if rate_match:
            rate = Decimal(rate_match.group(1)).quantize(Decimal("0.01"))
        if rate_match and len(amounts) >= 2:
            net_amount = amounts[-2]
            vat_amount = amounts[-1]
            breakdown.append({"rate": rate, "net": net_amount, "vat": vat_amount})
        elif amounts:
            vat_amount = amounts[-1]
            net_amount = None
    if len(breakdown) > 1:
        rates = {entry["rate"] for entry in breakdown}
        rate = rates.pop() if len(rates) == 1 else None
        net_amount = sum((entry["net"] for entry in breakdown), Decimal("0"))
        vat_amount = sum((entry["vat"] for entry in breakdown), Decimal("0"))
    return rate, vat_amount, net_amount, breakdown


def _parse_date(text: str) -> Optional[date]:
    for match in DATE_YMD.finditer(text):
        year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
        parsed = _safe_date(year, month, day)
        if parsed:
            return parsed
    for match in DATE_DMY.finditer(text):
        # "11/15/20 19" is a year split by the PDF reader, not 2020.
        if match.group(3).__len__() == 2 and DATE_BROKEN_YEAR.match(text, match.start()):
            continue
        first, second, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
        if year < 100:
            year += 2000
        parsed = _safe_date(year, second, first) or _safe_date(year, first, second)
        if parsed:
            return parsed
    for match in DATE_BROKEN_YEAR.finditer(text):
        first, second = int(match.group(1)), int(match.group(2))
        year = int(match.group(3) + match.group(4))
        parsed = _safe_date(year, second, first) or _safe_date(year, first, second)
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
        result.invoice_number = invoice.group(1).strip()[:100]

    vat_rate, vat_amount, vat_net, breakdown = _extract_vat(lines)
    result.vat_rate = vat_rate
    result.vat_amount = vat_amount
    result.net_amount = vat_net
    mixed_rates = len(breakdown) > 1
    if mixed_rates:
        result.vat_breakdown = [
            {key: str(value) for key, value in entry.items()} for entry in breakdown
        ]

    result.gross_amount = _last_labeled_amount(lines, STRONG_TOTAL)
    if result.gross_amount is None:
        result.gross_amount = _largest_labeled_amount(lines, PAYMENT_TOTAL)

    net_match = None if mixed_rates else NET_LINE.search(text)
    if net_match:
        labeled_net = parse_pt_amount(net_match.group(1))
        if labeled_net is not None:
            result.net_amount = labeled_net

    if result.gross_amount and result.vat_amount and result.net_amount is None:
        result.net_amount = result.gross_amount - result.vat_amount
    if result.gross_amount and result.net_amount and result.vat_amount is None:
        vat = result.gross_amount - result.net_amount
        if vat >= 0:
            result.vat_amount = vat

    if (
        result.net_amount
        and result.vat_amount
        and result.net_amount > 0
        and result.vat_rate is None
        and not mixed_rates
    ):
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

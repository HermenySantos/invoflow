"""
Portuguese receipt/invoice field extraction from OCR text.

Adapted as ideas (not copied code) from the TaxHacker OSS pipeline:
OCR/text first, then a structured schema (vendor, tax id, date, amounts).
This module is regex/heuristic only — no paid APIs.
"""

from __future__ import annotations

import json
import re
import unicodedata
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
DATE_PT_TEXT = re.compile(
    r"\b(\d{1,2})\s+de\s+([A-Za-zÀ-ÿ]{3,})\.?\s+de\s+(\d{4})\b",
    re.IGNORECASE,
)
DATE_PT_ABBR = re.compile(
    r"\b(\d{1,2})[./-]([A-Za-zÀ-ÿ]{3,})\.?[./-](\d{4})\b",
    re.IGNORECASE,
)
_ISSUE_LABEL = re.compile(
    r"data\s+de\s+emiss[aã]o|data\s+do\s+documento|issue\s+date|invoice\s+date|"
    r"(?<![A-Za-zÀ-ÿ])(?:data|date)\b",
    re.IGNORECASE,
)
_DUE_LABEL = re.compile(
    r"\bvencimento\b|\bdue(?:\s+date)?\b|\bdata\s+limite\b|\bpagamento\s+at[eé]\b",
    re.IGNORECASE,
)
_LETTERHEAD = re.compile(
    r"^[A-ZÀ-Ý][\wÀ-ÿ.'’\- ]{1,40},\s*\d{1,2}\s+de\s+",
)
# A heading. Citation and origin lines are not the document's own title.
_TITLE_HEAD = re.compile(
    r"^\s*(?:fatura|factura|nota\s+de|notade|n0ta|credit\s+note|invoice|recibo)\b",
    re.IGNORECASE,
)
_NUMBER_HEAD = re.compile(r"^\s*(?:FT|FR|FS|NC|ND)\b", re.IGNORECASE)
_ORIGIN_LINE = re.compile(
    r"^\s*(?:fatura\s+de\s+origem|ref\.|referente\b|doc\.?\s*origem)",
    re.IGNORECASE,
)
_NOTA_TITLE = re.compile(
    r"^\s*nota\s+de\s+(?:cr[eé]dito|d[eé]bito)\b",
    re.IGNORECASE,
)
# A credit or debit heading, including the OCR slips the gate listed.
_NC_HEAD = re.compile(
    r"^\s*(?:n[o0]ta\s*de\s*cr[eé]d(?:ito|lto|1to)|notade\s+cr[eé]dito|credit\s+note)\b",
    re.IGNORECASE,
)
_ND_HEAD = re.compile(
    r"^\s*(?:n[o0]ta\s*de\s*d[eé]bito|notade\s+d[eé]bito|debit\s+note)\b",
    re.IGNORECASE,
)
# "será emitida" is a promise of a later note, not this document's title.
_FUTURE_MENTION = re.compile(r"\bemitid", re.IGNORECASE)
_CREDIT_DEBIT_SIGNAL = re.compile(
    r"n[o0]ta\s*de\s*cr[eé]d(?:ito|lto|1to)|"
    r"n[o0]ta\s*de\s*d[eé]bito|"
    r"notade\s+cr[eé]dito|"
    r"notade\s+d[eé]bito|"
    r"credit\s+note|"
    r"debit\s+note|"
    r"\bcr[eé]dlto\b|"
    r"a\s+creditar|"
    r"a\s+debitar|"
    r"retificativa|"
    r"rectificativa|"
    r"anula",
    re.IGNORECASE,
)
# "NC/A/5", "NC A/5", "NC 2026A5", "Nº: NC 5". A quantity such as "NC 3m" is not one.
_NC_SERIES = re.compile(
    r"(?<![A-Za-z])(?P<series>NC|ND)\s*[/: ]\s*(?P<number>[A-Z0-9][A-Z0-9/.\-]{0,30})",
    re.IGNORECASE,
)
_REF_PAREN = re.compile(r"\([^)]*\bref\.?[^)]*\)", re.IGNORECASE)
# "ref FT B/99" without parentheses. Stops before "n.º FT A/12".
_INLINE_REF = re.compile(
    r"\bref\.?\s+(?:FT|FR|FS|NC|ND)\b(?:\s*/?\s*[A-Z0-9][A-Z0-9/.\-]{0,30})?",
    re.IGNORECASE,
)
_PURCHASE_LINE = re.compile(
    r"^\s*(?:fatura|factura|invoice|recibo)\b",
    re.IGNORECASE,
)
_NUMBER_INTRO = re.compile(r"n[º°.]|n[úu]mero\s*$", re.IGNORECASE)
DISCOUNT = re.compile(r"\b(?:desconto|discount|abatimento)\b", re.IGNORECASE)
# Series codes stay on the number ("FT A/12"). Words such as Invoice do not.
_SERIES_CODES = {"FT", "FR", "FS", "NC", "ND"}
INVOICE_NO = re.compile(
    r"(?<![A-Za-z])(?P<series>FT|FR|FS|NC|ND|Fatura|Factura|Recibo|Invoice)"
    r"[:\s#º°]+(?=\S*\d)(?P<number>[A-Z0-9][A-Z0-9/.\-]{1,30})",
    re.IGNORECASE,
)
# A hyphen glued to a label ("Total-12,30", "IVA 23%-2,30") is not a minus.
# A minus is a sign when whitespace (or the start of the line) precedes it.
MONEY = re.compile(
    r"(?<![\d.,])(?P<open>\()?(?P<prefix>[-−])?"
    r"(?P<amount>\d{1,3}(?:[.\s]\d{3})*(?:,\s*\d{2})|\d+,\s*\d{2}|\d+\.\d{2})"
    r"(?P<suffix>[-−])?(?P<close>\))?(?!\d)"
)
_PT_MONTHS = {
    "janeiro": 1, "jan": 1,
    "fevereiro": 2, "fev": 2,
    "marco": 3, "mar": 3,
    "abril": 4, "abr": 4,
    "maio": 5, "mai": 5,
    "junho": 6, "jun": 6,
    "julho": 7, "jul": 7,
    "agosto": 8, "ago": 8,
    "setembro": 9, "set": 9,
    "outubro": 10, "out": 10,
    "novembro": 11, "nov": 11,
    "dezembro": 12, "dez": 12,
}
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
    # Confirmed type. OCR never sets this; only an AT QR of FT/FS/FR/NC/ND does.
    document_type: Optional[str] = None
    # Prefill only. Netting and confirmation ignore both.
    suggested_type: Optional[str] = None
    suggested_invoice_number: Optional[str] = None
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
    """Parse a PT/EU money string, including a trailing minus and parentheses."""
    if not raw:
        return None
    cleaned = raw.strip().replace(" ", "").replace("€", "").replace("EUR", "")
    sign = 1
    if cleaned.startswith("(") and cleaned.endswith(")"):
        sign = -1
        cleaned = cleaned[1:-1]
    if cleaned.endswith("-") or cleaned.endswith("−"):
        sign = -1
        cleaned = cleaned[:-1]
    if cleaned[:1] in "+-−":
        if cleaned[0] in "-−":
            sign = -1
        cleaned = cleaned[1:]
    cleaned = _normalise_separators(cleaned)
    try:
        value = Decimal(cleaned) * sign
    except InvalidOperation:
        return None
    if abs(value) > Decimal("1000000"):
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


def _is_origin_line(line: str) -> bool:
    return bool(_ORIGIN_LINE.match(line or ""))


def _clear_title_type(line: str) -> Optional[str]:
    """A suggestion, and only when the heading itself is unambiguous."""
    if re.match(r"^\s*fatura\s+simplificada\b", line, re.IGNORECASE):
        return "FS"
    if re.match(r"^\s*fatura\s*/\s*recibo\b|^\s*fatura[\s-]+recibo\b", line, re.IGNORECASE):
        return "FR"
    if _NOTA_TITLE.match(line) and re.search(r"cr[eé]dito", line, re.IGNORECASE):
        return "NC"
    if _NOTA_TITLE.match(line) and re.search(r"d[eé]bito", line, re.IGNORECASE):
        return "ND"
    if re.match(r"^\s*fatura\b", line, re.IGNORECASE) and not re.search(
        r"retificativa|rectificativa|anula|origem",
        line,
        re.IGNORECASE,
    ):
        return "FT"
    return None


def _heading_kind(line: str) -> Optional[tuple[str, str]]:
    """(NC or ND, text after the heading) when the line opens with that heading."""
    for kind, pattern in (("ND", _ND_HEAD), ("NC", _NC_HEAD)):
        match = pattern.match(line)
        if match:
            return kind, line[match.end() :]
    return None


def _remainder_is_qualifier(rest: str) -> bool:
    """Prose after the heading, with no document id. 'só mediante devolução' is one."""
    if re.search(r"\d", rest):
        return False
    return bool(re.search(r"[A-Za-zÀ-ÿ]", rest))


def _nota_kind(line: str) -> Optional[str]:
    """NC or ND when this line is the document's own credit or debit title.

    A heading followed only by prose is a qualifier, not a title. A sentence
    such as 'é uma nota de crédito' is a veto, not a title.
    """
    if not line or _is_origin_line(line) or _FUTURE_MENTION.search(line):
        return None
    heading = _heading_kind(line)
    if heading is None:
        return None
    kind, rest = heading
    if _remainder_is_qualifier(rest):
        return None
    return kind


def _find_nota(lines: list[str]) -> Optional[tuple[str, str]]:
    """(kind, title text). A wrapped 'Nota de' / 'crédito …' is one title."""
    for line in lines:
        kind = _nota_kind(line)
        if kind:
            return kind, line
    for index in range(len(lines) - 1):
        if _is_origin_line(lines[index]):
            continue
        if re.match(r"^\s*n[o0]ta\s+de\s*$", lines[index], re.IGNORECASE):
            combined = f"{lines[index]} {lines[index + 1]}"
            kind = _nota_kind(combined)
            if kind:
                return kind, combined
    return None


def _line_has_credit_series(line: str) -> bool:
    """An NC/ND document id. 'Cabo NC 3m' and 'Plano nc 2026' are not one."""
    for match in _NC_SERIES.finditer(line or ""):
        number = match.group("number")
        if re.fullmatch(r"\d{1,3}[A-Za-z]{1,3}", number):
            continue
        if re.fullmatch(r"20\d{2}", number):
            continue
        if "/" in number or "/" in match.group(0) or re.search(r"\d", number):
            return True
    return False


def _printed_negative_total(lines: list[str]) -> bool:
    """A trailing minus or parentheses on the total. A glued hyphen is not one."""
    for line in lines:
        if DISCOUNT.search(line) and not STRONG_TOTAL.search(line):
            continue
        if not STRONG_TOTAL.search(line) and not PAYMENT_TOTAL.search(line):
            continue
        usable = _amount_line(line, STRONG_TOTAL if STRONG_TOTAL.search(line) else PAYMENT_TOTAL)
        for match in MONEY.finditer(usable):
            amount = _amount_from_match(usable, match)
            if amount is not None and amount < 0:
                return True
    return False


def _page_vetoes_purchase(text: str, lines: list[str]) -> bool:
    if _CREDIT_DEBIT_SIGNAL.search(text or ""):
        return True
    if _printed_negative_total(lines):
        return True
    return any(_line_has_credit_series(line) for line in lines)


def _is_purchase_line(line: str) -> bool:
    return bool(_PURCHASE_LINE.match(line or ""))


def _purchase_series(number: Optional[str]) -> bool:
    return bool(number and re.match(r"^(?:FT|FR|FS)\b", number.strip(), re.IGNORECASE))


def _series_number(line: str, *, allow_credit: bool, allow_purchase: bool) -> Optional[str]:
    """A series number on this line. A citation, a ref, and an origin line do not count."""
    if not line or _is_origin_line(line):
        return None
    cleaned = _INLINE_REF.sub(" ", _REF_PAREN.sub(" ", line))
    nota = _nota_kind(line) is not None
    kept: list[re.Match[str]] = []
    for match in INVOICE_NO.finditer(cleaned):
        series = match.group("series").upper()
        number = match.group("number")
        if series in {"NC", "ND"} and not allow_credit:
            continue
        if series in {"NC", "ND"} and "/" not in number and not nota:
            continue
        formatted = _invoice_number_from_match(match)
        if not allow_credit and re.match(r"^(?:NC|ND)\b", formatted, re.IGNORECASE):
            continue
        if not allow_purchase and _purchase_series(formatted):
            continue
        if series in {"FT", "FR", "FS"} and not allow_purchase:
            continue
        del number
        kept.append(match)
    if not kept:
        return None
    introduced = [
        match
        for match in kept
        if _NUMBER_INTRO.search(cleaned[max(0, match.start() - 20) : match.start()])
    ]
    chosen = introduced[-1] if introduced else min(kept, key=lambda match: match.start())
    formatted = _invoice_number_from_match(chosen)
    if not allow_purchase and _purchase_series(formatted):
        return None
    if not allow_credit and re.match(r"^(?:NC|ND)\b", formatted, re.IGNORECASE):
        return None
    return formatted


def _suggestions(text: str) -> tuple[Optional[str], Optional[str]]:
    """Type and number hints. A credit signal never yields FT, FS or FR.

    The number comes only from the same line as the title that produced the
    type. The line under that title is not used. In doubt the number is blank,
    and a credit note never keeps an FT-series number. A qualifier plus a
    purchase title suggests nothing.
    """
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    nota = _find_nota(lines)
    if nota is not None:
        kind, title = nota
        number = _series_number(title, allow_credit=True, allow_purchase=False)
        if _purchase_series(number):
            number = None
        return kind, number

    if _page_vetoes_purchase(text, lines):
        has_purchase = any(
            _is_purchase_line(line) and not _is_origin_line(line) and _clear_title_type(line)
            for line in lines
        )
        if not has_purchase:
            for line in lines:
                if _is_origin_line(line) or _is_purchase_line(line):
                    continue
                if re.match(r"^\s*(?:NC|ND)\b", line, re.IGNORECASE):
                    number = _series_number(line, allow_credit=True, allow_purchase=False)
                    if number and not _purchase_series(number):
                        return None, number
        return None, None

    title: Optional[str] = None
    for line in lines:
        if _is_origin_line(line):
            continue
        if _TITLE_HEAD.match(line) or _NUMBER_HEAD.match(line):
            title = line
            break
    if title is None:
        return None, None
    suggested = _clear_title_type(title)
    title_is_credit_number = bool(re.match(r"^\s*(?:NC|ND)\b", title, re.IGNORECASE))
    allow_credit = suggested in {"NC", "ND"} or title_is_credit_number
    number = _series_number(title, allow_credit=allow_credit, allow_purchase=True)
    if suggested in {"NC", "ND"} and _purchase_series(number):
        number = None
    return suggested, number


def _amount_from_match(line: str, match: re.Match[str], *, credit: bool = False) -> Optional[Decimal]:
    """A minus counts only when whitespace (or the start of the line) precedes it.

    A hyphen glued to a label is never a minus, including on a credit note.
    `credit` is ignored. The document type, not the glyph, carries the sign.
    """
    del credit
    value = parse_pt_amount(match.group("amount"))
    if value is None:
        return None
    value = abs(value)
    if match.group("open") and match.group("close"):
        return -value
    if match.group("suffix"):
        return -value
    prefix = match.group("prefix") or ""
    if not prefix:
        return value
    before = line[: match.start("prefix")]
    if before == "" or before[-1].isspace():
        return -value
    return value


def _money_amounts(line: str, *, credit: bool = False) -> list[Decimal]:
    """Money tokens on one line. A number followed by % is a rate, not an amount."""
    amounts: list[Decimal] = []
    for match in MONEY.finditer(line):
        if line[match.end() :].lstrip().startswith("%"):
            continue
        amount = _amount_from_match(line, match, credit=credit)
        if amount is not None and amount != 0:
            amounts.append(amount)
    return amounts


def _amount_line(line: str, label: re.Pattern[str]) -> str:
    """Drop a discount that follows the labelled total. A discount line is not a total."""
    if DISCOUNT.search(line) and not label.search(line):
        return ""
    discount = DISCOUNT.search(line)
    labeled = label.search(line)
    if discount and labeled and discount.start() > labeled.start():
        return line[: discount.start()]
    return line


def _last_labeled_amount(
    lines: list[str], label: re.Pattern[str], *, credit: bool = False
) -> Optional[Decimal]:
    found: Optional[Decimal] = None
    for line in lines:
        if SKIP_TOTAL_LINE.search(line):
            continue
        if not label.search(line):
            continue
        amounts = _money_amounts(_amount_line(line, label), credit=credit)
        if amounts:
            found = amounts[-1]
    return found


def _largest_labeled_amount(
    lines: list[str], label: re.Pattern[str], *, credit: bool = False
) -> Optional[Decimal]:
    found: list[Decimal] = []
    for line in lines:
        if SKIP_TOTAL_LINE.search(line):
            continue
        if not label.search(line):
            continue
        amounts = _money_amounts(line, credit=credit)
        if amounts:
            found.append(amounts[-1])
    return max(found) if found else None


def _extract_vat(
    lines: list[str], *, credit: bool = False
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
        amounts = _money_amounts(line, credit=credit)
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


def _fold_letters(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value)
    return "".join(char for char in decomposed if unicodedata.category(char) != "Mn").lower()


def _invoice_number_from_match(match: re.Match[str]) -> str:
    series = match.group("series").upper()
    number = match.group("number").strip()
    # "FT FT2026/1" already carries the series. Do not write "FT FT2026/1".
    if series in _SERIES_CODES and not number.upper().startswith(series):
        return f"{series} {number}"[:100]
    return number[:100]


def _month_number(token: str) -> Optional[int]:
    return _PT_MONTHS.get(_fold_letters(token).rstrip("."))


def _date_spans(line: str) -> list[tuple[int, int, date]]:
    found: list[tuple[int, int, date]] = []

    def add(start: int, end: int, parsed: Optional[date]) -> None:
        if parsed is None:
            return
        for old_start, old_end, _old in found:
            if start < old_end and end > old_start:
                return
        found.append((start, end, parsed))

    for match in DATE_PT_TEXT.finditer(line):
        month = _month_number(match.group(2))
        parsed = _safe_date(int(match.group(3)), month, int(match.group(1))) if month else None
        add(match.start(), match.end(), parsed)
    for match in DATE_PT_ABBR.finditer(line):
        month = _month_number(match.group(2))
        parsed = _safe_date(int(match.group(3)), month, int(match.group(1))) if month else None
        add(match.start(), match.end(), parsed)
    for match in DATE_YMD.finditer(line):
        year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
        add(match.start(), match.end(), _safe_date(year, month, day))
    for match in DATE_DMY.finditer(line):
        if match.group(3).__len__() == 2 and DATE_BROKEN_YEAR.match(line, match.start()):
            continue
        first, second, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
        if year < 100:
            year += 2000
        add(match.start(), match.end(), _safe_date(year, second, first) or _safe_date(year, first, second))
    for match in DATE_BROKEN_YEAR.finditer(line):
        first, second = int(match.group(1)), int(match.group(2))
        year = int(match.group(3) + match.group(4))
        add(match.start(), match.end(), _safe_date(year, second, first) or _safe_date(year, first, second))
    return found


def _dates_on_line(line: str) -> list[tuple[str, date]]:
    """Each date takes the label written just before it, so one line can hold both."""
    spans = _date_spans(line)
    classified: list[tuple[str, date]] = []
    cursor = 0
    letterhead = bool(_LETTERHEAD.match(line.strip()))
    for start, end, parsed in spans:
        prefix = line[cursor:start]
        if _DUE_LABEL.search(prefix):
            kind = "due"
        elif _ISSUE_LABEL.search(prefix):
            kind = "issue"
        elif letterhead:
            kind = "letterhead"
        else:
            kind = "other"
        classified.append((kind, parsed))
        cursor = end
    return classified


def _choose_date(text: str) -> tuple[Optional[date], bool]:
    """Issue label wins over a due date or a letterhead date.

    Two different issue dates, or two different unlabelled dates, are ambiguous.
    """
    buckets: dict[str, list[date]] = {"issue": [], "other": [], "letterhead": []}
    for raw in text.splitlines() or [text]:
        line = raw.strip()
        if not line:
            continue
        for kind, parsed in _dates_on_line(line):
            if kind == "due":
                continue
            buckets[kind].append(parsed)
    for kind in ("issue", "other", "letterhead"):
        unique: list[date] = []
        for item in buckets[kind]:
            if item not in unique:
                unique.append(item)
        if unique:
            return unique[0], len(unique) > 1
    return None, False


def _parse_date(text: str) -> Optional[date]:
    chosen, _ambiguous = _choose_date(text)
    return chosen


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
    credit = False
    result.vendor_name = _guess_vendor(lines)
    result.vendor_nif = extract_portuguese_nif(text)
    result.document_date, ambiguous_date = _choose_date(text)

    suggested_type, suggested_number = _suggestions(text)
    result.invoice_number = None
    result.document_type = "unclassified"
    result.suggested_type = suggested_type
    result.suggested_invoice_number = suggested_number

    vat_rate, vat_amount, vat_net, breakdown = _extract_vat(lines, credit=credit)
    result.vat_rate = vat_rate
    result.vat_amount = vat_amount
    result.net_amount = vat_net
    mixed_rates = len(breakdown) > 1
    if mixed_rates:
        result.vat_breakdown = [
            {key: str(value) for key, value in entry.items()} for entry in breakdown
        ]

    result.gross_amount = _last_labeled_amount(lines, STRONG_TOTAL, credit=credit)
    if result.gross_amount is None:
        result.gross_amount = _largest_labeled_amount(lines, PAYMENT_TOTAL, credit=credit)

    net_match = None if mixed_rates else NET_LINE.search(text)
    if net_match:
        labeled_net = parse_pt_amount(net_match.group(1))
        if labeled_net is not None:
            result.net_amount = labeled_net

    # Amounts are stored non-negative. A printed minus, a trailing minus, or
    # parentheses are an uncertain sign. They never set the document type.
    printed_minus = any(
        value is not None and value < 0
        for value in (result.gross_amount, result.net_amount, result.vat_amount)
    )
    for field in ("gross_amount", "net_amount", "vat_amount"):
        value = getattr(result, field)
        if value is not None:
            setattr(result, field, abs(value))

    if result.gross_amount is not None and result.vat_amount is not None and result.net_amount is None:
        result.net_amount = (result.gross_amount - result.vat_amount).quantize(Decimal("0.01"))
    if result.gross_amount is not None and result.net_amount is not None and result.vat_amount is None:
        vat = (result.gross_amount - result.net_amount).quantize(Decimal("0.01"))
        if result.gross_amount < 0 or vat >= 0:
            result.vat_amount = vat

    if (
        result.net_amount
        and result.vat_amount
        and result.vat_rate is None
        and not mixed_rates
        and abs(result.net_amount) > 0
    ):
        guessed = (abs(result.vat_amount) / abs(result.net_amount) * 100).quantize(Decimal("0.01"))
        result.vat_rate = _nearest_vat_rate(guessed) or guessed

    amounts_conflict = (
        result.net_amount is not None
        and result.vat_amount is not None
        and result.gross_amount is not None
        and abs(result.net_amount + result.vat_amount - result.gross_amount) > Decimal("0.01")
    )

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
    # No AT QR on this path, so the row always waits for a person.
    result.needs_review = True
    del ambiguous_date, printed_minus, amounts_conflict, filled
    return result


def extracted_to_json(fields: ExtractedFields, extra: Optional[dict] = None) -> str:
    payload = {"extractor": "oss-pt", "fields": fields.to_raw_dict()}
    if extra:
        payload.update(extra)
    return json.dumps(payload, ensure_ascii=False)

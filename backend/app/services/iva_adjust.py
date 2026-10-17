from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

_ZERO = Decimal("0.00")
_CENT = Decimal("0.01")
_CONFIRMED = ("ready", "accountant_review")


@dataclass(frozen=True)
class FiscalMark:
    document_type: Optional[str]
    fiscal_status: Optional[str]
    file_sha256: Optional[str]


@dataclass
class Counted:
    document: object
    net: Decimal
    vat: Decimal
    gross: Decimal


def _money(value) -> Decimal:
    if value is None:
        return _ZERO
    amount = Decimal(value)
    if amount < 0:
        return _ZERO
    return amount.quantize(_CENT)


def _code(value) -> Optional[str]:
    if not isinstance(value, str):
        return None
    text = value.strip().upper()
    return text or None


def fiscal_mark(document) -> FiscalMark:
    raw = getattr(document, "ocr_raw_response", None)
    if not raw:
        return FiscalMark(None, None, None)
    try:
        payload = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return FiscalMark(None, None, None)
    if not isinstance(payload, dict):
        return FiscalMark(None, None, None)
    qr = payload.get("qr")
    if not isinstance(qr, dict):
        qr = {}
    digest = payload.get("file_sha256")
    return FiscalMark(
        document_type=_code(qr.get("document_type")),
        fiscal_status=_code(qr.get("fiscal_status")),
        file_sha256=digest if isinstance(digest, str) and digest else None,
    )


def reading_is_fictional(raw: Optional[str]) -> bool:
    if not raw:
        return False
    try:
        payload = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return False
    if not isinstance(payload, dict):
        return False
    return bool(payload.get("mock")) or payload.get("backend") == "mock"


def _bucket(document) -> Optional[str]:
    status = getattr(document, "status", None)
    if status in _CONFIRMED:
        return "confirmed"
    if status == "needs_review":
        return "pending"
    return None


def _when(document):
    created = getattr(document, "created_at", None) or datetime.min
    issued = getattr(document, "document_date", None) or date.min
    return (issued, created, str(getattr(document, "id", "")))


# The QR does not carry the credited invoice number, so a purchase with the
# same supplier NIF is the link a person can actually see.
ORPHAN_CREDIT_WARNING = "nota de crédito sem fatura associada"
OTHER_PERIOD_CREDIT_WARNING = "nota de crédito referente a uma fatura de outro período"


def _nif(document) -> str:
    return (getattr(document, "vendor_nif", None) or "").strip()


def _prefer(candidate, incumbent) -> bool:
    """Reviewed copy wins. Otherwise the newer file wins."""
    candidate_confirmed = _bucket(candidate) == "confirmed"
    incumbent_confirmed = _bucket(incumbent) == "confirmed"
    if candidate_confirmed != incumbent_confirmed:
        return candidate_confirmed
    candidate_created = getattr(candidate, "created_at", None) or datetime.min
    incumbent_created = getattr(incumbent, "created_at", None) or datetime.min
    if candidate_created != incumbent_created:
        return candidate_created > incumbent_created
    return str(getattr(candidate, "id", "")) > str(getattr(incumbent, "id", ""))


def _signed(document, mark: FiscalMark) -> Counted:
    sign = -1 if mark.document_type == "NC" else 1
    return Counted(
        document=document,
        net=(_money(document.net_amount) * sign).quantize(_CENT),
        vat=(_money(document.vat_amount) * sign).quantize(_CENT),
        gross=(_money(document.gross_amount) * sign).quantize(_CENT),
    )


def contributions(documents) -> list[Counted]:
    """One row per counted document.

    Purchases stay positive. A credit note is its own row for the full
    amount, negative, including the part above the invoice it refers to.
    A cancelled invoice is left out. The same file counts once: the reviewed
    copy beats an unreviewed copy, and the newer copy beats an older one.
    """
    marked = [(document, fiscal_mark(document)) for document in documents if _bucket(document)]
    chosen: dict[str, tuple] = {}
    loose: list[tuple] = []
    for document, mark in marked:
        if mark.fiscal_status == "A":
            continue
        digest = mark.file_sha256
        if not digest:
            loose.append((document, mark))
            continue
        current = chosen.get(digest)
        if current is None or _prefer(document, current[0]):
            chosen[digest] = (document, mark)
    rows = [_signed(document, mark) for document, mark in list(chosen.values()) + loose]
    rows.sort(key=lambda row: _when(row.document))
    return rows


def _is_purchase(document) -> bool:
    if not _bucket(document):
        return False
    mark = fiscal_mark(document)
    return mark.fiscal_status != "A" and mark.document_type != "NC" and bool(_nif(document))


def credit_note_warnings(period_documents, library) -> list[str]:
    """Warn when a counted credit note has no purchase from that supplier in the period."""
    period_ids = {getattr(document, "id", None) for document in period_documents}
    period_ids.discard(None)
    period_tokens = {id(document) for document in period_documents}
    combined = {}
    for document in list(library) + list(period_documents):
        combined[getattr(document, "id", None) or id(document)] = document

    in_period: set[str] = set()
    anywhere: set[str] = set()
    for document in combined.values():
        if not _is_purchase(document):
            continue
        nif = _nif(document)
        anywhere.add(nif)
        ident = getattr(document, "id", None)
        if id(document) in period_tokens or (ident is not None and ident in period_ids):
            in_period.add(nif)

    warnings: list[str] = []
    for row in contributions(period_documents):
        if fiscal_mark(row.document).document_type != "NC":
            continue
        nif = _nif(row.document)
        if nif and nif in in_period:
            continue
        warnings.append(OTHER_PERIOD_CREDIT_WARNING if nif and nif in anywhere else ORPHAN_CREDIT_WARNING)
    return warnings

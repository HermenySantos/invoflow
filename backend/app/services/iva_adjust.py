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


def _same_invoice(purchase, credit) -> bool:
    if not purchase.vendor_nif or purchase.vendor_nif != credit.vendor_nif:
        return False
    left = (purchase.invoice_number or "").strip().lower()
    right = (credit.invoice_number or "").strip().lower()
    return bool(left) and left == right


def _same_supplier(purchase, credit) -> bool:
    return bool(purchase.vendor_nif and credit.vendor_nif and purchase.vendor_nif == credit.vendor_nif)


def contributions(documents) -> list[Counted]:
    marked = [(document, fiscal_mark(document)) for document in documents if _bucket(document)]
    purchases: list = []
    credits: list[tuple] = []
    seen_hash: set[str] = set()
    for document, mark in sorted(marked, key=lambda item: _when(item[0])):
        if mark.fiscal_status == "A":
            continue
        if mark.document_type == "NC":
            credits.append((document, mark))
            continue
        if mark.file_sha256:
            if mark.file_sha256 in seen_hash:
                continue
            seen_hash.add(mark.file_sha256)
        purchases.append(document)

    counted = {
        id(document): Counted(
            document=document,
            net=_money(document.net_amount),
            vat=_money(document.vat_amount),
            gross=_money(document.gross_amount),
        )
        for document in purchases
    }

    for credit, _mark in credits:
        bucket = _bucket(credit)
        linked = [
            document
            for document in purchases
            if _bucket(document) == bucket and _same_invoice(document, credit)
        ]
        targets = linked or [
            document
            for document in purchases
            if _bucket(document) == bucket and _same_supplier(document, credit)
        ]
        remaining_net = _money(credit.net_amount)
        remaining_vat = _money(credit.vat_amount)
        remaining_gross = _money(credit.gross_amount)
        for document in targets:
            row = counted[id(document)]
            take_net = min(row.net, remaining_net)
            take_vat = min(row.vat, remaining_vat)
            take_gross = min(row.gross, remaining_gross)
            row.net = (row.net - take_net).quantize(_CENT)
            row.vat = (row.vat - take_vat).quantize(_CENT)
            row.gross = (row.gross - take_gross).quantize(_CENT)
            remaining_net -= take_net
            remaining_vat -= take_vat
            remaining_gross -= take_gross
    return list(counted.values())

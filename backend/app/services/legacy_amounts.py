"""Repair rows from earlier draft heads.

Negatives become absolute values. The type comes from the stored AT QR
when there is one. A negative with no QR type becomes ``unclassified``
and goes back to review. A positive row keeps its QR type, or FT.
The sign is never inferred from the minus. A backup in the raw JSON
lets downgrade restore the amounts and the status.
"""

import json
from decimal import Decimal

from sqlalchemy import text

_CONCRETE = {"FT", "FR", "FS", "ND", "NC"}
_BACKUP = "_amount_sign_backup"

_SELECT = text(
    """
    SELECT id, net_amount, vat_amount, gross_amount, status, document_type, ocr_raw_response
    FROM documents
    """
)
_UPDATE = text(
    """
    UPDATE documents
    SET net_amount = :net_amount,
        vat_amount = :vat_amount,
        gross_amount = :gross_amount,
        status = :status,
        document_type = :document_type,
        ocr_raw_response = :ocr_raw_response
    WHERE id = :id
    """
)


def _money(value):
    if value is None:
        return None
    return Decimal(str(value))


def _payload(raw):
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _qr_type(payload: dict) -> str | None:
    qr = payload.get("qr")
    if not isinstance(qr, dict):
        return None
    code = str(qr.get("document_type") or "").strip().upper()
    return code if code in _CONCRETE else None


def _dump(payload: dict) -> str | None:
    if not payload:
        return None
    return json.dumps(payload, ensure_ascii=False)


def repair_legacy_negative_amounts(connection) -> None:
    rows = connection.execute(_SELECT).mappings().all()
    for row in rows:
        payload = _payload(row["ocr_raw_response"])
        if _BACKUP in payload:
            continue
        net, vat, gross = _money(row["net_amount"]), _money(row["vat_amount"]), _money(row["gross_amount"])
        negative = any(amount is not None and amount < 0 for amount in (net, vat, gross))
        qr_type = _qr_type(payload)
        current = (row["document_type"] or "").strip()
        if negative:
            backup = {
                "net": None if net is None else format(net, "f"),
                "vat": None if vat is None else format(vat, "f"),
                "gross": None if gross is None else format(gross, "f"),
                "status": row["status"],
            }
            payload[_BACKUP] = backup
            connection.execute(
                _UPDATE,
                {
                    "id": row["id"],
                    "net_amount": None if net is None else format(abs(net), "f"),
                    "vat_amount": None if vat is None else format(abs(vat), "f"),
                    "gross_amount": None if gross is None else format(abs(gross), "f"),
                    "status": row["status"] if qr_type else "needs_review",
                    "document_type": qr_type or "unclassified",
                    "ocr_raw_response": _dump(payload),
                },
            )
            continue
        if current:
            continue
        connection.execute(
            _UPDATE,
            {
                "id": row["id"],
                "net_amount": None if net is None else format(net, "f"),
                "vat_amount": None if vat is None else format(vat, "f"),
                "gross_amount": None if gross is None else format(gross, "f"),
                "status": row["status"],
                "document_type": qr_type or "FT",
                "ocr_raw_response": row["ocr_raw_response"],
            },
        )


def restore_legacy_negative_amounts(connection) -> None:
    rows = connection.execute(_SELECT).mappings().all()
    for row in rows:
        payload = _payload(row["ocr_raw_response"])
        backup = payload.get(_BACKUP)
        if not isinstance(backup, dict):
            continue
        payload.pop(_BACKUP, None)
        connection.execute(
            _UPDATE,
            {
                "id": row["id"],
                "net_amount": backup.get("net"),
                "vat_amount": backup.get("vat"),
                "gross_amount": backup.get("gross"),
                "status": backup.get("status") or row["status"],
                "document_type": None,
                "ocr_raw_response": _dump(payload),
            },
        )

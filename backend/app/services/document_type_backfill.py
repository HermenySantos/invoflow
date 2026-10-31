"""Migration 009 data repair.

Widen happens in the revision, before this runs. A stored AT QR type of
FT, FS, FR, NC or ND is written onto the column. Every other row becomes
unclassified. A ready or accountant_review row without one of those QR
types goes back to needs_review. Nothing is deployed, so that reset only
touches dev data. The previous type and status are kept under
``_type_backup`` so downgrade can put them back.

A missing raw value is written as that backup object and restored to empty.
A non-JSON string and a JSON value that is not an object are left
byte-for-byte alone, so there is no backup for them and downgrade keeps
the upgraded type. A database whose 008 came from the unmerged 2f8c720
revision has no ``_amount_sign_backup``; downgrading that lineage through
008 to 007 cannot restore the original minuses. That revision was never
merged, so only dev databases are affected. This module does not change 008.
"""

from __future__ import annotations

import json

from sqlalchemy import text

_CONCRETE = {"FT", "FS", "FR", "NC", "ND"}
_BACKUP = "_type_backup"
_CONFIRMED = {"ready", "accountant_review"}

_SELECT = text(
    """
    SELECT id, document_type, status, ocr_raw_response
    FROM documents
    """
)
_UPDATE = text(
    """
    UPDATE documents
    SET document_type = :document_type,
        status = :status,
        at_document_type = :at_document_type,
        ocr_raw_response = :ocr_raw_response
    WHERE id = :id
    """
)
_UPDATE_KEEP_RAW = text(
    """
    UPDATE documents
    SET document_type = :document_type,
        status = :status,
        at_document_type = :at_document_type
    WHERE id = :id
    """
)


def _payload(raw):
    """A JSON object to edit, ``{}`` for a missing raw value, or None to leave it.

    None means the raw text is not a JSON object. Callers must not write it
    back. An empty raw value can hold ``_type_backup`` and is restored to empty.
    """
    if raw is None:
        return {}
    if isinstance(raw, str) and not raw.strip():
        return {}
    if not isinstance(raw, str):
        return None
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def _dump(payload: dict) -> str | None:
    if not payload:
        return None
    return json.dumps(payload, ensure_ascii=False)


def _qr_code(payload: dict) -> str | None:
    """Raw AT type stored on the row, including codes we do not confirm."""
    qr = payload.get("qr")
    if isinstance(qr, dict):
        code = str(qr.get("document_type") or qr.get("at_document_type") or "").strip().upper()
        if code:
            return code
    code = str(payload.get("at_document_type") or "").strip().upper()
    return code or None


def backfill_document_types(connection) -> None:
    rows = connection.execute(_SELECT).mappings().all()
    for row in rows:
        payload = _payload(row["ocr_raw_response"])
        previous_status = row["status"]
        if payload is None:
            new_status = "needs_review" if previous_status in _CONFIRMED else previous_status
            connection.execute(
                _UPDATE_KEEP_RAW,
                {
                    "id": row["id"],
                    "document_type": "unclassified",
                    "status": new_status,
                    "at_document_type": None,
                },
            )
            continue
        if isinstance(payload.get(_BACKUP), dict):
            continue
        previous_type = row["document_type"]
        payload[_BACKUP] = {"document_type": previous_type, "status": previous_status}
        qr = _qr_code(payload)
        if qr in _CONCRETE:
            new_type = qr
            new_status = previous_status
        else:
            new_type = "unclassified"
            new_status = "needs_review" if previous_status in _CONFIRMED else previous_status
        connection.execute(
            _UPDATE,
            {
                "id": row["id"],
                "document_type": new_type,
                "status": new_status,
                "at_document_type": qr,
                "ocr_raw_response": _dump(payload),
            },
        )


def restore_document_types(connection) -> None:
    rows = connection.execute(_SELECT).mappings().all()
    for row in rows:
        payload = _payload(row["ocr_raw_response"])
        if payload is None:
            continue
        backup = payload.get(_BACKUP)
        if not isinstance(backup, dict):
            continue
        payload.pop(_BACKUP, None)
        connection.execute(
            _UPDATE,
            {
                "id": row["id"],
                "document_type": backup.get("document_type"),
                "status": backup.get("status") or row["status"],
                "at_document_type": None,
                "ocr_raw_response": _dump(payload),
            },
        )

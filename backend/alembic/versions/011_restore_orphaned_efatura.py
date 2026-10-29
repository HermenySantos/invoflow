"""Restore e-Fatura invoices whose linked scan was already deleted

Revision ID: 011_restore_orphaned_efatura
Revises: 010_series_mismatch_accepted
Create Date: 2026-10-29

A link that still points at a soft-deleted scan drops that AT invoice from
the totals. This stores one normal AT document per invoice (nif, type and
number) and points every link for that invoice at it. A doc-key link and an
ATCUD link for the same invoice share that row. The scan stays deleted.

A deleted e-Fatura document stays deleted. This revision does not recreate it.
It does not add columns. The identity column and its unique index are migration
012, so a database that already applied this revision id is not asked to add
them again.

The table shapes below are frozen. This file does not import the live models.

Downgrade does not remove restored rows. Running upgrade again changes nothing.

The identity string drops spaces and NBSP, a leading PT on the NIF, and leading
zeros in a digit run. It must match at_invoice_identity().

"""
from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from alembic import op


revision = "011_restore_orphaned_efatura"
down_revision = "010_series_mismatch_accepted"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.runtime.migration")

_CONFIRMED = {"ready", "accountant_review"}
_CONCRETE = {"FT", "FS", "FR", "NC", "ND"}

documents = sa.table(
    "documents",
    sa.column("id", sa.String),
    sa.column("user_id", sa.String),
    sa.column("status", sa.String),
    sa.column("storage_key", sa.String),
    sa.column("original_filename", sa.String),
    sa.column("mime_type", sa.String),
    sa.column("vendor_name", sa.String),
    sa.column("vendor_nif", sa.String),
    sa.column("invoice_number", sa.String),
    sa.column("document_type", sa.String),
    sa.column("at_document_type", sa.String),
    sa.column("document_date", sa.Date),
    sa.column("net_amount", sa.Numeric),
    sa.column("vat_amount", sa.Numeric),
    sa.column("gross_amount", sa.Numeric),
    sa.column("vat_rate", sa.Numeric),
    sa.column("ocr_raw_response", sa.Text),
    sa.column("expense_category", sa.String),
    sa.column("irs_sector", sa.String),
    sa.column("deductible_pct_override", sa.Integer),
    sa.column("series_mismatch_accepted", sa.Boolean),
    sa.column("deleted_at", sa.DateTime),
    sa.column("created_at", sa.DateTime),
    sa.column("updated_at", sa.DateTime),
)

links = sa.table(
    "efatura_links",
    sa.column("id", sa.String),
    sa.column("user_id", sa.String),
    sa.column("source_key", sa.String),
    sa.column("role", sa.String),
    sa.column("outcome", sa.String),
    sa.column("document_id", sa.String),
    sa.column("warning", sa.Text),
    sa.column("payload_json", sa.Text),
    sa.column("updated_at", sa.DateTime),
)

audits = sa.table(
    "audit_logs",
    sa.column("id", sa.String),
    sa.column("entity_type", sa.String),
    sa.column("entity_id", sa.String),
    sa.column("user_id", sa.String),
    sa.column("action", sa.String),
    sa.column("source", sa.String),
    sa.column("changes_json", sa.Text),
    sa.column("created_at", sa.DateTime),
)


_IDENTITY_SPACE = re.compile(r"(?:\s|\u00a0|\u202f|\u2007|\u2009)+")


def _squeeze(value) -> str:
    return _IDENTITY_SPACE.sub("", value or "").casefold()


def _identity(vendor_nif, document_type, invoice_number) -> str:
    nif = _squeeze(vendor_nif)
    if nif.startswith("pt"):
        nif = nif[2:]
    kind = (document_type or "").strip().upper()
    number = re.sub(r"\d+", lambda match: match.group(0).lstrip("0") or "0", _squeeze(invoice_number))
    return f"{nif}|{kind}|{number}"


def _is_scan(mime, raw) -> bool:
    if (mime or "").startswith("application/vnd.invoflow.efatura"):
        return False
    text = raw or ""
    return '"source":"efatura"' not in text and '"source": "efatura"' not in text


def _stored_type(raw_type: str) -> str:
    if raw_type in _CONCRETE:
        return raw_type
    return "unclassified"


def _money(value):
    if value is None or value == "":
        return None
    amount = Decimal(str(value))
    if amount < 0:
        amount = -amount
    return amount.quantize(Decimal("0.01"))


def _vat(payload: dict):
    total = Decimal("0")
    seen = False
    for line in payload.get("lines") or []:
        if not isinstance(line, dict) or line.get("tax_type") != "IVA":
            continue
        tax = line.get("tax")
        if tax is None or tax == "":
            continue
        total += Decimal(str(tax))
        seen = True
    if not seen:
        return Decimal("0.00")
    return abs(total).quantize(Decimal("0.01"))


def _rate(payload: dict):
    rates = []
    for line in payload.get("lines") or []:
        if not isinstance(line, dict) or line.get("tax_type") != "IVA":
            continue
        tax = line.get("tax")
        percentage = line.get("percentage")
        if tax in (None, "") or Decimal(str(tax)) <= 0 or percentage in (None, ""):
            continue
        rates.append(Decimal(str(percentage)).quantize(Decimal("0.01")))
    if len(rates) == 1:
        return rates[0]
    return None


class _NotStored(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason


def _load_invoice(payload_json: str) -> dict:
    payload = json.loads(payload_json)
    if not isinstance(payload, dict):
        raise ValueError("payload is not an object")
    number = payload.get("invoice_number")
    nif = payload.get("issuer_nif")
    raw_type = payload.get("document_type")
    if not isinstance(number, str) or not number.strip():
        raise ValueError("invoice number is missing")
    if not isinstance(nif, str) or not nif.strip():
        raise ValueError("issuer NIF is missing")
    if not isinstance(raw_type, str) or raw_type not in _CONCRETE:
        raise ValueError("document type is missing")
    if payload.get("fiscal_status") == "cancelled":
        raise _NotStored("cancelled")
    if raw_type == "NC":
        raise _NotStored("a credit note")
    return payload


def upgrade() -> None:
    _restore_deleted_scans(op.get_bind())


def _restore_deleted_scans(bind) -> None:
    now = datetime.utcnow()
    link_rows = bind.execute(
        sa.select(
            links.c.id,
            links.c.user_id,
            links.c.source_key,
            links.c.outcome,
            links.c.document_id,
            links.c.payload_json,
        ).where(links.c.outcome.in_(["linked_existing", "linked_hidden"]))
    ).mappings()
    grouped: dict[tuple, list] = {}
    for link in link_rows:
        if not link["document_id"]:
            continue
        scan = bind.execute(
            sa.select(
                documents.c.id,
                documents.c.status,
                documents.c.mime_type,
                documents.c.ocr_raw_response,
                documents.c.invoice_number,
                documents.c.deleted_at,
                documents.c.expense_category,
                documents.c.irs_sector,
                documents.c.deductible_pct_override,
            ).where(documents.c.id == link["document_id"])
        ).mappings().first()
        if scan is None or scan["deleted_at"] is None:
            continue
        if not _is_scan(scan["mime_type"], scan["ocr_raw_response"]):
            continue
        try:
            payload = _load_invoice(link["payload_json"])
        except _NotStored as exc:
            log.warning("e-Fatura link %s skipped; invoice is %s", link["id"], exc.reason)
            continue
        except (TypeError, ValueError, json.JSONDecodeError):
            log.warning("e-Fatura link %s skipped; payload is not readable", link["id"])
            continue
        kind = _stored_type(str(payload.get("document_type")))
        identity = _identity(payload.get("issuer_nif"), kind, payload.get("invoice_number"))
        grouped.setdefault((link["user_id"], identity), []).append(
            {"link": link, "scan": scan, "payload": payload, "kind": kind, "identity": identity}
        )

    for (user_id, identity), items in grouped.items():
        target = _existing_at_row(bind, user_id, identity)
        if target is None:
            target = _insert_at_row(bind, items, now)
        for item in items:
            bind.execute(
                links.update()
                .where(links.c.id == item["link"]["id"])
                .values(
                    document_id=target,
                    outcome="created",
                    warning=None,
                    updated_at=now,
                )
            )
        seen_scans = set()
        for item in items:
            scan_id = item["scan"]["id"]
            if scan_id in seen_scans:
                continue
            seen_scans.add(scan_id)
            _audit(bind, item, target, now)


def _insert_at_row(bind, items, now) -> str:
    item = items[0]
    confirmed = next((entry for entry in items if entry["scan"]["status"] in _CONFIRMED), None)
    review = confirmed["scan"] if confirmed else None
    payload = item["payload"]
    document_id = str(uuid.uuid4())
    issue_date = payload.get("issue_date")
    if isinstance(issue_date, str) and issue_date:
        issue_date = datetime.strptime(issue_date[:10], "%Y-%m-%d").date()
    number = str(payload.get("invoice_number"))
    filename = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in number)[:180] or "fatura"
    bind.execute(
        documents.insert().values(
            id=document_id,
            user_id=item["link"]["user_id"],
            status=review["status"] if review else "needs_review",
            storage_key=f"efatura/{item['link']['user_id']}/{item['link']['source_key']}",
            original_filename=f"{filename}.efatura",
            mime_type="application/vnd.invoflow.efatura+json",
            vendor_name=payload.get("issuer_name"),
            vendor_nif=str(payload.get("issuer_nif")),
            invoice_number=number,
            document_type=item["kind"],
            at_document_type=str(payload.get("document_type")),
            document_date=issue_date,
            net_amount=_money(payload.get("net_total")),
            vat_amount=_vat(payload),
            gross_amount=_money(payload.get("gross_total")),
            vat_rate=_rate(payload),
            ocr_raw_response='{"source":"efatura"}',
            expense_category=review["expense_category"] if review else None,
            irs_sector=review["irs_sector"] if review else None,
            deductible_pct_override=review["deductible_pct_override"] if review else None,
            series_mismatch_accepted=False,
            deleted_at=None,
            created_at=now,
            updated_at=now,
        )
    )
    return document_id


def _audit(bind, item, target: str, now) -> None:
    scan = item["scan"]
    link = item["link"]
    changes = {
        "efatura_document_id": {"old": scan["id"], "new": target},
        "source_key": {"old": None, "new": link["source_key"]},
        "invoice_number": {"old": scan["invoice_number"], "new": item["payload"].get("invoice_number")},
    }
    bind.execute(
        audits.insert().values(
            id=str(uuid.uuid4()),
            entity_type="document",
            entity_id=scan["id"],
            user_id=link["user_id"],
            action="efatura_unlink",
            source="efatura",
            changes_json=json.dumps(changes),
            created_at=now,
        )
    )


def _existing_at_row(bind, user_id: str, identity: str):
    """An e-Fatura row for this invoice, including one that was deleted."""
    rows = bind.execute(
        sa.select(
            documents.c.id,
            documents.c.vendor_nif,
            documents.c.document_type,
            documents.c.invoice_number,
            documents.c.mime_type,
            documents.c.ocr_raw_response,
            documents.c.created_at,
        )
        .where(documents.c.user_id == user_id)
        .order_by(documents.c.created_at.asc())
    ).mappings()
    for row in rows:
        if _is_scan(row["mime_type"], row["ocr_raw_response"]):
            continue
        if _identity(row["vendor_nif"], row["document_type"], row["invoice_number"]) == identity:
            return row["id"]
    return None


def downgrade() -> None:
    # Data only. Restored rows stay, and this revision adds no column.
    return

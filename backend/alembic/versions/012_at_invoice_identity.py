"""Identity column for one live e-Fatura invoice per user

Revision ID: 012_at_invoice_identity
Revises: 011_restore_orphaned_efatura
Create Date: 2026-10-29

Adds at_invoice_identity and its unique index when they are missing, so a
database that already has the column (an older draft of 011, or dev startup)
still upgrades. Duplicate live AT rows for the same invoice are soft-deleted
down to one. The kept row is the oldest. Each removed row gets an audit entry.

The shapes below are frozen and do not import the live models.

Downgrade drops the index and the column. Soft-deleted duplicates stay deleted.

The identity string matches migration 011 and at_invoice_identity().

"""
from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime

import sqlalchemy as sa
from alembic import op


revision = "012_at_invoice_identity"
down_revision = "011_restore_orphaned_efatura"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.runtime.migration")
_IDENTITY_SPACE = re.compile(r"(?:\s|\u00a0|\u202f|\u2007|\u2009)+")

documents = sa.table(
    "documents",
    sa.column("id", sa.String),
    sa.column("user_id", sa.String),
    sa.column("vendor_nif", sa.String),
    sa.column("invoice_number", sa.String),
    sa.column("document_type", sa.String),
    sa.column("mime_type", sa.String),
    sa.column("ocr_raw_response", sa.Text),
    sa.column("at_invoice_identity", sa.String),
    sa.column("deleted_at", sa.DateTime),
    sa.column("created_at", sa.DateTime),
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


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("documents")}
    if "at_invoice_identity" not in columns:
        op.add_column(
            "documents",
            sa.Column("at_invoice_identity", sa.String(length=200), nullable=True),
        )
    removed = _dedupe(bind)
    log.info("e-Fatura identity dedupe soft-deleted %s duplicate row(s)", removed)
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("documents")}
    if "uq_documents_at_invoice_identity" not in indexes:
        op.create_index(
            "uq_documents_at_invoice_identity",
            "documents",
            ["user_id", "at_invoice_identity"],
            unique=True,
        )


def _dedupe(bind) -> int:
    now = datetime.utcnow()
    rows = list(
        bind.execute(
            sa.select(
                documents.c.id,
                documents.c.user_id,
                documents.c.vendor_nif,
                documents.c.document_type,
                documents.c.invoice_number,
                documents.c.mime_type,
                documents.c.ocr_raw_response,
                documents.c.deleted_at,
                documents.c.created_at,
            ).order_by(documents.c.created_at.asc(), documents.c.id.asc())
        ).mappings()
    )
    groups: dict[tuple, list] = {}
    for row in rows:
        if _is_scan(row["mime_type"], row["ocr_raw_response"]):
            continue
        if not row["vendor_nif"] or not row["invoice_number"] or not row["document_type"]:
            continue
        identity = _identity(row["vendor_nif"], row["document_type"], row["invoice_number"])
        groups.setdefault((row["user_id"], identity), []).append(row)

    removed = 0
    for (_user_id, identity), group in groups.items():
        live = [row for row in group if row["deleted_at"] is None]
        keeper = live[0] if live else group[0]
        bind.execute(
            documents.update()
            .where(documents.c.id == keeper["id"])
            .values(at_invoice_identity=identity, updated_at=now)
        )
        for extra in live[1:]:
            bind.execute(
                documents.update()
                .where(documents.c.id == extra["id"])
                .values(deleted_at=now, at_invoice_identity=None, updated_at=now)
            )
            bind.execute(
                audits.insert().values(
                    id=str(uuid.uuid4()),
                    entity_type="document",
                    entity_id=extra["id"],
                    user_id=extra["user_id"],
                    action="efatura_dedupe",
                    source="efatura",
                    changes_json=json.dumps(
                        {
                            "deleted_at": {"old": None, "new": now.isoformat() + "Z"},
                            "kept_document_id": {"old": None, "new": keeper["id"]},
                            "at_invoice_identity": {"old": None, "new": identity},
                        }
                    ),
                    created_at=now,
                )
            )
            removed += 1
    return removed


def downgrade() -> None:
    bind = op.get_bind()
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("documents")}
    if "uq_documents_at_invoice_identity" in indexes:
        op.drop_index("uq_documents_at_invoice_identity", table_name="documents")
    columns = {column["name"] for column in sa.inspect(bind).get_columns("documents")}
    if "at_invoice_identity" in columns:
        op.drop_column("documents", "at_invoice_identity")

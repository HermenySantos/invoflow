"""Identity column for one live e-Fatura invoice per user

Revision ID: 012_at_invoice_identity
Revises: 011_restore_orphaned_efatura
Create Date: 2026-10-29

Adds at_invoice_identity and its unique index when they are missing, so a
database that already has the column (an older draft of 011, or dev startup)
still upgrades. Any existing unique index is dropped first, because that draft
indexed deleted rows too. Identity is recomputed on every AT row, including
deleted ones. Duplicate live rows are soft-deleted down to one: a confirmed
row, then one a user edited, then one with links, then the latest update.
Links on the removed rows move to the kept row. Each removed row gets an audit
entry. The new unique index ignores deleted rows.

The shapes below are frozen and do not import the live models.

Downgrade drops the index and the column. Soft-deleted duplicates stay deleted.

The identity string matches migration 011 and at_invoice_identity().

"""
from __future__ import annotations

import json
import logging
import re
import unicodedata
import uuid
from datetime import datetime

import sqlalchemy as sa
from alembic import op


revision = "012_at_invoice_identity"
down_revision = "011_restore_orphaned_efatura"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.runtime.migration")
_CONFIRMED = {"ready", "accountant_review"}

documents = sa.table(
    "documents",
    sa.column("id", sa.String),
    sa.column("user_id", sa.String),
    sa.column("status", sa.String),
    sa.column("vendor_nif", sa.String),
    sa.column("invoice_number", sa.String),
    sa.column("document_type", sa.String),
    sa.column("mime_type", sa.String),
    sa.column("ocr_raw_response", sa.Text),
    sa.column("review_notes", sa.Text),
    sa.column("deductible_pct_override", sa.Integer),
    sa.column("at_invoice_identity", sa.String),
    sa.column("deleted_at", sa.DateTime),
    sa.column("created_at", sa.DateTime),
    sa.column("updated_at", sa.DateTime),
)

links = sa.table(
    "efatura_links",
    sa.column("id", sa.String),
    sa.column("document_id", sa.String),
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


def _prepare(value) -> str:
    text = unicodedata.normalize("NFKC", value or "")
    text = text.replace("\u00a0", " ").replace("\u202f", " ").replace("\u2007", " ").replace("\u2009", " ")
    text = text.strip()
    text = re.sub(r"\s+", " ", text)
    return text.casefold()


def _nif(value) -> str:
    text = _prepare(value)
    if text.startswith("pt") and (len(text) == 2 or text[2] == " " or text[2].isdigit()):
        text = text[2:].lstrip()
    return text.replace(" ", "")


def _separate_type_token(text: str) -> str:
    for token in ("ft", "fs", "fr", "nc", "nd"):
        if len(text) > len(token) and text.startswith(token) and text[len(token)] not in " /":
            return f"{token} {text[len(token):]}"
    return text


def _number(value) -> str:
    text = _prepare(value)
    text = re.sub(r"\s*/\s*", "/", text)
    text = _separate_type_token(text)
    if "/" not in text:
        return text
    head, seq = text.rsplit("/", 1)
    if seq.isdigit():
        seq = seq.lstrip("0") or "0"
    return f"{head}/{seq}"


def _identity(vendor_nif, document_type, invoice_number) -> str:
    kind = (document_type or "").strip().upper()
    return f"{_nif(vendor_nif)}|{kind}|{_number(invoice_number)}"


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
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("documents")}
    if "uq_documents_at_invoice_identity" in indexes:
        # An older 011 created this index without the deleted_at predicate.
        op.drop_index("uq_documents_at_invoice_identity", table_name="documents")
    removed = _dedupe(bind)
    log.info("e-Fatura identity dedupe soft-deleted %s duplicate row(s)", removed)
    op.create_index(
        "uq_documents_at_invoice_identity",
        "documents",
        ["user_id", "at_invoice_identity"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
        sqlite_where=sa.text("deleted_at IS NULL"),
    )


def _dedupe(bind) -> int:
    now = datetime.utcnow()
    rows = list(
        bind.execute(
            sa.select(
                documents.c.id,
                documents.c.user_id,
                documents.c.status,
                documents.c.vendor_nif,
                documents.c.document_type,
                documents.c.invoice_number,
                documents.c.mime_type,
                documents.c.ocr_raw_response,
                documents.c.review_notes,
                documents.c.deductible_pct_override,
                documents.c.deleted_at,
                documents.c.created_at,
                documents.c.updated_at,
            ).order_by(documents.c.created_at.asc(), documents.c.id.asc())
        ).mappings()
    )
    edited = {
        entity_id
        for entity_id in bind.execute(
            sa.select(audits.c.entity_id).where(audits.c.source == "user")
        ).scalars()
    }
    link_counts: dict[str, int] = {}
    for document_id in bind.execute(
        sa.select(links.c.document_id).where(links.c.document_id.is_not(None))
    ).scalars():
        link_counts[document_id] = link_counts.get(document_id, 0) + 1

    groups: dict[tuple, list] = {}
    for row in rows:
        if _is_scan(row["mime_type"], row["ocr_raw_response"]):
            continue
        if not row["vendor_nif"] or not row["invoice_number"] or not row["document_type"]:
            continue
        identity = _identity(row["vendor_nif"], row["document_type"], row["invoice_number"])
        groups.setdefault((row["user_id"], identity), []).append((identity, row))

    removed = 0
    for (_user_id, identity), group in groups.items():
        live = [row for _ident, row in group if row["deleted_at"] is None]

        def rank(row):
            confirmed = 1 if (row["status"] or "") in _CONFIRMED else 0
            has_edit = 1 if (
                row["id"] in edited
                or row["review_notes"]
                or row["deductible_pct_override"] is not None
            ) else 0
            has_links = 1 if link_counts.get(row["id"]) else 0
            updated = row["updated_at"] or datetime.min
            return (confirmed, has_edit, has_links, updated)

        keeper = max(live, key=rank) if live else group[0][1]
        for _ident, row in group:
            bind.execute(
                documents.update()
                .where(documents.c.id == row["id"])
                .values(at_invoice_identity=identity)
            )
        for extra in live:
            if extra["id"] == keeper["id"]:
                continue
            bind.execute(
                documents.update()
                .where(documents.c.id == extra["id"])
                .values(deleted_at=now, updated_at=now)
            )
            bind.execute(
                links.update()
                .where(links.c.document_id == extra["id"])
                .values(document_id=keeper["id"], updated_at=now)
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

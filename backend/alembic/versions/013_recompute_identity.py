"""Recompute e-Fatura identities with the current invoice-number normaliser.

Revision ID: 013_recompute_identity
Revises: 012_at_invoice_identity
Create Date: 2026-11-02

Databases that ran 012 stored identities from the previous normaliser.
After a leading FT, FS, FR, NC or ND, a run of non-alphanumerics or a
glued digit becomes one space. A letter after the code stays in the
series. º is mapped to ° before NFKC.

The upgrade adds at_invoice_identity when the column is missing and drops
uq_documents_at_invoice_identity when that index is present. The drop
comes first, because a recomputed key can match a live row the stored key
kept apart. Identity is recomputed on every AT row, including deleted
ones, when the row already has an identity or has a NIF, number and type.
Scans stay as they are. Duplicate live rows are soft-deleted down to one
with 012's ranking. A confirmed row wins, then one a user edited, then one
with links, then the latest update. Links on the removed rows move to the
kept row. Each removed row gets an efatura_dedupe audit entry. The partial
unique index is recreated. An identity update is written only when the
stored value differs, so a second run writes nothing and removes nothing.

The shapes and the normaliser below are frozen and do not import the app.

Downgrade leaves identities, soft-deleted rows, audit entries and the
index as they are.

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


revision = "013_recompute_identity"
down_revision = "012_at_invoice_identity"
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


def _prepare_identity_text(value) -> str:
    text = unicodedata.normalize("NFKC", (value or "").replace("\u00ba", "\u00b0"))
    text = text.replace("\u00a0", " ").replace("\u202f", " ").replace("\u2007", " ").replace("\u2009", " ")
    text = text.strip()
    text = re.sub(r"\s+", " ", text)
    return text.casefold()


def normalise_nif(value) -> str:
    text = _prepare_identity_text(value)
    if text.startswith("pt") and (len(text) == 2 or text[2] == " " or text[2].isdigit()):
        text = text[2:].lstrip()
    return text.replace(" ", "")


_TYPE_TOKEN_SEPARATOR = re.compile(r"^(ft|fs|fr|nc|nd)(?:[\W_]+(?=\w)|(?=\d))")


def normalise_invoice_number(value) -> str:
    text = _prepare_identity_text(value)
    text = re.sub(r"\s*/\s*", "/", text)
    if "/" in text:
        head, seq = text.rsplit("/", 1)
        if seq.isdigit():
            seq = seq.lstrip("0") or "0"
        text = f"{head}/{seq}"
    return _TYPE_TOKEN_SEPARATOR.sub(r"\1 ", text, count=1)


def at_invoice_identity(vendor_nif, document_type, invoice_number) -> str:
    kind = (document_type or "").strip().upper()
    return f"{normalise_nif(vendor_nif)}|{kind}|{normalise_invoice_number(invoice_number)}"


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
        # Drop first. The recomputed key can match a live row the stored key kept apart.
        op.drop_index("uq_documents_at_invoice_identity", table_name="documents")
    removed = _recompute(bind)
    log.info("e-Fatura identity recompute soft-deleted %s duplicate row(s)", removed)
    op.create_index(
        "uq_documents_at_invoice_identity",
        "documents",
        ["user_id", "at_invoice_identity"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
        sqlite_where=sa.text("deleted_at IS NULL"),
    )


def _recompute(bind) -> int:
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
                documents.c.at_invoice_identity,
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
        has_identity = bool(row["at_invoice_identity"])
        has_parts = bool(row["vendor_nif"] and row["invoice_number"] and row["document_type"])
        if not has_identity and not has_parts:
            continue
        identity = at_invoice_identity(
            row["vendor_nif"], row["document_type"], row["invoice_number"]
        )
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
            if row["at_invoice_identity"] == identity:
                continue
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
    """Leave identities, soft-deleted rows, audits and the index."""
    return

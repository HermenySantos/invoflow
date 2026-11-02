"""Recompute e-Fatura identities with the current invoice-number normaliser.

Revision ID: 013_recompute_identity
Revises: 012_at_invoice_identity
Create Date: 2026-11-02

Databases that ran 012 stored identities from the previous normaliser.
The identity is now built from the series check's parse: code, series and
sequence. 'FTA/5' and 'FT A/5' are one invoice, and so are 'NC. 2026/5'
and 'NC 2026/5'. º is mapped to ° before NFKC.

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
from typing import NamedTuple, Optional

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


CONCRETE_DOCUMENT_TYPES = ("FT", "FR", "FS", "ND", "NC")
_SERIES_SEPARATED = re.compile(
    r"^(?P<code>FT|FS|FR|NC|ND)(?P<sep>[\W_]+|$)",
    re.IGNORECASE,
)
# "NCA/5": the code, one extra letter, then / . or -. Whitespace does not count,
# so "FRA 2026/12" is vendor numbering.
_SERIES_GLUED_LETTER = re.compile(
    r"^(?P<code>FT|FS|FR|NC|ND)[A-Za-z](?=[/.\-])",
    re.IGNORECASE,
)
# Glued NC/ND digits. A separator after the digits always counts ("NC2026/5",
# "NC1/5"). Two or more digits count with nothing after ("NC2026", "NC001",
# "ND2026"). One digit counts only when whitespace continues the number
# ("NC1 2026"). A bare "NC1" does not. FT/FS/FR glued to digits stay vendor
# numbering ("FS2026/12", "FT2026/1").
_SERIES_GLUED_DIGIT = re.compile(
    r"^(?P<code>NC|ND)(?:\d+(?=[/.\-])|\d{2,}|\d(?=\s))",
    re.IGNORECASE,
)
# "N/C", "N.C", "N-C", "N C A/5", "N.C. A/5".
_SERIES_SPLIT = re.compile(
    r"^(?P<c1>[A-Za-z])[\s./\-]+(?P<c2>[A-Za-z])(?=[\s/.\-]|$)",
)
_CONFUSABLES = str.maketrans(
    {
        chr(code): latin
        for code, latin in (
            (0x0391, "A"), (0x03B1, "a"),  # Greek alpha
            (0x0392, "B"), (0x03B2, "b"),
            (0x0395, "E"), (0x03B5, "e"),
            (0x0396, "Z"), (0x03B6, "z"),
            (0x0397, "H"), (0x03B7, "h"),
            (0x0399, "I"), (0x03B9, "i"),
            (0x039A, "K"), (0x03BA, "k"),
            (0x039C, "M"), (0x03BC, "m"),
            (0x039D, "N"), (0x03BD, "n"),
            (0x039F, "O"), (0x03BF, "o"),
            (0x03A1, "P"), (0x03C1, "p"),
            (0x03A4, "T"), (0x03C4, "t"),
            (0x03A5, "Y"), (0x03C5, "y"),
            (0x03A7, "X"), (0x03C7, "x"),
            (0x0410, "A"), (0x0430, "a"),  # Cyrillic a
            (0x0412, "B"), (0x0432, "b"),
            (0x0415, "E"), (0x0435, "e"),
            (0x041A, "K"), (0x043A, "k"),
            (0x041C, "M"), (0x043C, "m"),
            (0x041D, "N"), (0x043D, "n"),  # Н, the H-shaped letter, read here as N
            (0x041E, "O"), (0x043E, "o"),
            (0x0420, "P"), (0x0440, "p"),
            (0x0421, "C"), (0x0441, "c"),
            (0x0422, "T"), (0x0442, "t"),
            (0x0423, "Y"), (0x0443, "y"),
            (0x0425, "X"), (0x0445, "x"),
            (0x0406, "I"), (0x0456, "i"),
            (0x0407, "I"), (0x0457, "i"),
            (0x0408, "J"), (0x0458, "j"),
            (0x0274, "N"),  # ɴ small capital n
            (0x1D04, "C"),  # ᴄ small capital c
            (0xA730, "F"),  # ꜰ
            (0x1D1B, "T"),  # ᴛ
            (0xA731, "S"),  # ꜱ
            (0x0280, "R"),  # ʀ
            (0x1D05, "D"),  # ᴅ
            (0xA4E0, "N"),  # ꓠ Lisu na, the N lookalike
            (0xA4DA, "C"),  # ꓚ Lisu ca, the C lookalike
        )
    }
)
_HYPHEN_SLASH = str.maketrans(
    {
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2015": "-",
        "\u2212": "-",
        "\ufe58": "-",
        "\ufe63": "-",
        "\uff0d": "-",
        "\u2044": "/",
        "\u2215": "/",
        "\u29f8": "/",
        "\uff0f": "/",
    }
)


def fold_series_text(value: Optional[str]) -> str:
    """Normalise a document number before the series token is read.

    º becomes ° before NFKC, which would turn it into the letter o. NFKC,
    then format characters (zero-width space, BOM, soft hyphen) are
    dropped. Greek, Cyrillic, small-cap and Lisu lookalikes fold to Latin.
    Accents fold away (Ń/Ć). Unicode hyphens and slashes become ASCII.
    """
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value).replace("\u00ba", "\u00b0"))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Cf")
    text = text.translate(_CONFUSABLES)
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.translate(_HYPHEN_SLASH)
    return text.strip()


# A code glued to letters or digits ("FTA/5", "FT2026/12", "FTFT/1"). The
# letters split off as the series unless whitespace ends the run, so
# "FTA 2026/5" and "frete 12" keep their letters.
_GLUED_CODE = re.compile(r"^(?P<code>FT|FS|FR|NC|ND)(?P<run>[A-Za-z0-9]+)", re.IGNORECASE)


class ParsedNumber(NamedTuple):
    """A document number read once, for the series check and the e-Fatura identity.

    code is FT, FS, FR, NC or ND when one is split off the front. series and seq
    are casefolded, with inner whitespace collapsed and no spaces next to '/'.
    seq is the part after the last '/', without leading zeros. is_series is True
    when the series check reads code as the number's type. A code split off
    vendor numbering ('FT2026/1', 'FTFT/1') has is_series False.
    """

    code: Optional[str]
    series: str
    seq: Optional[str]
    is_series: bool


def _split_code(text: str) -> tuple[Optional[str], str, bool]:
    separated = _SERIES_SEPARATED.match(text)
    if separated:
        code = separated.group("code")
        follows = text[separated.end():separated.end() + 1]
        if code.isupper() or "." not in separated.group("sep") or follows.isalpha():
            return code.upper(), text[separated.end():], True
        return None, text, False
    glued = _GLUED_CODE.match(text)
    if glued:
        counts = bool(_SERIES_GLUED_DIGIT.match(text) or _SERIES_GLUED_LETTER.match(text))
        after_run = text[glued.end():glued.end() + 1]
        if counts or glued.group("run")[0].isdigit() or not after_run.isspace():
            return glued.group("code").upper(), text[glued.start("run"):], counts
        return None, text, False
    split = _SERIES_SPLIT.match(text)
    if split:
        code = (split.group("c1") + split.group("c2")).upper()
        if code in CONCRETE_DOCUMENT_TYPES:
            return code, re.sub(r"^[\W_]+", "", text[split.end():]), True
    return None, text, False


def parse_document_number(number: Optional[str]) -> ParsedNumber:
    """Split a document number into code, series and sequence."""
    code, rest, is_series = _split_code(fold_series_text(number))
    rest = re.sub(r"\s+", " ", rest.casefold()).strip()
    rest = re.sub(r"\s*/\s*", "/", rest)
    if "/" not in rest:
        return ParsedNumber(code, rest, None, is_series)
    series, seq = rest.rsplit("/", 1)
    if seq.isdigit():
        seq = seq.lstrip("0") or "0"
    return ParsedNumber(code, series, seq, is_series)


def normalise_invoice_number(value) -> str:
    parsed = parse_document_number(value)
    body = parsed.series if parsed.seq is None else f"{parsed.series}/{parsed.seq}"
    if parsed.code is None:
        return body
    return f"{parsed.code.lower()} {body}".rstrip()


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

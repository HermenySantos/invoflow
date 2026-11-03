"""Keep the series' letter case in the e-Fatura identity and split false merges.

Revision ID: 014_series_case_identity
Revises: 013_recompute_identity
Create Date: 2026-11-03

AT allows both upper and lower case letters in a series, so 'FT A/5' and
'FT a/5' from one supplier can be two invoices. Until now the identity
casefolded the series and stored them as one row. The type code still
ignores case ('ft A/5' and 'FT A/5' are one invoice), and 'FTA/5' is still
'FT A/5'. A punctuation mark that follows the space after the code now
starts the series: 'FT -A/5' is no longer 'FT A/5'.

The upgrade, in order:

1. Recomputes at_invoice_identity on every AT row, including deleted ones,
   that has an identity or a NIF, number and type. Scans stay as they are.
   The new key only ever tells apart rows the old key merged, so no two live
   rows can collide.
2. Restores an AT row that 012 or 013 soft-deleted as a duplicate
   (its latest audit entry is efatura_dedupe) when its new identity differs
   from the kept row's and no live row has that identity.
3. Splits a document whose links carry more than one invoice under the new
   identity. The links whose invoice matches the document stay. A scan with
   no matching group keeps the group that matches it ignoring case, else
   its oldest link. Every other invoice moves to its live AT row, else its
   deleted AT row (which stays deleted), else a new AT row built from the
   link payload in needs_review. A document with links for one invoice is
   never touched, with one exception: an AT row whose doc-key link now
   carries the other case of its number ('FT A/5' row, 'FT a/5' payload).
   A doc key lowercased the number, so the later pull overwrote the
   payload. That row keeps its own invoice and the payload's invoice is
   split off. Every moved link gets a warning naming the document it left.
4. Checks that live AT rows still have unique identities, then recreates
   the partial unique index.

Each restored or new row gets an efatura_split audit entry. Writes happen
only where a stored value differs, so a second run writes nothing. An empty
database, or one with no merged rows, only gets the identity recompute.

The shapes and the normaliser below are frozen and do not import the app.

Downgrade leaves identities, restored rows, split rows, audits and the index
as they are.

"""
from __future__ import annotations

import json
import logging
import re
import unicodedata
import uuid
from datetime import datetime
from decimal import Decimal
from typing import NamedTuple, Optional

import sqlalchemy as sa
from alembic import op


revision = "014_series_case_identity"
down_revision = "013_recompute_identity"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.runtime.migration")
_INDEX = "uq_documents_at_invoice_identity"
_AT_MIME = "application/vnd.invoflow.efatura+json"

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
    sa.column("at_invoice_identity", sa.String),
    sa.column("deleted_at", sa.DateTime),
    sa.column("created_at", sa.DateTime),
    sa.column("updated_at", sa.DateTime),
)

links = sa.table(
    "efatura_links",
    sa.column("id", sa.String),
    sa.column("user_id", sa.String),
    sa.column("source_key", sa.String),
    sa.column("outcome", sa.String),
    sa.column("document_id", sa.String),
    sa.column("warning", sa.Text),
    sa.column("payload_json", sa.Text),
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


# A code glued to letters or digits ("FTA/5", "FTA 2026/5", "FT2026/12",
# "FTFT/1"). The identity always splits it off. The series check counts it
# only under its glued-digit and glued-letter rules.
_GLUED_CODE = re.compile(r"^(?P<code>FT|FS|FR|NC|ND)(?P<run>[A-Za-z0-9]+)", re.IGNORECASE)


class ParsedNumber(NamedTuple):
    code: Optional[str]
    series: str
    seq: Optional[str]
    is_series: bool
    glued_run: str = ""


# Punctuation that follows a space after the code starts the series:
# 'FT -A/5' is series '-A', not 'A'. 'FT-A/5' and 'FT - A/5' still split.
_SERIES_LEADING_MARK = re.compile(r"\s+(?P<mark>[^\s/]+)$")


def _split_code(text: str) -> tuple[Optional[str], str, bool, str]:
    separated = _SERIES_SEPARATED.match(text)
    if separated:
        code = separated.group("code")
        sep = separated.group("sep")
        follows = text[separated.end():separated.end() + 1]
        if code.isupper() or "." not in sep or follows.isalpha():
            rest = text[separated.end():]
            mark = _SERIES_LEADING_MARK.fullmatch(sep)
            if mark and follows.isalnum():
                rest = mark.group("mark") + rest
            return code.upper(), rest, True, ""
        return None, text, False, ""
    glued = _GLUED_CODE.match(text)
    if glued:
        counts = bool(_SERIES_GLUED_DIGIT.match(text) or _SERIES_GLUED_LETTER.match(text))
        return glued.group("code").upper(), text[glued.start("run"):], counts, glued.group("run")
    split = _SERIES_SPLIT.match(text)
    if split:
        code = (split.group("c1") + split.group("c2")).upper()
        if code in CONCRETE_DOCUMENT_TYPES:
            return code, re.sub(r"^[\W_]+", "", text[split.end():]), True, ""
    return None, text, False, ""


def parse_document_number(number: Optional[str]) -> ParsedNumber:
    code, rest, is_series, glued_run = _split_code(fold_series_text(number))
    rest = re.sub(r"\s+", " ", rest).strip()
    rest = re.sub(r"\s*/\s*", "/", rest)
    if "/" not in rest:
        return ParsedNumber(code, rest, None, is_series, glued_run)
    series, seq = rest.rsplit("/", 1)
    if seq.isdigit():
        seq = seq.lstrip("0") or "0"
    return ParsedNumber(code, series, seq, is_series, glued_run)


def normalise_invoice_number(value) -> str:
    parsed = parse_document_number(value)
    body = parsed.series if parsed.seq is None else f"{parsed.series}/{parsed.seq}"
    if parsed.code is None:
        return body
    return f"{parsed.code.lower()} {body}".rstrip()


def at_invoice_identity(vendor_nif, document_type, invoice_number) -> str:
    kind = (document_type or "").strip().upper()
    return f"{normalise_nif(vendor_nif)}|{kind}|{normalise_invoice_number(invoice_number)}"


def _scan_number(value) -> str:
    parsed = parse_document_number(value)
    series = re.sub(r"^[\W_]+", "", parsed.series)
    body = series if parsed.seq is None else f"{series}/{parsed.seq}"
    head = f"{parsed.code.lower()} " if parsed.code else ""
    return f"{head}{body}".strip().casefold()


def _is_scan(mime, raw) -> bool:
    if (mime or "").startswith("application/vnd.invoflow.efatura"):
        return False
    text = raw or ""
    return '"source":"efatura"' not in text and '"source": "efatura"' not in text


def _stored_type(raw_type) -> str:
    if raw_type in CONCRETE_DOCUMENT_TYPES:
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


def _payload(payload_json):
    """The link's invoice, or None when the payload has no NIF and number."""
    try:
        payload = json.loads(payload_json or "")
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    if not isinstance(payload.get("issuer_nif"), str) or not isinstance(
        payload.get("invoice_number"), str
    ):
        return None
    if not payload["invoice_number"].strip():
        return None
    return payload


def _audit(bind, *, entity_id, user_id, changes, now) -> None:
    bind.execute(
        audits.insert().values(
            id=str(uuid.uuid4()),
            entity_type="document",
            entity_id=entity_id,
            user_id=user_id,
            action="efatura_split",
            source="efatura",
            changes_json=json.dumps(changes),
            created_at=now,
        )
    )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if not {"documents", "efatura_links", "audit_logs"} <= tables:
        return
    columns = {column["name"] for column in inspector.get_columns("documents")}
    if "at_invoice_identity" not in columns:
        return
    indexes = {index["name"] for index in inspector.get_indexes("documents")}
    if _INDEX in indexes:
        op.drop_index(_INDEX, table_name="documents")
    counts = _apply(bind, datetime.utcnow())
    log.info(
        "e-Fatura series case: %s identity update(s), %s row(s) restored, %s row(s) split off",
        *counts,
    )
    op.create_index(
        _INDEX,
        "documents",
        ["user_id", "at_invoice_identity"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
        sqlite_where=sa.text("deleted_at IS NULL"),
    )


def _apply(bind, now) -> tuple[int, int, int]:
    rows = {
        row["id"]: dict(row)
        for row in bind.execute(
            sa.select(
                documents.c.id,
                documents.c.user_id,
                documents.c.vendor_nif,
                documents.c.document_type,
                documents.c.invoice_number,
                documents.c.mime_type,
                documents.c.ocr_raw_response,
                documents.c.at_invoice_identity,
                documents.c.deleted_at,
                documents.c.created_at,
            ).order_by(documents.c.created_at.asc(), documents.c.id.asc())
        ).mappings()
    }

    updated = 0
    # identity of every AT row, live and deleted, under the new rule
    identities: dict[str, str] = {}
    for row in rows.values():
        if _is_scan(row["mime_type"], row["ocr_raw_response"]):
            continue
        if not row["at_invoice_identity"] and not (
            row["vendor_nif"] and row["invoice_number"] and row["document_type"]
        ):
            continue
        identity = at_invoice_identity(row["vendor_nif"], row["document_type"], row["invoice_number"])
        identities[row["id"]] = identity
        if row["at_invoice_identity"] != identity:
            bind.execute(
                documents.update()
                .where(documents.c.id == row["id"])
                .values(at_invoice_identity=identity)
            )
            row["at_invoice_identity"] = identity
            updated += 1

    def live_row(user_id, identity):
        for row_id, row_identity in identities.items():
            row = rows[row_id]
            if row["user_id"] == user_id and row_identity == identity and row["deleted_at"] is None:
                return row_id
        return None

    def deleted_row(user_id, identity):
        for row_id, row_identity in identities.items():
            row = rows[row_id]
            if row["user_id"] == user_id and row_identity == identity and row["deleted_at"] is not None:
                return row_id
        return None

    restored = _restore_dedupes(bind, rows, identities, live_row, now)
    split = _split_links(bind, rows, identities, live_row, deleted_row, now)

    seen: dict[tuple, str] = {}
    for row_id, identity in identities.items():
        row = rows[row_id]
        if row["deleted_at"] is not None:
            continue
        key = (row["user_id"], identity)
        if key in seen:
            raise RuntimeError(
                f"documents {seen[key]} and {row_id} share e-Fatura identity {identity}"
            )
        seen[key] = row_id
    return updated, restored, split


def _restore_dedupes(bind, rows, identities, live_row, now) -> int:
    latest: dict[str, dict] = {}
    for audit in bind.execute(
        sa.select(audits.c.entity_id, audits.c.action, audits.c.changes_json, audits.c.created_at)
        .where(audits.c.entity_type == "document")
        .order_by(audits.c.created_at.asc(), audits.c.id.asc())
    ).mappings():
        latest[audit["entity_id"]] = dict(audit)

    restored = 0
    for row_id, identity in list(identities.items()):
        row = rows[row_id]
        audit = latest.get(row_id)
        if row["deleted_at"] is None or audit is None or audit["action"] != "efatura_dedupe":
            continue
        try:
            keeper = json.loads(audit["changes_json"] or "{}")["kept_document_id"]["new"]
        except (TypeError, ValueError, KeyError):
            continue
        if keeper not in identities or identities[keeper] == identity:
            continue
        if live_row(row["user_id"], identity) is not None:
            continue
        bind.execute(
            documents.update()
            .where(documents.c.id == row_id)
            .values(deleted_at=None, updated_at=now)
        )
        _audit(
            bind,
            entity_id=row_id,
            user_id=row["user_id"],
            changes={
                "deleted_at": {"old": row["deleted_at"].isoformat() + "Z", "new": None},
                "split_from_document_id": {"old": None, "new": keeper},
                "at_invoice_identity": {"old": identities[keeper], "new": identity},
            },
            now=now,
        )
        row["deleted_at"] = None
        restored += 1
    return restored


def _split_links(bind, rows, identities, live_row, deleted_row, now) -> int:
    by_document: dict[str, list] = {}
    for link in bind.execute(
        sa.select(
            links.c.id,
            links.c.user_id,
            links.c.source_key,
            links.c.document_id,
            links.c.payload_json,
            links.c.created_at,
        )
        .where(links.c.document_id.is_not(None))
        .order_by(links.c.created_at.asc(), links.c.id.asc())
    ).mappings():
        payload = _payload(link["payload_json"])
        if payload is None or link["document_id"] not in rows:
            continue
        kind = _stored_type(payload.get("document_type"))
        identity = at_invoice_identity(payload["issuer_nif"], kind, payload["invoice_number"])
        by_document.setdefault(link["document_id"], []).append((identity, kind, payload, link))

    split = 0
    for document_id, items in by_document.items():
        groups: dict[str, list] = {}
        for item in items:
            groups.setdefault(item[0], []).append(item)
        document = rows[document_id]
        own = identities.get(document_id)
        if own is not None and own not in groups and any(_overwritten(document, item) for item in items):
            groups[own] = []
        if len(groups) < 2:
            continue
        keep = _kept_identity(document, own, groups, items)
        for identity, group in groups.items():
            if identity == keep:
                continue
            user_id = document["user_id"]
            target = live_row(user_id, identity) or deleted_row(user_id, identity)
            if target is None:
                target = _insert_at_row(bind, user_id, group, identity, now)
                rows[target] = {
                    "id": target,
                    "user_id": user_id,
                    "deleted_at": None,
                }
                identities[target] = identity
                split += 1
            bind.execute(
                links.update()
                .where(links.c.id.in_([item[3]["id"] for item in group]))
                .values(
                    document_id=target,
                    outcome="created",
                    warning=(
                        f"Split off receipt {document_id}: the series' letter case "
                        "makes it another e-Fatura document. Review both."
                    ),
                    updated_at=now,
                )
            )
            _audit(
                bind,
                entity_id=target,
                user_id=user_id,
                changes={
                    "split_from_document_id": {"old": None, "new": document_id},
                    "at_invoice_identity": {"old": keep, "new": identity},
                    "source_keys": {"old": None, "new": [item[3]["source_key"] for item in group]},
                },
                now=now,
            )
    return split


def _overwritten(document, item) -> bool:
    """A doc key lowercased the number, so a pull of 'FT a/5' overwrote the
    payload of the link that made the 'FT A/5' row. The row is still 'FT A/5'."""
    _identity, _kind, payload, link = item
    return (link["source_key"] or "").startswith("doc:") and (
        payload["invoice_number"].strip().lower() == (document["invoice_number"] or "").strip().lower()
    )


def _kept_identity(document, own_identity, groups, items) -> str:
    if own_identity in groups:
        return own_identity
    if _is_scan(document["mime_type"], document["ocr_raw_response"]) and document["invoice_number"]:
        nif = normalise_nif(document["vendor_nif"])
        number = normalise_invoice_number(document["invoice_number"])
        for identity, group in groups.items():
            payload = group[0][2]
            if (normalise_nif(payload["issuer_nif"]), normalise_invoice_number(payload["invoice_number"])) == (
                nif,
                number,
            ):
                return identity
        loose = _scan_number(document["invoice_number"])
        for identity, group in groups.items():
            payload = group[0][2]
            if normalise_nif(payload["issuer_nif"]) == nif and _scan_number(payload["invoice_number"]) == loose:
                return identity
    return items[0][0]


def _insert_at_row(bind, user_id, group, identity, now) -> str:
    _identity, kind, payload, link = group[0]
    document_id = str(uuid.uuid4())
    issue_date = payload.get("issue_date")
    if isinstance(issue_date, str) and issue_date:
        issue_date = datetime.strptime(issue_date[:10], "%Y-%m-%d").date()
    else:
        issue_date = None
    number = str(payload.get("invoice_number"))
    filename = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in number)[:180] or "fatura"
    bind.execute(
        documents.insert().values(
            id=document_id,
            user_id=user_id,
            status="needs_review",
            storage_key=f"efatura/{user_id}/{link['source_key']}",
            original_filename=f"{filename}.efatura",
            mime_type=_AT_MIME,
            vendor_name=payload.get("issuer_name"),
            vendor_nif=str(payload.get("issuer_nif")),
            invoice_number=number,
            document_type=kind,
            at_document_type=str(payload.get("document_type")),
            document_date=issue_date,
            net_amount=_money(payload.get("net_total")),
            vat_amount=_vat(payload),
            gross_amount=_money(payload.get("gross_total")),
            vat_rate=_rate(payload),
            ocr_raw_response='{"source":"efatura"}',
            expense_category=None,
            irs_sector=None,
            deductible_pct_override=None,
            series_mismatch_accepted=False,
            at_invoice_identity=identity,
            deleted_at=None,
            created_at=now,
            updated_at=now,
        )
    )
    return document_id


def downgrade() -> None:
    """Leave identities, restored rows, split rows, audits and the index."""
    return

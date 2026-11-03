"""e-Fatura pull.

Public surface: InvoiceQuery, EFaturaInvoice, EFaturaClient, build_efatura_client,
import_purchases. Adapters return domain invoices. The importer writes new
purchases and link rows.
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
import uuid
from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Callable, Literal, Optional, Protocol, Sequence

from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.models.document import Document
from app.models.efatura import EfaturaLink, EfaturaSubject
from app.schemas.document import parse_document_number
from app.services.audit import drop_accepted_series_mismatch, log_auto_categorize, log_event
from app.services.categorization import categorize_document

DocumentType = Literal["FT", "FS", "FR", "NC", "ND", "PF", "OR", "RG", "GT"]
FiscalStatus = Literal["normal", "cancelled", "invoiced"]
PartyRole = Literal["acquirer", "issuer", "not_party"]

_DOCUMENT_TYPES = ("FT", "FS", "FR", "NC", "ND", "PF", "OR", "RG", "GT")
_FISCAL_STATUSES = ("normal", "cancelled", "invoiced")
_STORABLE_TYPES = ("FT", "FS", "FR", "ND")
_REVIEW_TYPES = ("PF", "OR", "RG", "GT")
_CONCRETE_AT_TYPES = frozenset({"FT", "FS", "FR", "NC", "ND"})
_STORABLE_FISCAL = ("normal", "invoiced")
_NIF = re.compile(r"^\d{9}$")
_CENT = Decimal("0.01")
_GROSS_TOLERANCE = Decimal("0.50")
_LINKED_WARNING = "Linked to an existing receipt without copying e-Fatura figures."
_HIDDEN_WARNING = "Linked to a hidden receipt without restoring it or copying e-Fatura figures."
_CANCELLED_WARNING = "e-Fatura fiscal status changed to cancelled. The receipt was not changed."


@dataclass(frozen=True)
class VatLine:
    tax_type: str
    region: str
    tax_code: str
    percentage: Optional[Decimal]
    taxable: Decimal
    tax: Decimal
    exemption_code: Optional[str]


@dataclass(frozen=True)
class EFaturaInvoice:
    """Parsed consultation row. issuer_nif is the supplier. acquirer_nif is the buyer."""

    document_type: DocumentType
    invoice_number: str
    issue_date: date
    issuer_nif: str
    acquirer_nif: Optional[str]
    acquirer_country: Optional[str]
    fiscal_status: FiscalStatus
    lines: tuple[VatLine, ...]
    tax_payable: Optional[Decimal]
    net_total: Optional[Decimal]
    gross_total: Optional[Decimal]
    atcud: Optional[str] = None
    issuer_name: Optional[str] = None


@dataclass(frozen=True)
class InvoiceQuery:
    taxpayer_nif: str
    period_start: date
    period_end: date


class EFaturaClient(Protocol):
    def fetch(self, query: InvoiceQuery) -> tuple[EFaturaInvoice, ...]:
        """Return domain invoices."""


class EFaturaDisabled(Exception):
    """Flag is off. The fixture file has not been opened."""


class EFaturaConfigError(Exception):
    """Endpoint is set but a sandbox credential is empty. No socket was opened."""


class EFaturaSubjectMismatch(Exception):
    """This user already has a different taxpayer NIF stored."""


@dataclass(frozen=True)
class Skipped:
    source_key: str
    outcome: str
    warning: Optional[str] = None


@dataclass(frozen=True)
class ImportResult:
    created: tuple[str, ...]
    linked_existing: tuple[str, ...]
    unchanged: tuple[str, ...]
    skipped: tuple[Skipped, ...]
    warnings: tuple[str, ...]


def build_efatura_client(settings: object) -> EFaturaClient:
    """Select the adapter. Do not call this from lifespan.

    Flag off raises EFaturaDisabled and does not open the fixture.
    An empty endpoint uses the fixture. A set endpoint with a blank username,
    password, or AT public key raises EFaturaConfigError. Otherwise the SOAP
    adapter is returned and its fetch does not connect.
    """
    enabled = bool(getattr(settings, "efatura_pull_enabled", False))
    if not enabled:
        raise EFaturaDisabled("e-Fatura pull is disabled")

    endpoint = str(getattr(settings, "efatura_endpoint", "") or "").strip()
    if not endpoint:
        return FixtureEFaturaClient()

    username = str(getattr(settings, "efatura_username", "") or "").strip()
    password = str(getattr(settings, "efatura_password", "") or "")
    at_public_key = str(getattr(settings, "efatura_at_public_key_pem", "") or "").strip()
    if not username or not password or not at_public_key:
        raise EFaturaConfigError(
            "EFATURA_ENDPOINT is set but EFATURA_USERNAME, EFATURA_PASSWORD, "
            "or EFATURA_AT_PUBLIC_KEY_PEM is empty"
        )
    return SoapEFaturaClient(
        endpoint=endpoint,
        username=username,
        password=password,
        at_public_key_pem=at_public_key,
        client_cert_pem=str(getattr(settings, "efatura_client_cert_pem", "") or ""),
        client_key_pem=str(getattr(settings, "efatura_client_key_pem", "") or ""),
    )


def _fixture_path() -> Path:
    return Path(__file__).resolve().parent / "efatura_fixtures" / "purchases.json"


def _load_fixture_rows() -> list[dict]:
    payload = json.loads(_fixture_path().read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("e-Fatura fixture must be a list")
    return payload


class FixtureEFaturaClient:
    def fetch(self, query: InvoiceQuery) -> tuple[EFaturaInvoice, ...]:
        """Read the fixture here. Keep rows whose issue date is inside the query."""
        invoices = []
        for row in _load_fixture_rows():
            invoice = _parse_invoice(row)
            if query.period_start <= invoice.issue_date <= query.period_end:
                invoices.append(invoice)
        return tuple(invoices)


class SoapEFaturaClient:
    """Selected when sandbox settings are present. fetch does not connect."""

    def __init__(
        self,
        *,
        endpoint: str,
        username: str,
        password: str,
        at_public_key_pem: str,
        client_cert_pem: str = "",
        client_key_pem: str = "",
    ) -> None:
        self._endpoint = endpoint
        self._username = username
        self._password = password
        self._at_public_key_pem = at_public_key_pem
        self._client_cert_pem = client_cert_pem
        self._client_key_pem = client_key_pem

    def fetch(self, query: InvoiceQuery) -> tuple[EFaturaInvoice, ...]:
        raise NotImplementedError("e-Fatura test-environment consultation is not implemented")


def import_purchases(
    db: Session,
    *,
    user_id: str,
    taxpayer_nif: str,
    invoices: Sequence[EFaturaInvoice],
    after_invoice: Optional[Callable[[EFaturaInvoice], None]] = None,
) -> ImportResult:
    """Store acquirer purchases on Document and record every row on a link.

    The caller commits. This function does not. Each invoice runs in a savepoint,
    so a failed invoice does not undo the caller's uncommitted work or the other
    invoices. ``after_invoice`` is a test hook, called inside the savepoint.
    """
    if not _NIF.fullmatch(taxpayer_nif or ""):
        raise ValueError("taxpayer_nif must be 9 digits")

    subject = db.query(EfaturaSubject).filter(EfaturaSubject.user_id == user_id).one_or_none()
    if subject is None:
        subject = EfaturaSubject(
            user_id=user_id,
            taxpayer_nif=taxpayer_nif,
            updated_at=datetime.utcnow(),
        )
        db.add(subject)
        db.flush()
    elif subject.taxpayer_nif != taxpayer_nif:
        raise EFaturaSubjectMismatch(
            "taxpayer NIF does not match the one stored for this account"
        )

    created: list[str] = []
    linked_existing: list[str] = []
    unchanged: list[str] = []
    skipped: list[Skipped] = []
    warnings: list[str] = []

    known = _known_at_invoices(db, user_id, invoices)
    for invoice in invoices:
        outcome = None
        key = _source_key(invoice)
        for attempt in range(2):
            try:
                with db.begin_nested():
                    outcome = _import_one(
                        db,
                        user_id=user_id,
                        taxpayer_nif=taxpayer_nif,
                        invoice=invoice,
                        known=known,
                    )
                    db.flush()
                    if after_invoice is not None:
                        after_invoice(invoice)
                break
            except OperationalError as exc:
                if not is_pg_deadlock(exc):
                    raise
                logger.warning("e-Fatura import deadlock on %s; retrying", key)
                if attempt == 0:
                    continue
                logger.warning("e-Fatura import deadlock on %s; recorded as failed", key)
                warning = "A importação deste documento falhou após duas tentativas."
                skipped.append(Skipped(key, "deadlock", warning))
                warnings.append(f"{key}: {warning}")
                outcome = None
                break
            except IntegrityError:
                link = (
                    db.query(EfaturaLink)
                    .filter(
                        EfaturaLink.user_id == user_id,
                        EfaturaLink.source_key == key,
                    )
                    .one_or_none()
                )
                unchanged.append(key if link is None else link.source_key)
                outcome = None
                break
        if outcome is None:
            continue

        if outcome.kind == "created" and outcome.document_id:
            created.append(outcome.document_id)
        elif outcome.kind == "linked" and outcome.document_id:
            linked_existing.append(outcome.document_id)
        elif outcome.kind == "unchanged":
            unchanged.append(outcome.source_key)
        elif outcome.kind == "skipped":
            skipped.append(Skipped(outcome.source_key, outcome.outcome, outcome.warning))
        if outcome.warning and outcome.kind in ("linked", "skipped", "unchanged", "created"):
            warnings.append(outcome.warning)

    return ImportResult(
        created=tuple(created),
        linked_existing=tuple(linked_existing),
        unchanged=tuple(unchanged),
        skipped=tuple(skipped),
        warnings=tuple(warnings),
    )


@dataclass
class _Outcome:
    kind: str
    source_key: str
    outcome: str = ""
    document_id: Optional[str] = None
    warning: Optional[str] = None


def _import_one(
    db: Session,
    *,
    user_id: str,
    taxpayer_nif: str,
    invoice: EFaturaInvoice,
    known: set[_KnownInvoice],
) -> _Outcome:
    source_key, existing = _resolve_source_key(db, user_id, invoice)
    if existing is not None:
        # Documents first, then this link. Delete uses the same order.
        _lock_documents_then_links(
            db,
            [existing.document_id] if existing.document_id else [],
            [existing.id],
        )
        db.refresh(existing)
    payload = _payload(invoice)
    if existing is not None:
        warning = None
        if existing.fiscal_status != "cancelled" and invoice.fiscal_status == "cancelled":
            warning = _CANCELLED_WARNING
            existing.warning = warning
        existing.fiscal_status = invoice.fiscal_status
        existing.payload_json = payload
        existing.updated_at = datetime.utcnow()
        _retire_printed_pair(db, existing.document_id, invoice.document_type)
        restored = restore_orphaned_link(db, existing, invoice, audit_source="efatura")
        if restored is not None:
            document, created_new = restored
            if created_new:
                return _Outcome("created", source_key, "created", document.id)
            return _Outcome("unchanged", source_key, existing.outcome, document.id, warning)
        return _Outcome("unchanged", source_key, existing.outcome, existing.document_id, warning)

    role = _role(invoice, taxpayer_nif)
    skip = _skip_reason(invoice, role)
    if skip is not None:
        _add_link(
            db,
            user_id=user_id,
            source_key=source_key,
            role=role,
            outcome=skip,
            document_id=None,
            fiscal_status=invoice.fiscal_status,
            warning=None,
            payload=payload,
        )
        return _Outcome("skipped", source_key, skip)

    matches = _match_documents(db, user_id, invoice)
    if len(matches) > 1:
        ids = ", ".join(sorted(document.id for document in matches))
        warning = f"Several receipts match this e-Fatura document: {ids}"
        _add_link(
            db,
            user_id=user_id,
            source_key=source_key,
            role=role,
            outcome="ambiguous_duplicate",
            document_id=None,
            fiscal_status=invoice.fiscal_status,
            warning=warning,
            payload=payload,
        )
        return _Outcome("skipped", source_key, "ambiguous_duplicate", warning=warning)

    if len(matches) == 1:
        # A concurrent retype holds this row lock. Re-read the row after it
        # commits, so an NC scan is not linked to an FT.
        _lock_documents_then_links(db, [matches[0].id], [])
        db.refresh(matches[0])
        if not _type_compatible(matches[0], invoice):
            matches = []

    if len(matches) == 1 and not _matched_same_invoice(matches[0], invoice):
        # A loose match must not swallow a different invoice. Store it instead.
        matches = []

    review_warning = None
    if len(matches) == 1:
        _release_loose_links(db, matches[0], invoice)
        review_warning = _unsafe_link_warning(db, matches[0], invoice, known)
        if review_warning is not None:
            matches = []

    if len(matches) == 1:
        document = matches[0]
        hidden = document.deleted_at is not None
        warning = _HIDDEN_WARNING if hidden else _LINKED_WARNING
        outcome = "linked_hidden" if hidden else "linked_existing"
        _add_link(
            db,
            user_id=user_id,
            source_key=source_key,
            role=role,
            outcome=outcome,
            document_id=document.id,
            fiscal_status=invoice.fiscal_status,
            warning=warning,
            payload=payload,
        )
        log_event(
            db,
            entity_type="document",
            entity_id=document.id,
            user_id=user_id,
            action="efatura_duplicate",
            source="efatura",
            changes={
                "source_key": {"old": None, "new": source_key},
                "fields_copied": {"old": None, "new": False},
            },
        )
        drop_accepted_series_mismatch(db, document, invoice.document_type, source="efatura")
        return _Outcome("linked", source_key, outcome, document.id, warning)

    # A user-deleted AT row stays deleted, including when this invoice arrives
    # under a new source key. This is the same identity check as _place_at_invoice.
    identity = at_invoice_identity(
        invoice.issuer_nif, _stored_type(invoice), invoice.invoice_number
    )
    if _identity_row(db, user_id, identity, live=False) is not None:
        return _Outcome("unchanged", source_key, "unchanged")

    if review_warning is None:
        review_warning = _similar_scan_warning(db, user_id, invoice)
    document = _new_purchase(db, user_id=user_id, source_key=source_key, invoice=invoice)
    _add_link(
        db,
        user_id=user_id,
        source_key=source_key,
        role=role,
        outcome="created",
        document_id=document.id,
        fiscal_status=invoice.fiscal_status,
        warning=review_warning,
        payload=payload,
    )
    return _Outcome("created", source_key, "created", document.id, review_warning)


def _prepare_identity_text(value: Optional[str]) -> str:
    """º becomes °, NFKC, NBSP becomes a space, outer trim, inner whitespace runs become one space."""
    text = unicodedata.normalize("NFKC", (value or "").replace("\u00ba", "\u00b0"))
    text = text.replace("\u00a0", " ").replace("\u202f", " ").replace("\u2007", " ").replace("\u2009", " ")
    text = text.strip()
    text = re.sub(r"\s+", " ", text)
    return text.casefold()


def normalise_nif(value: Optional[str]) -> str:
    """NIF identity. A leading PT is removed only when a digit or space follows it.

    Every remaining space is removed. A NIF is digits, so ``123 456 002`` is
    ``123456002``. Spaces in an invoice number are a different rule.
    """
    text = _prepare_identity_text(value)
    if text.startswith("pt") and (len(text) == 2 or text[2] == " " or text[2].isdigit()):
        text = text[2:].lstrip()
    return text.replace(" ", "")


def normalise_invoice_number(value: Optional[str]) -> str:
    """Number identity, built from parse_document_number, the series check's parse.

    'FTA/5' and 'FT A/5' are both FT, series A, sequence 5: 'ft A/5'. The
    type code ignores case and the series does not, so 'FT a/5' is
    'ft a/5', a different invoice. Inner spaces stay, collapsed to one, and
    the spaces next to '/' go. Leading zeros come off only the sequence after
    the last '/'. 'FT A1/005' and 'FT A1/5' match. 'FT A01/5' and 'FT A1/5'
    do not. 'FT -A/5' keeps its '-'.
    """
    parsed = parse_document_number(value)
    body = parsed.series if parsed.seq is None else f"{parsed.series}/{parsed.seq}"
    if parsed.code is None:
        return body
    return f"{parsed.code.lower()} {body}".rstrip()


def _scan_number(value: Optional[str]) -> str:
    """A looser key a scan may link on: case folded, leading series marks dropped.

    'ft a/5' and 'FT -A/5' share it with 'FT A/5'. It is only used when no
    number matches exactly and no other known AT invoice shares the key.
    """
    parsed = parse_document_number(value)
    series = re.sub(r"^[\W_]+", "", parsed.series)
    body = series if parsed.seq is None else f"{series}/{parsed.seq}"
    head = f"{parsed.code.lower()} " if parsed.code else ""
    return f"{head}{body}".strip().casefold()


def _glue_key(value: Optional[str]) -> str:
    """The scan key with every space before the sequence removed.

    Every way of reading a number that lost its spaces shares it:
    'FRA2026/12', 'FRA 2026/12' and 'FR A2026/12' are all 'fra2026/12'.
    """
    return _scan_number(value).replace(" ", "")


def _reads_two_ways(value: Optional[str]) -> bool:
    """True when the code is glued to two or more characters.

    'FRA2026/12' can be FR series A2026 or the vendor code FRA with series
    2026. 'FTA/5' has one glued letter and only reads as FT series A.
    """
    return len(parse_document_number(value).glued_run) >= 2


def _keeps_case(value: Optional[str]) -> bool:
    """False for a number with no upper case letter, such as OCR's 'ft a/5'.

    Its series case says nothing, so it matches only on the looser scan key.
    """
    return any(ch.isupper() for ch in value or "")


def at_invoice_identity(
    vendor_nif: Optional[str],
    document_type: Optional[str],
    invoice_number: Optional[str],
) -> str:
    """One key for an AT invoice, shared by a doc-key link and an ATCUD link.

    NIF, type and number are normalised the same way import matching compares them.
    """
    kind = (document_type or "").strip().upper()
    return f"{normalise_nif(vendor_nif)}|{kind}|{normalise_invoice_number(invoice_number)}"


def _stored_type(invoice: EFaturaInvoice) -> str:
    if invoice.document_type in _CONCRETE_AT_TYPES:
        return invoice.document_type
    return "unclassified"


def _new_purchase(
    db: Session,
    *,
    user_id: str,
    source_key: str,
    invoice: EFaturaInvoice,
    review_from: Optional[Document] = None,
) -> Document:
    status = "needs_review"
    deductible_pct_override = None
    # A confirmed scan keeps its category and deductible review. An unconfirmed
    # scan does not: the AT row's category stays empty, matching migration 011.
    if review_from is not None and review_from.status in ("ready", "accountant_review"):
        status = review_from.status
        expense_category = review_from.expense_category
        irs_sector = review_from.irs_sector
        deductible_pct_override = review_from.deductible_pct_override
    elif review_from is not None:
        expense_category = None
        irs_sector = None
    else:
        expense_category, irs_sector = categorize_document(invoice.issuer_name, invoice.issuer_nif)
    document = Document(
        id=str(uuid.uuid4()),
        user_id=user_id,
        status=status,
        storage_key=f"efatura/{user_id}/{source_key}",
        original_filename=_safe_filename(invoice.invoice_number),
        mime_type="application/vnd.invoflow.efatura+json",
        file_size=None,
        vendor_nif=invoice.issuer_nif,
        vendor_name=invoice.issuer_name,
        invoice_number=invoice.invoice_number,
        document_type=_stored_type(invoice),
        at_document_type=invoice.document_type,
        at_invoice_identity=at_invoice_identity(
            invoice.issuer_nif, _stored_type(invoice), invoice.invoice_number
        ),
        document_date=invoice.issue_date,
        net_amount=_non_negative(invoice.net_total),
        gross_amount=_non_negative(invoice.gross_total),
        vat_amount=_iva_amount(invoice),
        vat_rate=_single_vat_rate(invoice),
        ocr_confidence=None,
        ocr_raw_response='{"source":"efatura"}',
        deductible_pct_override=deductible_pct_override,
        expense_category=expense_category,
        irs_sector=irs_sector,
    )
    db.add(document)
    db.flush()
    log_event(
        db,
        entity_type="document",
        entity_id=document.id,
        user_id=user_id,
        action="create",
        source="efatura",
    )
    log_auto_categorize(
        db,
        document_id=document.id,
        user_id=user_id,
        expense_category=expense_category,
        irs_sector=irs_sector,
    )
    return document


def _add_link(
    db: Session,
    *,
    user_id: str,
    source_key: str,
    role: str,
    outcome: str,
    document_id: Optional[str],
    fiscal_status: str,
    warning: Optional[str],
    payload: str,
) -> EfaturaLink:
    link = EfaturaLink(
        id=str(uuid.uuid4()),
        user_id=user_id,
        source_key=source_key,
        role=role,
        outcome=outcome,
        document_id=document_id,
        fiscal_status=fiscal_status,
        warning=warning,
        payload_json=payload,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(link)
    return link


def _retire_printed_pair(db: Session, document_id: Optional[str], arriving_type: Optional[str]) -> None:
    """A refreshed e-Fatura snapshot is still an AT pair, so the printed flag ends."""
    if not document_id:
        return
    document = db.get(Document, document_id)
    if document is None:
        return
    drop_accepted_series_mismatch(db, document, arriving_type, source="efatura")


_LINKED_SCAN_OUTCOMES = frozenset({"linked_existing", "linked_hidden"})


def _is_scan(document: Document) -> bool:
    """A photo or PDF, not the AT row this importer stores."""
    if (document.mime_type or "").startswith("application/vnd.invoflow.efatura"):
        return False
    raw = document.ocr_raw_response or ""
    return '"source":"efatura"' not in raw and '"source": "efatura"' not in raw


def _visible_link_target(db: Session, link: EfaturaLink) -> Optional[Document]:
    if not link.document_id:
        return None
    document = db.get(Document, link.document_id)
    if document is None or document.deleted_at is not None:
        return None
    return document


def _identity_row(
    db: Session,
    user_id: str,
    identity: str,
    *,
    live: bool,
) -> Optional[Document]:
    query = db.query(Document).filter(
        Document.user_id == user_id,
        Document.at_invoice_identity == identity,
    )
    if live:
        query = query.filter(Document.deleted_at.is_(None))
    else:
        query = query.filter(Document.deleted_at.isnot(None))
    return query.order_by(Document.created_at.asc()).with_for_update().first()


def _place_at_invoice(
    db: Session,
    link: EfaturaLink,
    invoice: EFaturaInvoice,
    scan: Optional[Document],
) -> tuple[Document, bool]:
    """Return the one AT row for this invoice, creating it only when none exists.

    A deleted AT row stays deleted. A second link for the same nif, type and
    number attaches to the row the first link already has. ``created`` is true
    only when this call inserted that row.
    """
    identity = at_invoice_identity(invoice.issuer_nif, _stored_type(invoice), invoice.invoice_number)
    live = _identity_row(db, link.user_id, identity, live=True)
    if live is not None:
        return live, False
    deleted = _identity_row(db, link.user_id, identity, live=False)
    if deleted is not None:
        return deleted, False
    try:
        with db.begin_nested():
            document = _new_purchase(
                db,
                user_id=link.user_id,
                source_key=link.source_key,
                invoice=invoice,
                review_from=scan,
            )
    except IntegrityError:
        db.expire_all()
        live = _identity_row(db, link.user_id, identity, live=True)
        if live is not None:
            return live, False
        deleted = _identity_row(db, link.user_id, identity, live=False)
        if deleted is not None:
            return deleted, False
        raise
    return document, True


def _log_unlink(
    db: Session,
    scan: Document,
    at_row: Document,
    source_key: str,
    audit_source: str,
) -> None:
    log_event(
        db,
        entity_type="document",
        entity_id=scan.id,
        user_id=scan.user_id,
        action="efatura_unlink",
        source=audit_source,
        changes={
            "efatura_document_id": {"old": scan.id, "new": at_row.id},
            "source_key": {"old": None, "new": source_key},
            "invoice_number": {"old": scan.invoice_number, "new": at_row.invoice_number},
        },
    )


def restore_orphaned_link(
    db: Session,
    link: EfaturaLink,
    invoice: EFaturaInvoice,
    *,
    audit_source: str,
    write_audit: bool = True,
) -> Optional[tuple[Document, bool]]:
    """Move one link off a deleted scan onto the single AT row for that invoice.

    A live target is left alone. A deleted e-Fatura document stays deleted:
    only a deleted scan is restored. Returns ``(row, created_new)``.
    """
    if _visible_link_target(db, link) is not None:
        return None
    if link.outcome not in _LINKED_SCAN_OUTCOMES and link.outcome != "created":
        return None
    previous = db.get(Document, link.document_id) if link.document_id else None
    if previous is None or previous.deleted_at is None or not _is_scan(previous):
        return None
    role: PartyRole = link.role if link.role in ("acquirer", "issuer", "not_party") else "acquirer"
    reason = _skip_reason(invoice, role)
    if reason == "cancelled":
        logger.warning("e-Fatura link %s skipped; invoice is cancelled", link.id)
        return None
    if reason is not None:
        return None
    document, created_new = _place_at_invoice(db, link, invoice, previous)
    link.document_id = document.id
    link.outcome = "created"
    link.warning = None
    link.updated_at = datetime.utcnow()
    if created_new and write_audit:
        _log_unlink(db, previous, document, link.source_key, audit_source)
    return document, created_new


def detach_deleted_scan(db: Session, document: Document) -> None:
    """Deleting a linked scan must not drop the AT invoice from the totals.

    Every link on the scan is moved. Links for the same invoice share one AT
    row, and the scan gets one ``efatura_unlink`` entry.
    """
    if document.deleted_at is None or not _is_scan(document):
        return
    links = (
        db.query(EfaturaLink)
        .filter(
            EfaturaLink.user_id == document.user_id,
            EfaturaLink.document_id == document.id,
        )
        .order_by(EfaturaLink.id)
        .with_for_update()
        .all()
    )
    moved_to: Optional[Document] = None
    source_key = ""
    for link in links:
        try:
            invoice = _parse_invoice(json.loads(link.payload_json))
        except (TypeError, ValueError, json.JSONDecodeError):
            logger.warning(
                "e-Fatura link %s skipped; payload is not readable",
                link.id,
            )
            continue
        restored = restore_orphaned_link(
            db, link, invoice, audit_source="user", write_audit=False
        )
        if restored is None:
            continue
        row, _created_new = restored
        if moved_to is None:
            moved_to = row
            source_key = link.source_key
    if moved_to is not None:
        _log_unlink(db, document, moved_to, source_key, "user")


def is_pg_deadlock(exc: BaseException) -> bool:
    """True for Postgres deadlock (40P01) and serialization failure (40001)."""
    orig = getattr(exc, "orig", None)
    code = getattr(orig, "pgcode", None) or getattr(orig, "sqlstate", None)
    if code in {"40P01", "40001"}:
        return True
    return type(orig).__name__ in {"DeadlockDetected", "SerializationFailure"}


def _lock_documents_then_links(db: Session, document_ids, link_ids) -> None:
    """Canonical lock order: document ids ascending, then link ids ascending."""
    for document_id in sorted({document_id for document_id in document_ids if document_id}):
        db.query(Document).filter(Document.id == document_id).with_for_update().one()
    for link_id in sorted({link_id for link_id in link_ids if link_id}):
        db.query(EfaturaLink).filter(EfaturaLink.id == link_id).with_for_update().one()


def _source_key(invoice: EFaturaInvoice) -> str:
    if invoice.atcud:
        return f"atcud:{invoice.atcud}"
    number = invoice.invoice_number.strip().lower()
    return f"doc:{invoice.issuer_nif}:{invoice.document_type}:{number}"


def _link_by_key(db: Session, user_id: str, source_key: str) -> Optional[EfaturaLink]:
    return (
        db.query(EfaturaLink)
        .filter(EfaturaLink.user_id == user_id, EfaturaLink.source_key == source_key)
        .one_or_none()
    )


def _resolve_source_key(
    db: Session, user_id: str, invoice: EFaturaInvoice
) -> tuple[str, Optional[EfaturaLink]]:
    """The link key for this invoice and the link that already holds it.

    A doc key lowercases the number, so 'FT A/5' and 'FT a/5' share one. When
    that key holds a different invoice, this one keeps its number's case.
    """
    source_key = _source_key(invoice)
    existing = _link_by_key(db, user_id, source_key)
    if invoice.atcud or existing is None:
        return source_key, existing
    payload = _payload_number(existing)
    if payload is None or normalise_invoice_number(payload[1]) == normalise_invoice_number(
        invoice.invoice_number
    ):
        return source_key, existing
    exact_key = f"doc:{invoice.issuer_nif}:{invoice.document_type}:{invoice.invoice_number.strip()}"
    return exact_key, _link_by_key(db, user_id, exact_key)


def _role(invoice: EFaturaInvoice, taxpayer_nif: str) -> PartyRole:
    if invoice.acquirer_nif == taxpayer_nif:
        return "acquirer"
    if invoice.issuer_nif == taxpayer_nif:
        return "issuer"
    return "not_party"


def _iva_lines(invoice: EFaturaInvoice) -> list[VatLine]:
    return [line for line in invoice.lines if line.tax_type == "IVA"]


def _iva_sum(invoice: EFaturaInvoice) -> Optional[Decimal]:
    lines = _iva_lines(invoice)
    if not lines:
        return None
    return sum((line.tax for line in lines), Decimal("0"))


def _iva_amount(invoice: EFaturaInvoice) -> Decimal:
    total = _iva_sum(invoice)
    if total is None:
        return Decimal("0.00")
    return total.quantize(_CENT)


def _single_vat_rate(invoice: EFaturaInvoice) -> Optional[Decimal]:
    taxed = [line for line in _iva_lines(invoice) if line.tax > 0]
    if len(taxed) == 1 and taxed[0].percentage is not None:
        return taxed[0].percentage.quantize(_CENT)
    return None


def _amounts_missing(invoice: EFaturaInvoice) -> bool:
    return invoice.gross_total is None and invoice.net_total is None and _iva_sum(invoice) is None


def _skip_reason(invoice: EFaturaInvoice, role: PartyRole) -> Optional[str]:
    if role == "issuer":
        return "issuer"
    if role == "not_party":
        return "not_party"
    if invoice.fiscal_status == "cancelled":
        return "cancelled"
    if invoice.document_type == "NC":
        return "credit_note"
    iva = _iva_sum(invoice)
    if iva is not None and iva < 0:
        return "negative_iva"
    if _amounts_missing(invoice):
        return "incomplete"
    storable = invoice.document_type in _STORABLE_TYPES or invoice.document_type in _REVIEW_TYPES
    if not storable or invoice.fiscal_status not in _STORABLE_FISCAL:
        return "not_storable"
    return None


_INVOICE_FAMILY = frozenset({"FT", "FS", "FR"})


def _type_compatible(document: Document, invoice: EFaturaInvoice) -> bool:
    """An imported FT must not link to an NC or ND row.

    Unclassified rows still match. FT, FS and FR match each other. NC matches
    NC and ND matches ND.
    """
    stored = (document.document_type or "unclassified").strip().upper()
    incoming = (invoice.document_type or "").strip().upper()
    if stored in ("", "UNCLASSIFIED"):
        return True
    if stored in _INVOICE_FAMILY and incoming in _INVOICE_FAMILY:
        return True
    return stored == incoming


def _matched_same_invoice(document: Document, invoice: EFaturaInvoice) -> bool:
    """A numbered row links only when it is this invoice.

    An unnumbered scan matched by date and amount stays a link. ATCUD is the
    same invoice even when the printed number differs. A scan may also match
    on the looser scan key. A different number is stored on its own row
    instead of being reported as a link and dropped.
    """
    if invoice.atcud and _qr_atcud(document) == invoice.atcud:
        return True
    if not (document.invoice_number or "").strip():
        return True
    if normalise_nif(document.vendor_nif) != normalise_nif(invoice.issuer_nif):
        return False
    if normalise_invoice_number(document.invoice_number) == normalise_invoice_number(
        invoice.invoice_number
    ):
        return True
    return _is_scan(document) and _scan_number(document.invoice_number) == _scan_number(
        invoice.invoice_number
    )


@dataclass(frozen=True)
class _KnownInvoice:
    nif: str
    number: str
    glue: str


def _known_invoice(nif: Optional[str], number: Optional[str]) -> Optional[_KnownInvoice]:
    if not (number or "").strip():
        return None
    return _KnownInvoice(normalise_nif(nif), normalise_invoice_number(number), _glue_key(number))


def _known_at_invoices(
    db: Session, user_id: str, invoices: Sequence[EFaturaInvoice]
) -> set[_KnownInvoice]:
    """Every AT invoice this account has seen: this pull, AT rows and link payloads."""
    known: set[_KnownInvoice] = set()
    for invoice in invoices:
        entry = _known_invoice(invoice.issuer_nif, invoice.invoice_number)
        if entry:
            known.add(entry)
    for document in db.query(Document).filter(Document.user_id == user_id).all():
        if _is_scan(document):
            continue
        entry = _known_invoice(document.vendor_nif, document.invoice_number)
        if entry:
            known.add(entry)
    for link in db.query(EfaturaLink).filter(EfaturaLink.user_id == user_id).all():
        payload = _payload_number(link)
        if payload is not None:
            entry = _known_invoice(*payload)
            if entry:
                known.add(entry)
    return known


def _payload_number(link: EfaturaLink) -> Optional[tuple[Optional[str], Optional[str]]]:
    try:
        payload = json.loads(link.payload_json or "")
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    nif, number = payload.get("issuer_nif"), payload.get("invoice_number")
    if not isinstance(nif, str) or not isinstance(number, str):
        return None
    return nif, number


def _unsafe_link_warning(
    db: Session,
    document: Document,
    invoice: EFaturaInvoice,
    known: set[_KnownInvoice],
) -> Optional[str]:
    """Why this scan must not be linked to this invoice, or None.

    A scan already linked to a different AT invoice is not linked to a second
    one. A scan whose number matched only on the looser key, is written
    without an upper case letter, or has its code glued to two or more
    characters is not linked when another AT invoice from the same supplier
    reads the same with its spaces and case dropped. The invoice is then
    stored on its own row for review.
    """
    if not _is_scan(document):
        return None
    if invoice.atcud and _qr_atcud(document) == invoice.atcud:
        return None
    nif = normalise_nif(invoice.issuer_nif)
    number = normalise_invoice_number(invoice.invoice_number)
    for link in db.query(EfaturaLink).filter(EfaturaLink.document_id == document.id).all():
        payload = _payload_number(link)
        if payload is None:
            continue
        if (normalise_nif(payload[0]), normalise_invoice_number(payload[1])) != (nif, number):
            return (
                f"Not linked to receipt {document.id}: it is already linked to another "
                "e-Fatura document. Review both."
            )
    printed = document.invoice_number or ""
    if not printed.strip():
        return None
    exact = normalise_invoice_number(printed) == number and _keeps_case(printed)
    if exact and not _reads_two_ways(printed):
        return None
    glue = _glue_key(printed)
    for other in known:
        if other.nif == nif and other.number != number and other.glue == glue:
            return (
                f"Not linked to receipt {document.id}: its number could also be another "
                "e-Fatura document from this supplier. Review both."
            )
    return None


def _release_loose_links(db: Session, document: Document, invoice: EFaturaInvoice) -> None:
    """Move invoices that match this receipt only on the looser key to their own AT rows.

    The receipt's number is this invoice's exactly, so 'FT a/5', linked to a
    scan of 'FT A/5' before 'FT A/5' was known, is not the receipt's. Main's
    shared doc key left the same state on AT rows and scans. Each moved
    invoice goes to its AT row, or a new one in review, with a warning.
    """
    printed = document.invoice_number or ""
    nif = normalise_nif(document.vendor_nif)
    number = normalise_invoice_number(printed)
    if _is_scan(document) and not _keeps_case(printed):
        return
    if nif != normalise_nif(invoice.issuer_nif) or number != normalise_invoice_number(
        invoice.invoice_number
    ):
        return
    links = (
        db.query(EfaturaLink)
        .filter(EfaturaLink.document_id == document.id)
        .order_by(EfaturaLink.id)
        .with_for_update()
        .all()
    )
    for link in links:
        try:
            other = _parse_invoice(json.loads(link.payload_json))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if normalise_nif(other.issuer_nif) != nif:
            continue
        if normalise_invoice_number(other.invoice_number) == number:
            continue
        if _scan_number(other.invoice_number) != _scan_number(printed):
            continue
        if other.atcud and _qr_atcud(document) == other.atcud:
            continue
        row, _created = _place_at_invoice(db, link, other, None)
        link.document_id = row.id
        link.outcome = "created"
        link.warning = (
            f"Moved off receipt {document.id}: the receipt's number is another "
            "e-Fatura document. Review both."
        )
        link.updated_at = datetime.utcnow()
        _log_unlink(db, document, row, link.source_key, "efatura")
    db.flush()


_REVIEW_RECEIPT = re.compile(r"\b[Rr]eceipt (?P<id>[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})\b.*Review both\.$")


def review_receipt_id(warning: Optional[str]) -> Optional[str]:
    """The receipt a review warning names, or None for any other warning."""
    match = _REVIEW_RECEIPT.search(warning or "")
    return match.group("id") if match else None


def _similar_scan_warning(db: Session, user_id: str, invoice: EFaturaInvoice) -> Optional[str]:
    """A live scan whose glued number could also be this invoice, or None.

    Catches a scan that an earlier pull linked to the supplier's other
    invoice: 'FRA2026/12' linked to 'FR A2026/12' before 'FRA 2026/12' arrived.
    """
    nif = normalise_nif(invoice.issuer_nif)
    number = normalise_invoice_number(invoice.invoice_number)
    glue = _glue_key(invoice.invoice_number)
    for document in (
        db.query(Document)
        .filter(Document.user_id == user_id, Document.deleted_at.is_(None))
        .order_by(Document.created_at.asc(), Document.id.asc())
        .all()
    ):
        printed = document.invoice_number or ""
        if not _is_scan(document) or not printed.strip():
            continue
        if normalise_nif(document.vendor_nif) != nif or not _reads_two_ways(printed):
            continue
        if _glue_key(printed) == glue and normalise_invoice_number(printed) != number:
            return (
                f"Receipt {document.id} has a number that could also be this e-Fatura "
                "document. Review both."
            )
    return None


def _match_documents(db: Session, user_id: str, invoice: EFaturaInvoice) -> list[Document]:
    documents = [
        document
        for document in db.query(Document)
        .filter(Document.user_id == user_id, Document.deleted_at.is_(None))
        .all()
        if _type_compatible(document, invoice)
    ]
    if invoice.atcud:
        by_atcud = [document for document in documents if _qr_atcud(document) == invoice.atcud]
        if by_atcud:
            return by_atcud

    number = normalise_invoice_number(invoice.invoice_number)
    incoming_nif = normalise_nif(invoice.issuer_nif)
    if number:
        by_number = [
            document
            for document in documents
            if normalise_nif(document.vendor_nif) == incoming_nif
            and document.invoice_number
            and normalise_invoice_number(document.invoice_number) == number
        ]
        if by_number:
            return by_number
        loose = _scan_number(invoice.invoice_number)
        by_scan_number = [
            document
            for document in documents
            if _is_scan(document)
            and normalise_nif(document.vendor_nif) == incoming_nif
            and document.invoice_number
            and _scan_number(document.invoice_number) == loose
        ]
        if by_scan_number:
            return by_scan_number

    matched: list[Document] = []
    for document in documents:
        if normalise_nif(document.vendor_nif) != normalise_nif(invoice.issuer_nif):
            continue
        if document.invoice_number and document.invoice_number.strip():
            continue
        if document.document_date != invoice.issue_date:
            continue
        if document.gross_amount is None or invoice.gross_total is None:
            continue
        if abs(Decimal(document.gross_amount) - invoice.gross_total) <= _GROSS_TOLERANCE:
            matched.append(document)
    return matched


def _qr_atcud(document: Document) -> Optional[str]:
    raw = document.ocr_raw_response
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    qr = payload.get("qr")
    if not isinstance(qr, dict):
        return None
    atcud = qr.get("atcud")
    if isinstance(atcud, str) and atcud:
        return atcud
    return None


def _non_negative(value: Optional[Decimal]) -> Optional[Decimal]:
    if value is None or value < 0:
        return None
    return value.quantize(_CENT)


def _safe_filename(invoice_number: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", invoice_number.strip()) or "invoice"
    suffix = ".efatura"
    return cleaned[: 255 - len(suffix)] + suffix


def _payload(invoice: EFaturaInvoice) -> str:
    return json.dumps(asdict(invoice), default=_json_default, separators=(",", ":"))


def _json_default(value: object) -> str:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, date):
        return value.isoformat()
    raise TypeError(f"Cannot encode {type(value).__name__}")


def _decimal_or_none(value: object) -> Optional[Decimal]:
    if value is None or value == "":
        return None
    return Decimal(str(value))


def _parse_line(row: dict) -> VatLine:
    percentage = row.get("percentage")
    return VatLine(
        tax_type=str(row["tax_type"]),
        region=str(row.get("region") or ""),
        tax_code=str(row.get("tax_code") or ""),
        percentage=None if percentage is None else Decimal(str(percentage)),
        taxable=Decimal(str(row["taxable"])),
        tax=Decimal(str(row["tax"])),
        exemption_code=row.get("exemption_code"),
    )


def _parse_invoice(row: dict) -> EFaturaInvoice:
    if not isinstance(row, dict):
        raise ValueError("e-Fatura fixture row must be an object")
    document_type = row.get("document_type")
    fiscal_status = row.get("fiscal_status")
    if document_type not in _DOCUMENT_TYPES:
        raise ValueError(f"unsupported document type: {document_type}")
    if fiscal_status not in _FISCAL_STATUSES:
        raise ValueError(f"unsupported fiscal status: {fiscal_status}")
    invoice_number = row.get("invoice_number")
    issuer_nif = row.get("issuer_nif")
    if not isinstance(invoice_number, str) or not invoice_number.strip():
        raise ValueError("invoice number is required")
    if not isinstance(issuer_nif, str) or not issuer_nif.strip():
        raise ValueError("issuer NIF is required")
    lines = row.get("lines") or []
    if not isinstance(lines, list):
        raise ValueError("lines must be a list")
    atcud = row.get("atcud")
    issuer_name = row.get("issuer_name")
    acquirer_nif = row.get("acquirer_nif")
    return EFaturaInvoice(
        document_type=document_type,
        invoice_number=invoice_number,
        issue_date=date.fromisoformat(str(row["issue_date"])),
        issuer_nif=issuer_nif,
        acquirer_nif=None if acquirer_nif is None else str(acquirer_nif),
        acquirer_country=row.get("acquirer_country"),
        fiscal_status=fiscal_status,
        lines=tuple(_parse_line(line) for line in lines),
        tax_payable=_decimal_or_none(row.get("tax_payable")),
        net_total=_decimal_or_none(row.get("net_total")),
        gross_total=_decimal_or_none(row.get("gross_total")),
        atcud=None if atcud is None else str(atcud),
        issuer_name=None if issuer_name is None else str(issuer_name),
    )

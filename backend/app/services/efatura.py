"""e-Fatura pull.

Public surface: InvoiceQuery, EFaturaInvoice, EFaturaClient, build_efatura_client,
import_purchases. Adapters return domain invoices. The importer writes new
purchases and link rows.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal, Optional, Protocol, Sequence

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.efatura import EfaturaLink, EfaturaSubject
from app.services.audit import log_auto_categorize, log_event
from app.services.categorization import categorize_document

DocumentType = Literal["FT", "FS", "FR", "NC", "ND"]
FiscalStatus = Literal["normal", "cancelled", "invoiced"]
PartyRole = Literal["acquirer", "issuer", "not_party"]

_DOCUMENT_TYPES = ("FT", "FS", "FR", "NC", "ND")
_FISCAL_STATUSES = ("normal", "cancelled", "invoiced")
_STORABLE_TYPES = ("FT", "FS", "FR", "ND")
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
) -> ImportResult:
    """Store acquirer purchases on Document and record every row on a link.

    The caller commits. This function flushes and uses a savepoint per invoice.
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

    for invoice in invoices:
        try:
            with db.begin_nested():
                outcome = _import_one(db, user_id=user_id, taxpayer_nif=taxpayer_nif, invoice=invoice)
                db.flush()
        except IntegrityError:
            link = (
                db.query(EfaturaLink)
                .filter(
                    EfaturaLink.user_id == user_id,
                    EfaturaLink.source_key == _source_key(invoice),
                )
                .one_or_none()
            )
            unchanged.append(_source_key(invoice) if link is None else link.source_key)
            continue

        if outcome.kind == "created" and outcome.document_id:
            created.append(outcome.document_id)
        elif outcome.kind == "linked" and outcome.document_id:
            linked_existing.append(outcome.document_id)
        elif outcome.kind == "unchanged":
            unchanged.append(outcome.source_key)
        elif outcome.kind == "skipped":
            skipped.append(Skipped(outcome.source_key, outcome.outcome, outcome.warning))
        if outcome.warning and outcome.kind in ("linked", "skipped", "unchanged"):
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
) -> _Outcome:
    source_key = _source_key(invoice)
    existing = (
        db.query(EfaturaLink)
        .filter(EfaturaLink.user_id == user_id, EfaturaLink.source_key == source_key)
        .one_or_none()
    )
    payload = _payload(invoice)
    if existing is not None:
        warning = None
        if existing.fiscal_status != "cancelled" and invoice.fiscal_status == "cancelled":
            warning = _CANCELLED_WARNING
            existing.warning = warning
        existing.fiscal_status = invoice.fiscal_status
        existing.payload_json = payload
        existing.updated_at = datetime.utcnow()
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
        return _Outcome("linked", source_key, outcome, document.id, warning)

    document = _new_purchase(db, user_id=user_id, source_key=source_key, invoice=invoice)
    _add_link(
        db,
        user_id=user_id,
        source_key=source_key,
        role=role,
        outcome="created",
        document_id=document.id,
        fiscal_status=invoice.fiscal_status,
        warning=None,
        payload=payload,
    )
    return _Outcome("created", source_key, "created", document.id)


def _new_purchase(
    db: Session,
    *,
    user_id: str,
    source_key: str,
    invoice: EFaturaInvoice,
) -> Document:
    expense_category, irs_sector = categorize_document(invoice.issuer_name, invoice.issuer_nif)
    document = Document(
        id=str(uuid.uuid4()),
        user_id=user_id,
        status="needs_review",
        storage_key=f"efatura/{user_id}/{source_key}",
        original_filename=_safe_filename(invoice.invoice_number),
        mime_type="application/vnd.invoflow.efatura+json",
        file_size=None,
        vendor_nif=invoice.issuer_nif,
        vendor_name=invoice.issuer_name,
        invoice_number=invoice.invoice_number,
        document_date=invoice.issue_date,
        net_amount=_non_negative(invoice.net_total),
        gross_amount=_non_negative(invoice.gross_total),
        vat_amount=_iva_amount(invoice),
        vat_rate=_single_vat_rate(invoice),
        ocr_confidence=None,
        ocr_raw_response='{"source":"efatura"}',
        deductible_pct_override=None,
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


def _source_key(invoice: EFaturaInvoice) -> str:
    if invoice.atcud:
        return f"atcud:{invoice.atcud}"
    number = invoice.invoice_number.strip().lower()
    return f"doc:{invoice.issuer_nif}:{invoice.document_type}:{number}"


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
    if invoice.document_type not in _STORABLE_TYPES or invoice.fiscal_status not in _STORABLE_FISCAL:
        return "not_storable"
    return None


def _match_documents(db: Session, user_id: str, invoice: EFaturaInvoice) -> list[Document]:
    documents = db.query(Document).filter(Document.user_id == user_id).all()
    if invoice.atcud:
        by_atcud = [document for document in documents if _qr_atcud(document) == invoice.atcud]
        if by_atcud:
            return by_atcud

    number = invoice.invoice_number.strip().lower()
    if number:
        by_number = [
            document
            for document in documents
            if document.vendor_nif == invoice.issuer_nif
            and document.invoice_number
            and document.invoice_number.strip().lower() == number
        ]
        if by_number:
            return by_number

    matched: list[Document] = []
    for document in documents:
        if document.vendor_nif != invoice.issuer_nif:
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

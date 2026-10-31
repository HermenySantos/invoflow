"""Import e-Fatura purchases onto receipts without a network call."""

import json
import uuid
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.document import Document
from app.models.efatura import EfaturaLink
from app.models.user import User
from app.models.vat_sales import VatSalesEntry
from app.services.categorization import deductible_vat_split
from app.services.efatura import (
    EFaturaInvoice,
    FixtureEFaturaClient,
    InvoiceQuery,
    VatLine,
    import_purchases,
)

TAXPAYER = "555555555"
WIDE = InvoiceQuery(TAXPAYER, date(2020, 1, 1), date(2099, 12, 31))


def _user(db: Session) -> User:
    user = User(clerk_id=f"efatura-{uuid.uuid4().hex[:8]}", email="efatura@example.com")
    db.add(user)
    db.commit()
    return user


def _fixture() -> tuple[EFaturaInvoice, ...]:
    return FixtureEFaturaClient().fetch(WIDE)


def _photo(db: Session, user: User) -> Document:
    document = Document(
        user_id=user.id,
        status="ready",
        storage_key=f"{user.clerk_id}/2026/01/photo.jpg",
        original_filename="photo.jpg",
        mime_type="image/jpeg",
        vendor_name="Photo Shop",
        vendor_nif="500100144",
        invoice_number="ft a/123",
        document_date=date(2026, 1, 20),
        net_amount=Decimal("80.00"),
        vat_amount=Decimal("1.00"),
        gross_amount=Decimal("99.99"),
        vat_rate=Decimal("23.00"),
        ocr_raw_response=json.dumps({"text": "photo of a receipt", "qr": {"atcud": "PHOTO"}}),
        expense_category="food",
        irs_sector="geral",
    )
    db.add(document)
    db.commit()
    return document


def test_new_purchase_lands_as_needs_review_and_stays_out_of_the_payable(db: Session):
    user = _user(db)
    result = import_purchases(db, user_id=user.id, taxpayer_nif=TAXPAYER, invoices=_fixture())
    db.commit()

    created = [db.get(Document, document_id) for document_id in result.created]
    utility = next(document for document in created if document.vendor_nif == "123456002")
    assert utility.status == "needs_review"
    assert utility.status != "processing"
    assert utility.invoice_number == "FT LX/2026/1"
    assert "JF8K2M9X" not in utility.invoice_number
    assert utility.storage_key == f"efatura/{user.id}/atcud:JF8K2M9X-1"
    assert utility.original_filename.endswith(".efatura")
    assert utility.mime_type == "application/vnd.invoflow.efatura+json"
    assert utility.vat_amount == Decimal("26.00")
    assert utility.vat_rate is None
    assert json.loads(utility.ocr_raw_response) == {"source": "efatura"}
    assert "text" not in json.loads(utility.ocr_raw_response)
    # The name matches the utilities rule. The NIF is synthetic and is not in the map.
    assert utility.expense_category == "utilities"

    confirmed, pending = deductible_vat_split([utility])
    assert confirmed == Decimal("0.00")
    assert pending == utility.vat_amount

    again = import_purchases(db, user_id=user.id, taxpayer_nif=TAXPAYER, invoices=_fixture())
    db.commit()
    assert again.created == ()
    assert db.query(Document).filter(Document.user_id == user.id).count() == len(result.created)


def test_matching_scan_is_linked_and_not_overwritten(db: Session):
    user = _user(db)
    photo = _photo(db, user)
    before = {
        "vendor_name": photo.vendor_name,
        "vendor_nif": photo.vendor_nif,
        "invoice_number": photo.invoice_number,
        "gross_amount": photo.gross_amount,
        "vat_amount": photo.vat_amount,
        "ocr_raw_response": photo.ocr_raw_response,
        "status": photo.status,
    }

    result = import_purchases(db, user_id=user.id, taxpayer_nif=TAXPAYER, invoices=_fixture())
    db.commit()
    db.refresh(photo)

    assert photo.id in result.linked_existing
    assert photo.vendor_name == before["vendor_name"]
    assert photo.gross_amount == before["gross_amount"]
    assert photo.vat_amount == before["vat_amount"]
    assert photo.ocr_raw_response == before["ocr_raw_response"]
    assert photo.status == before["status"]
    link = (
        db.query(EfaturaLink)
        .filter(EfaturaLink.document_id == photo.id)
        .one()
    )
    assert link.outcome == "linked_existing"
    assert link.warning
    audit = (
        db.query(AuditLog)
        .filter(AuditLog.entity_id == photo.id, AuditLog.action == "efatura_duplicate")
        .one()
    )
    assert audit.source == "efatura"
    assert json.loads(audit.changes_json)["fields_copied"]["new"] is False


def test_issuer_credit_note_cancelled_and_empty_do_not_become_expenses(db: Session):
    user = _user(db)
    import_purchases(db, user_id=user.id, taxpayer_nif=TAXPAYER, invoices=_fixture())
    db.commit()

    numbers = {row.invoice_number for row in db.query(Document).all()}
    assert "FT SALE/1" not in numbers
    assert "NC 2026/1" not in numbers
    assert "FT CANCEL/1" not in numbers
    assert "FT EMPTY/1" not in numbers
    assert db.query(VatSalesEntry).count() == 0

    outcomes = {link.outcome for link in db.query(EfaturaLink).all()}
    assert {"issuer", "credit_note", "cancelled", "incomplete"} <= outcomes


def test_nif_starting_with_four_and_a_future_date_are_stored(db: Session):
    user = _user(db)
    import_purchases(db, user_id=user.id, taxpayer_nif=TAXPAYER, invoices=_fixture())
    db.commit()
    document = db.query(Document).filter(Document.vendor_nif == "412345678").one()
    assert document.vendor_nif.startswith("4")
    assert document.document_date > date.today()
    assert document.status == "needs_review"


def test_invoiced_purchase_is_stored_and_a_later_cancellation_does_not_hide_it(db: Session):
    user = _user(db)
    invoice = EFaturaInvoice(
        document_type="FT",
        invoice_number="FT INV/1",
        issue_date=date(2026, 2, 1),
        issuer_nif="500829993",
        acquirer_nif=TAXPAYER,
        acquirer_country="PT",
        fiscal_status="invoiced",
        lines=(
            VatLine("IVA", "PT", "NOR", Decimal("23.00"), Decimal("10.00"), Decimal("2.30"), None),
        ),
        tax_payable=Decimal("2.30"),
        net_total=Decimal("10.00"),
        gross_total=Decimal("12.30"),
        issuer_name="Pingo Doce",
    )
    first = import_purchases(db, user_id=user.id, taxpayer_nif=TAXPAYER, invoices=[invoice])
    db.commit()
    document = db.get(Document, first.created[0])
    assert document.status == "needs_review"

    cancelled = EFaturaInvoice(
        document_type=invoice.document_type,
        invoice_number=invoice.invoice_number,
        issue_date=invoice.issue_date,
        issuer_nif=invoice.issuer_nif,
        acquirer_nif=invoice.acquirer_nif,
        acquirer_country=invoice.acquirer_country,
        fiscal_status="cancelled",
        lines=invoice.lines,
        tax_payable=invoice.tax_payable,
        net_total=invoice.net_total,
        gross_total=invoice.gross_total,
        issuer_name=invoice.issuer_name,
    )
    second = import_purchases(db, user_id=user.id, taxpayer_nif=TAXPAYER, invoices=[cancelled])
    db.commit()
    db.refresh(document)
    assert second.unchanged
    assert document.deleted_at is None
    assert document.status == "needs_review"
    link = db.query(EfaturaLink).filter(EfaturaLink.document_id == document.id).one()
    assert link.fiscal_status == "cancelled"
    assert link.warning


def test_hidden_receipt_stays_hidden(db: Session):
    user = _user(db)
    photo = _photo(db, user)
    photo.deleted_at = datetime.utcnow()
    db.commit()
    result = import_purchases(db, user_id=user.id, taxpayer_nif=TAXPAYER, invoices=_fixture())
    db.commit()
    db.refresh(photo)
    assert photo.id not in result.linked_existing
    assert photo.id not in result.created
    assert photo.deleted_at is not None
    live = (
        db.query(Document)
        .filter(
            Document.user_id == user.id,
            Document.deleted_at.is_(None),
            Document.invoice_number == "FT A/123",
        )
        .one()
    )
    assert live.id != photo.id
    assert live.mime_type == "application/vnd.invoflow.efatura+json"
    link = db.query(EfaturaLink).filter(EfaturaLink.document_id == live.id).one()
    assert link.outcome == "created"
    assert db.query(EfaturaLink).filter(EfaturaLink.document_id == photo.id).count() == 0


def test_efatura_module_does_not_name_the_upload_or_sales_paths():
    source = Path("app/services/efatura.py").read_text(encoding="utf-8")
    for name in (
        "create_document",
        "OCRService",
        "process_document",
        "extract_fields",
        "VatSalesEntry",
        "read_receipt",
    ):
        assert name not in source
    lowered = source.lower()
    assert "zeep" not in lowered
    assert "import socket" not in lowered
    assert "urllib" not in lowered


def test_fixture_file_is_not_read_at_import():
    source = Path("app/services/efatura.py").read_text(encoding="utf-8")
    assert "purchases.json" not in source.split("def fetch", 1)[0]

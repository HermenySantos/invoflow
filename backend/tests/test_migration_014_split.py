"""Migration 014 splits rows the casefolded identity merged, and only those."""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.document import Document
from app.models.efatura import EfaturaLink
from app.services.efatura import _payload, import_purchases
from tests.test_efatura_import import TAXPAYER
from tests.test_gil160_linked_delete import _counted_vat, _purchase, _user, _visible
from tests.test_migration_014_identity import load_migration_014

NIF = "296123456"
AT_MIME = "application/vnd.invoflow.efatura+json"
FOLDED = f"{NIF}|FT|ft a/5"
UPPER = f"{NIF}|FT|ft A/5"
LOWER = f"{NIF}|FT|ft a/5"
BASE = datetime(2026, 4, 2, 9, 0, 0)


@pytest.fixture(scope="module")
def migration():
    return load_migration_014()


def _at_row(db: Session, user, number: str, identity: str, *, deleted=None, created=BASE) -> Document:
    row = Document(
        id=str(uuid.uuid4()),
        user_id=user.id,
        status="needs_review",
        storage_key=f"efatura/{user.id}/{number}",
        original_filename="at.efatura",
        mime_type=AT_MIME,
        vendor_nif=NIF,
        vendor_name="Loja",
        invoice_number=number,
        document_type="FT",
        at_document_type="FT",
        document_date=date(2026, 4, 1),
        net_amount=Decimal("10.00"),
        vat_amount=Decimal("2.30"),
        gross_amount=Decimal("12.30"),
        ocr_raw_response='{"source":"efatura"}',
        at_invoice_identity=identity,
        deleted_at=deleted,
        created_at=created,
        updated_at=created,
    )
    db.add(row)
    db.commit()
    return row


def _scan_row(db: Session, user, number: str) -> Document:
    row = Document(
        id=str(uuid.uuid4()),
        user_id=user.id,
        status="ready",
        storage_key=f"{user.id}/scan.jpg",
        original_filename="scan.jpg",
        mime_type="image/jpeg",
        vendor_nif=NIF,
        invoice_number=number,
        document_type="FT",
        document_date=date(2026, 4, 1),
        net_amount=Decimal("10.00"),
        vat_amount=Decimal("2.30"),
        gross_amount=Decimal("12.30"),
        ocr_raw_response=json.dumps({"text": "scan"}),
        created_at=BASE,
        updated_at=BASE,
    )
    db.add(row)
    db.commit()
    return row


def _link(
    db: Session, user, document: Document, number: str, key: str, *, outcome="created", at=BASE, vat="2.30"
):
    link = EfaturaLink(
        id=str(uuid.uuid4()),
        user_id=user.id,
        source_key=key,
        role="acquirer",
        outcome=outcome,
        document_id=document.id,
        fiscal_status="normal",
        payload_json=_payload(_purchase(number, vat=vat)),
        created_at=at,
        updated_at=at,
    )
    db.add(link)
    db.commit()
    return link


def _audit(db: Session, user, document: Document, action: str, source: str, changes: dict, at):
    db.add(
        AuditLog(
            entity_type="document",
            entity_id=document.id,
            user_id=user.id,
            action=action,
            source=source,
            changes_json=json.dumps(changes),
            created_at=at,
        )
    )
    db.commit()


def _run(db: Session, migration):
    counts = migration._apply(db.connection(), datetime(2026, 11, 3, 8, 0, 0))
    db.commit()
    db.expire_all()
    return counts


def _snapshot(db: Session):
    documents = sorted(
        (row.id, row.invoice_number, row.at_invoice_identity, row.deleted_at, row.updated_at, row.status)
        for row in db.query(Document).all()
    )
    links = sorted(
        (row.id, row.source_key, row.document_id, row.outcome, row.updated_at)
        for row in db.query(EfaturaLink).all()
    )
    audits = sorted((row.id, row.entity_id, row.action) for row in db.query(AuditLog).all())
    return documents, links, audits


def test_empty_database_writes_nothing(db: Session, migration):
    assert _run(db, migration) == (0, 0, 0)
    assert _snapshot(db) == ([], [], [])


def test_correct_database_writes_nothing(db: Session, migration):
    user, _headers = _user(db)
    upper = _at_row(db, user, "FT A/5", UPPER)
    lower = _at_row(db, user, "FT a/5", LOWER)
    _link(db, user, upper, "FT A/5", "atcud:U")
    _link(db, user, lower, "FT a/5", "atcud:L")
    scan = _scan_row(db, user, "ft a/5")
    _link(db, user, scan, "FT B/5", "atcud:B", outcome="linked_existing")
    before = _snapshot(db)
    assert _run(db, migration) == (0, 0, 0)
    assert _snapshot(db) == before


def test_merged_case_pair_splits_into_two_rows_and_a_second_run_writes_nothing(
    db: Session, migration
):
    user, _headers = _user(db)
    merged = _at_row(db, user, "FT A/5", FOLDED)
    own = _link(db, user, merged, "FT A/5", "atcud:UPPER")
    other = _link(db, user, merged, "FT a/5", "atcud:LOWER", outcome="linked_existing", at=BASE + timedelta(hours=1))
    assert _counted_vat(db, user) == [Decimal("2.30")]

    assert _run(db, migration) == (1, 0, 1)
    visible = {row.invoice_number: row for row in _visible(db, user)}
    assert set(visible) == {"FT A/5", "FT a/5"}
    assert visible["FT A/5"].id == merged.id
    assert visible["FT A/5"].at_invoice_identity == UPPER
    split = visible["FT a/5"]
    assert split.at_invoice_identity == LOWER
    assert split.status == "needs_review"
    assert split.mime_type == AT_MIME
    assert split.vat_amount == Decimal("2.30")
    assert db.get(EfaturaLink, own.id).document_id == merged.id
    moved = db.get(EfaturaLink, other.id)
    assert (moved.document_id, moved.outcome) == (split.id, "created")
    audit = db.query(AuditLog).filter(AuditLog.action == "efatura_split").one()
    assert audit.entity_id == split.id
    body = json.loads(audit.changes_json)
    assert body["split_from_document_id"]["new"] == merged.id
    assert body["source_keys"]["new"] == ["atcud:LOWER"]
    assert _counted_vat(db, user) == [Decimal("2.30"), Decimal("2.30")]

    after = _snapshot(db)
    assert _run(db, migration) == (0, 0, 0)
    assert _snapshot(db) == after


def test_row_deleted_as_a_case_duplicate_is_restored_with_its_links(db: Session, migration):
    user, _headers = _user(db)
    keeper = _at_row(db, user, "FT A/5", FOLDED)
    dropped = _at_row(db, user, "FT a/5", FOLDED, deleted=BASE + timedelta(hours=2))
    _link(db, user, keeper, "FT A/5", "atcud:K")
    moved = _link(db, user, keeper, "FT a/5", "atcud:D")
    _audit(db, user, dropped, "create", "efatura", {}, BASE)
    _audit(
        db,
        user,
        dropped,
        "efatura_dedupe",
        "efatura",
        {"kept_document_id": {"old": None, "new": keeper.id}},
        BASE + timedelta(hours=2),
    )

    assert _run(db, migration) == (1, 1, 0)
    restored = db.get(Document, dropped.id)
    assert restored.deleted_at is None
    assert restored.at_invoice_identity == LOWER
    assert db.get(EfaturaLink, moved.id).document_id == dropped.id
    assert sorted(row.invoice_number for row in _visible(db, user)) == ["FT A/5", "FT a/5"]
    assert _counted_vat(db, user) == [Decimal("2.30"), Decimal("2.30")]
    after = _snapshot(db)
    assert _run(db, migration) == (0, 0, 0)
    assert _snapshot(db) == after


def test_row_a_user_deleted_stays_deleted_and_takes_its_links(db: Session, migration):
    user, _headers = _user(db)
    keeper = _at_row(db, user, "FT A/5", FOLDED)
    deleted = _at_row(db, user, "FT a/5", None, deleted=BASE + timedelta(hours=3))
    _link(db, user, keeper, "FT A/5", "atcud:K")
    moved = _link(db, user, keeper, "FT a/5", "atcud:D", outcome="linked_existing")
    _audit(db, user, deleted, "delete", "user", {}, BASE + timedelta(hours=3))

    assert _run(db, migration) == (2, 0, 0)
    assert db.get(Document, deleted.id).deleted_at is not None
    assert db.get(EfaturaLink, moved.id).document_id == deleted.id
    assert [row.id for row in _visible(db, user)] == [keeper.id]


def test_scan_linked_to_two_invoices_keeps_its_own_and_splits_the_other(db: Session, migration):
    user, _headers = _user(db)
    scan = _scan_row(db, user, "FT a/5")
    wrong = _link(db, user, scan, "FT A/5", "atcud:U", outcome="linked_existing")
    right = _link(db, user, scan, "FT a/5", "atcud:L", outcome="linked_existing", at=BASE + timedelta(hours=1))

    assert _run(db, migration) == (0, 0, 1)
    assert db.get(EfaturaLink, right.id).document_id == scan.id
    split = db.get(Document, db.get(EfaturaLink, wrong.id).document_id)
    assert split.id != scan.id
    assert split.invoice_number == "FT A/5"
    assert split.at_invoice_identity == UPPER
    assert sorted(_counted_vat(db, user)) == [Decimal("2.30"), Decimal("2.30")]


@pytest.mark.parametrize("scan_number", ["ft a/5", "FT a/5", "FTA/5"])
def test_scan_with_one_invoice_is_left_alone(db: Session, migration, scan_number):
    user, _headers = _user(db)
    scan = _scan_row(db, user, scan_number)
    _link(db, user, scan, "FT A/5", "atcud:U", outcome="linked_existing")
    _link(db, user, scan, "FT A/5", "doc:296123456:FT:ft a/5", outcome="linked_existing")
    before = _snapshot(db)
    assert _run(db, migration) == (0, 0, 0)
    assert _snapshot(db) == before


def test_at_row_whose_number_was_edited_is_not_split(db: Session, migration):
    user, _headers = _user(db)
    edited = _at_row(db, user, "FT A/50", f"{NIF}|FT|ft A/50")
    _link(db, user, edited, "FT A/5", "atcud:E")
    before = _snapshot(db)
    assert _run(db, migration) == (0, 0, 0)
    assert _snapshot(db) == before


# U-A: on main, 'FT A/5' and 'FT a/5' without an ATCUD shared the doc key
# doc:<nif>:FT:ft a/5, so the second pull overwrote the link's payload. The
# link still points at the row or scan made for 'FT A/5'.
MAIN_DOC_KEY = f"doc:{NIF}:FT:ft a/5"


def _re_pull(db: Session, user, *numbers_and_vat):
    result = import_purchases(
        db,
        user_id=user.id,
        taxpayer_nif=TAXPAYER,
        invoices=[_purchase(number, vat=vat) for number, vat in numbers_and_vat],
    )
    db.commit()
    db.expire_all()
    return result


_BOTH_ORDERS = (
    (("FT A/5", "2.30"), ("FT a/5", "4.60")),
    (("FT a/5", "4.60"), ("FT A/5", "2.30")),
)


@pytest.mark.parametrize("order", _BOTH_ORDERS)
def test_main_doc_key_pair_without_a_scan_gives_one_row_per_invoice(db: Session, migration, order):
    user, _headers = _user(db)
    upper = _at_row(db, user, "FT A/5", FOLDED)
    _link(db, user, upper, "FT a/5", MAIN_DOC_KEY, vat="4.60")

    assert _run(db, migration) == (1, 0, 1)
    lower = next(row for row in _visible(db, user) if row.invoice_number == "FT a/5")
    assert lower.status == "needs_review"
    assert lower.vat_amount == Decimal("4.60")
    moved = db.query(EfaturaLink).filter(EfaturaLink.document_id == lower.id).one()
    assert upper.id in moved.warning

    for _ in range(2):
        again = _re_pull(db, user, *order)
        assert again.created == ()
        assert sorted((row.invoice_number, row.vat_amount) for row in _visible(db, user)) == [
            ("FT A/5", Decimal("2.30")),
            ("FT a/5", Decimal("4.60")),
        ]
        assert sorted(_counted_vat(db, user)) == [Decimal("2.30"), Decimal("4.60")]
    after = _snapshot(db)
    assert _run(db, migration) == (0, 0, 0)
    assert _snapshot(db) == after


@pytest.mark.parametrize("order", _BOTH_ORDERS)
def test_main_doc_key_pair_next_to_a_scan_is_not_counted_twice(db: Session, migration, order):
    user, _headers = _user(db)
    scan = _scan_row(db, user, "FT A/5")
    _link(db, user, scan, "FT a/5", MAIN_DOC_KEY, outcome="linked_existing", vat="4.60")

    _run(db, migration)
    for _ in range(2):
        _re_pull(db, user, *order)
        visible = _visible(db, user)
        at_rows = [row for row in visible if row.mime_type == AT_MIME]
        assert [row.invoice_number for row in at_rows] == ["FT a/5"]
        assert at_rows[0].status == "needs_review"
        assert sorted(_counted_vat(db, user)) == [Decimal("2.30"), Decimal("4.60")]
        scan_links = db.query(EfaturaLink).filter(EfaturaLink.document_id == scan.id).all()
        assert [json.loads(link.payload_json)["invoice_number"] for link in scan_links] == ["FT A/5"]
    lower_link = db.query(EfaturaLink).filter(EfaturaLink.document_id == at_rows[0].id).one()
    assert scan.id in lower_link.warning

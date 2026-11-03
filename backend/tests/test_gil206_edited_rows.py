"""GIL-206. A user's edit is never read as AT's number, and VAT is neither lost nor doubled."""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.document import Document
from app.models.efatura import EfaturaLink
from app.services.efatura import at_invoice_identity, review_receipt_id
from tests.test_gil160_linked_delete import _counted_vat, _purchase, _user, _visible
from tests.test_gil205_series_case import NIF, _at, _pull, _scan_numbered
from tests.test_migration_014_identity import load_migration_014
from tests.test_migration_014_split import LOWERCASED_DOC_KEY, _at_row, _link, _run

AT_MIME = "application/vnd.invoflow.efatura+json"
UPPER = at_invoice_identity(NIF, "FT", "FT A/5")
LOWER = at_invoice_identity(NIF, "FT", "FT a/5")
EXPECTED = [Decimal("2.30"), Decimal("4.60")]


def _patch(client: TestClient, headers, document_id: str, **fields):
    response = client.patch(f"/api/documents/{document_id}", headers=headers, json=fields)
    assert response.status_code == 200, response.text
    return response.json()


def _rows(db: Session, user):
    db.expire_all()
    return sorted((row.invoice_number, row.vat_amount) for row in _visible(db, user))


def _vat(db: Session, user) -> list[Decimal]:
    db.expire_all()
    return sorted(_counted_vat(db, user))


def _held_link(db: Session, document_id: str) -> EfaturaLink:
    return db.query(EfaturaLink).filter(EfaturaLink.document_id == document_id).one()


def _reviews(client: TestClient, headers) -> dict[str, dict]:
    listed = client.get("/api/documents", headers=headers)
    assert listed.status_code == 200, listed.text
    return {row["id"]: row["efatura_review"] for row in listed.json()["documents"]}


def _pair(atcud: bool):
    if atcud:
        return _at("FT A/5", "G-UPPER"), _at("FT a/5", "G-LOWER", vat="4.60")
    return _purchase("FT A/5"), _purchase("FT a/5", vat="4.60")


# G-1: FT a/5 (4.60) is stored, a user edits its number to FT A/5, then AT sends the real FT A/5 (2.30).


@pytest.mark.parametrize("atcud", [False, True], ids=["doc-key", "atcud"])
@pytest.mark.parametrize("upper_first", [True, False], ids=["upper-first", "lower-first"])
def test_g1_an_edited_at_number_is_not_an_exact_match(client, db: Session, atcud, upper_first):
    user, headers = _user(db)
    upper, lower = _pair(atcud)
    edited_id = _pull(db, user, lower).created[0]
    _patch(client, headers, edited_id, invoice_number="FT A/5")

    result = _pull(db, user, *((upper, lower) if upper_first else (lower, upper)))

    assert result.linked_existing == ()
    assert len(result.created) == 1
    held = db.get(Document, result.created[0])
    assert (held.invoice_number, held.vat_amount, held.status) == ("FT A/5", Decimal("2.30"), "needs_review")
    assert held.at_invoice_identity == UPPER
    assert review_receipt_id(_held_link(db, held.id).warning) == edited_id
    edited = db.get(Document, edited_id)
    assert (edited.invoice_number, edited.vat_amount) == ("FT A/5", Decimal("4.60"))
    assert edited.at_invoice_identity == LOWER
    assert _vat(db, user) == EXPECTED
    assert sum(_vat(db, user)) == Decimal("6.90")
    assert _reviews(client, headers)[held.id]["related_document_id"] == edited_id

    again = _pull(db, user, upper, lower)
    assert again.created == ()
    assert again.linked_existing == ()
    assert _vat(db, user) == EXPECTED


def test_g1_a_second_pull_after_the_hold_writes_nothing(client, db: Session):
    user, headers = _user(db)
    upper, lower = _pair(atcud=False)
    edited_id = _pull(db, user, lower).created[0]
    _patch(client, headers, edited_id, invoice_number="FT A/5")
    _pull(db, user, upper, lower)
    db.expire_all()
    before = sorted(
        (row.id, row.invoice_number, row.at_invoice_identity, row.updated_at) for row in db.query(Document)
    )
    audits = db.query(AuditLog).count()

    _pull(db, user, upper, lower)
    db.expire_all()
    after = sorted(
        (row.id, row.invoice_number, row.at_invoice_identity, row.updated_at) for row in db.query(Document)
    )
    assert after == before
    assert db.query(AuditLog).count() == audits


def test_g1_an_edit_that_keeps_the_identity_is_still_an_exact_match(client, db: Session):
    user, headers = _user(db)
    row_id = _pull(db, user, _at("FT A/5", "SAME")).created[0]
    _patch(client, headers, row_id, invoice_number="FTA/5")
    result = _pull(db, user, _at("FT A/5", "SAME-NEW-KEY"))
    assert result.created == ()
    assert result.linked_existing == (row_id,)
    assert _vat(db, user) == [Decimal("2.30")]


def test_g1_patch_onto_the_held_rows_number_is_still_409(client, db: Session):
    user, headers = _user(db)
    upper, lower = _pair(atcud=False)
    edited_id = _pull(db, user, lower).created[0]
    _patch(client, headers, edited_id, invoice_number="FT A/5")
    held_id = _pull(db, user, upper, lower).created[0]

    resaved = client.patch(
        f"/api/documents/{edited_id}", headers=headers, json={"invoice_number": "FT A/5", "status": "ready"}
    )
    assert resaved.status_code == 200, resaved.text
    respelled = client.patch(f"/api/documents/{edited_id}", headers=headers, json={"invoice_number": "FTA/5"})
    assert respelled.status_code == 409, respelled.text
    assert "FT A/5" in respelled.json()["detail"]
    assert _vat(db, user) == EXPECTED
    assert db.get(Document, held_id).vat_amount == Decimal("2.30")


def test_g1_two_rows_whose_numbers_a_user_swapped_both_keep_their_invoices(client, db: Session):
    user, headers = _user(db)
    upper, lower = _pair(atcud=True)
    created = _pull(db, user, upper, lower).created
    upper_id, lower_id = created
    _patch(client, headers, upper_id, invoice_number="FT X/5")
    _patch(client, headers, lower_id, invoice_number="FT A/5")
    _patch(client, headers, upper_id, invoice_number="FT a/5")

    result = _pull(db, user, upper, lower)
    assert result.created == ()
    db.expire_all()
    assert db.get(Document, upper_id).at_invoice_identity == UPPER
    assert db.get(Document, lower_id).at_invoice_identity == LOWER
    assert _vat(db, user) == EXPECTED


def test_g1_an_edited_row_that_cannot_get_its_identity_back_warns_instead_of_dropping(client, db: Session):
    user, headers = _user(db)
    edited_id = _pull(db, user, _at("FT a/5", "BLOCK-LOWER", vat="4.60")).created[0]
    _patch(client, headers, edited_id, invoice_number="FT A/5")
    _at_row(db, user, "FT a/5", LOWER)

    result = _pull(db, user, _at("FT A/5", "BLOCK-UPPER"))

    assert result.created == ()
    assert [(skip.source_key, skip.outcome) for skip in result.skipped] == [
        ("atcud:BLOCK-UPPER", "ambiguous_duplicate")
    ]
    assert review_receipt_id(result.skipped[0].warning) == edited_id
    assert db.get(Document, edited_id).at_invoice_identity == UPPER


# G-2: main merged FT A/5 (2.30) and FT a/5 (4.60) on one doc key; a user edited the row to FT a/5.


def _g2_state(client, db: Session):
    user, headers = _user(db)
    row = _at_row(db, user, "FT A/5", f"{NIF}|FT|ft a/5")
    _link(db, user, row, "FT a/5", LOWERCASED_DOC_KEY, vat="4.60")
    _patch(client, headers, row.id, invoice_number="FT a/5")
    _run(db, load_migration_014())
    return user, headers, row.id


@pytest.mark.parametrize("upper_first", [True, False], ids=["upper-first", "lower-first"])
def test_g2_edited_row_in_a_main_merged_pair_keeps_both_invoices(client, db: Session, upper_first):
    user, headers, edited_id = _g2_state(client, db)
    upper, lower = _pair(atcud=False)

    for _ in range(2):
        _pull(db, user, *((upper, lower) if upper_first else (lower, upper)))
        assert _vat(db, user) == EXPECTED
        assert sum(_vat(db, user)) == Decimal("6.90")
        assert _rows(db, user) == [("FT a/5", Decimal("2.30")), ("FT a/5", Decimal("4.60"))]

    edited = db.get(Document, edited_id)
    assert (edited.invoice_number, edited.vat_amount) == ("FT a/5", Decimal("2.30"))
    split = next(row for row in _visible(db, user) if row.id != edited_id)
    assert (split.status, split.mime_type, split.at_invoice_identity) == ("needs_review", AT_MIME, LOWER)
    moved = db.query(EfaturaLink).filter(EfaturaLink.source_key == LOWERCASED_DOC_KEY).one()
    assert moved.document_id == split.id
    assert review_receipt_id(moved.warning) == edited_id
    assert _reviews(client, headers)[split.id]["related_document_id"] == edited_id


def test_g2_a_pull_of_only_the_overwritten_invoice_splits_it_off(client, db: Session):
    user, headers, edited_id = _g2_state(client, db)
    _pull(db, user, _purchase("FT a/5", vat="4.60"))
    assert _vat(db, user) == EXPECTED
    split = next(row for row in _visible(db, user) if row.id != edited_id)
    assert review_receipt_id(_held_link(db, split.id).warning) == edited_id


def test_g2_a_case_only_edit_with_no_overwrite_keeps_one_row(client, db: Session):
    user, headers = _user(db)
    row = _at_row(db, user, "FT A/5", f"{NIF}|FT|ft a/5")
    _link(db, user, row, "FT A/5", LOWERCASED_DOC_KEY)
    _patch(client, headers, row.id, invoice_number="FT a/5")
    _run(db, load_migration_014())

    _pull(db, user, _purchase("FT A/5"))
    assert [link.document_id for link in db.query(EfaturaLink)] == [row.id]
    assert _rows(db, user) == [("FT a/5", Decimal("2.30"))]


# G-3: a user edited the amounts of a scan after it was linked on the loose key.


def _loosely_linked_scan(db: Session, user):
    scan = _scan_numbered(db, user, "FT A/5")
    assert _pull(db, user, _at("FT a/5", "G3-LOWER", vat="4.60")).linked_existing == (scan.id,)
    return scan


def test_g3_scan_amounts_edited_after_the_loose_link_hold_the_exact_invoice(client, db: Session):
    user, headers = _user(db)
    scan = _loosely_linked_scan(db, user)
    _patch(client, headers, scan.id, vat_amount="4.60", gross_amount="14.60")

    result = _pull(db, user, _at("FT A/5", "G3-UPPER"))

    assert result.linked_existing == ()
    held = db.get(Document, result.created[0])
    assert (held.invoice_number, held.status) == ("FT A/5", "needs_review")
    assert review_receipt_id(_held_link(db, held.id).warning) == scan.id
    scan_links = db.query(EfaturaLink).filter(EfaturaLink.document_id == scan.id).all()
    assert [link.source_key for link in scan_links] == ["atcud:G3-LOWER"]
    assert _vat(db, user) == EXPECTED
    assert sum(_vat(db, user)) == Decimal("6.90")


def test_g3_edited_vat_that_matches_the_exact_invoice_still_moves_the_loose_link(client, db: Session):
    user, headers = _user(db)
    scan = _loosely_linked_scan(db, user)
    _patch(client, headers, scan.id, vat_amount="4.60", gross_amount="14.60")
    _patch(client, headers, scan.id, vat_amount="2.30", gross_amount="12.30")
    result = _pull(db, user, _at("FT A/5", "G3-UPPER"))
    assert result.linked_existing == (scan.id,)
    assert _vat(db, user) == EXPECTED


def test_g3_amounts_edited_before_the_link_do_not_pin_it(client, db: Session):
    user, headers = _user(db)
    scan = _scan_numbered(db, user, "FT A/5")
    _patch(client, headers, scan.id, vat_amount="2.40", gross_amount="12.40")
    _pull(db, user, _at("FT a/5", "G3-LOWER", vat="4.60"))
    result = _pull(db, user, _at("FT A/5", "G3-UPPER"))
    assert result.linked_existing == (scan.id,)
    assert _vat(db, user) == [Decimal("2.40"), Decimal("4.60")]


# G-4: the real scan of FT a/5 arrives after FT a/5 was linked to the scan of FT A/5.


def test_g4_a_moved_loose_link_goes_to_the_real_scan_of_its_number(client, db: Session):
    user, headers = _user(db)
    first = _loosely_linked_scan(db, user)
    real = _scan_numbered(db, user, "FT a/5")
    real.vat_amount = Decimal("4.60")
    real.gross_amount = Decimal("14.60")
    db.commit()

    result = _pull(db, user, _at("FT A/5", "G4-UPPER"))

    assert result.created == ()
    assert result.linked_existing == (first.id,)
    assert all(row.mime_type != AT_MIME for row in _visible(db, user))
    moved = db.query(EfaturaLink).filter(EfaturaLink.source_key == "atcud:G3-LOWER").one()
    assert (moved.document_id, moved.outcome) == (real.id, "linked_existing")
    assert _vat(db, user) == EXPECTED
    assert _reviews(client, headers) == {first.id: None, real.id: None}

    again = _pull(db, user, _at("FT A/5", "G4-UPPER"), _at("FT a/5", "G3-LOWER", vat="4.60"))
    assert again.created == ()
    assert _vat(db, user) == EXPECTED


def test_g4_a_lowercase_ocr_scan_is_not_a_home_for_the_moved_link(db: Session):
    user, _headers = _user(db)
    first = _loosely_linked_scan(db, user)
    ocr = _scan_numbered(db, user, "ft a/5")

    result = _pull(db, user, _at("FT A/5", "G4-UPPER"))

    assert result.linked_existing == (first.id,)
    moved = db.query(EfaturaLink).filter(EfaturaLink.source_key == "atcud:G3-LOWER").one()
    assert moved.document_id not in (first.id, ocr.id)
    assert review_receipt_id(moved.warning) == first.id


# G-8: the type code's case says nothing about the series' case.


def test_g8_title_case_type_code_scan_is_held_when_both_cases_are_known(db: Session):
    user, _headers = _user(db)
    scan = _scan_numbered(db, user, "Ft a/5")
    result = _pull(db, user, _at("FT A/5", "G8-UPPER"), _at("FT a/5", "G8-LOWER"))
    assert result.linked_existing == ()
    assert len(result.created) == 2
    assert len([warning for warning in result.warnings if scan.id in warning]) == 2
    assert db.query(EfaturaLink).filter(EfaturaLink.document_id == scan.id).count() == 0


@pytest.mark.parametrize("scan_number", ["Ft A/5", "ft A/5", "FT A/5"])
def test_g8_an_upper_case_series_is_still_an_exact_match(db: Session, scan_number):
    user, _headers = _user(db)
    scan = _scan_numbered(db, user, scan_number)
    result = _pull(db, user, _at("FT A/5", "G8-UPPER"), _at("FT a/5", "G8-LOWER"))
    assert result.linked_existing == (scan.id,)
    scan_links = db.query(EfaturaLink).filter(EfaturaLink.document_id == scan.id).all()
    assert [link.source_key for link in scan_links] == ["atcud:G8-UPPER"]

"""GIL-160 item 2. Any non-alphanumeric run after the type code is a separator."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.schemas.document import SERIES_MISMATCH_DETAIL, invoice_series_prefix, series_disagrees
from app.services.efatura import at_invoice_identity, import_purchases, normalise_invoice_number
from tests.test_efatura_import import TAXPAYER
from tests.test_gil160_linked_delete import _purchase, _scan, _user
from tests.test_qa_gate_ocr import _stored_receipt

CREDIT_NOTES_WITH_SEPARATORS = (
    "NC. 2026/5",
    "NC..2026/5",
    "NC;2026/5",
    "NC'2026/5",
    "NC*2026/5",
    "NC+2026/5",
    "NC(2026)5",
    "NC[1]",
    "NC\u00ba1",
    "NC\u00b01",
)


@pytest.mark.parametrize("number", CREDIT_NOTES_WITH_SEPARATORS)
def test_separator_run_after_the_code_is_a_series(number):
    assert invoice_series_prefix(number) == "NC"
    assert series_disagrees("FT", number)
    assert not series_disagrees("NC", number)


@pytest.mark.parametrize("number", CREDIT_NOTES_WITH_SEPARATORS)
def test_credit_note_numbers_are_refused_on_an_ft(client, db, mock_user_headers, number):
    stored = _stored_receipt(
        db,
        status="needs_review",
        document_type="FT",
        invoice_number="FT A/1",
        ocr_raw_response=None,
    )
    response = client.patch(
        f"/api/documents/{stored.id}",
        headers=mock_user_headers,
        json={"invoice_number": number, "status": "ready"},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == SERIES_MISMATCH_DETAIL
    db.refresh(stored)
    assert stored.invoice_number == "FT A/1"


@pytest.mark.parametrize(
    ("number", "prefix"),
    [
        ("FT\u00b02026/5", "FT"),
        ("ND:5", "ND"),
        ("FS_1", "FS"),
        ("FR, 2026/1", "FR"),
        ("nc;5", "NC"),
        ("Fr. 12", None),
        ("Fr.12", None),
        ("nd..2026", None),
        ("Nc. 12", None),
        ("fr.a", "FR"),
        ("FTA 2026/5", None),
        ("NCB/12", "NC"),
        ("frete 12", None),
        ("FRANGO", None),
    ],
)
def test_separator_rule_keeps_abbreviations_and_words(number, prefix):
    assert invoice_series_prefix(number) == prefix


@pytest.mark.parametrize(
    "number",
    ["NC. 2026/5", "NC..2026/5", "NC;2026/5", "NC'2026/5", "NC*2026/5", "NC+2026/5",
     "NC\u00ba2026/5", "NC\u00b02026/5", "NC/2026/5", "NC2026/5", "nc - 2026 / 005"],
)
def test_identity_reads_a_separator_run_as_one_space(number):
    assert normalise_invoice_number(number) == "nc 2026/5"
    assert at_invoice_identity("296123456", "NC", number) == at_invoice_identity(
        "296123456", "NC", "NC 2026/5"
    )


def test_identity_keeps_real_series_zeros_spaces_and_type():
    nif = "296123456"
    assert normalise_invoice_number("FTA 2026/5") == "fta 2026/5"
    assert normalise_invoice_number("NCB/12") == "nc b/12"
    assert at_invoice_identity(nif, "FT", "FTA 2026/5") != at_invoice_identity(nif, "FT", "FT A 2026/5")
    assert at_invoice_identity(nif, "NC", "NCB/12") == at_invoice_identity(nif, "NC", "NC B/12")
    assert at_invoice_identity(nif, "FT", "FT. A01/5") != at_invoice_identity(nif, "FT", "FT A1/5")
    assert at_invoice_identity(nif, "NC", "NC;007/1") != at_invoice_identity(nif, "NC", "NC 7/1")
    assert normalise_invoice_number("NC;007/001") == "nc 007/1"
    assert at_invoice_identity(nif, "FT", "FT;A 1/5") != at_invoice_identity(nif, "FT", "FT A1/5")
    assert normalise_invoice_number("FT;A 1/5") == "ft a 1/5"
    assert normalise_invoice_number("FT 2026/5") != normalise_invoice_number("NC 2026/5")
    assert at_invoice_identity(nif, "FT", "FT 2026/5") != at_invoice_identity(nif, "NC", "NC 2026/5")


def test_import_links_a_scan_written_with_a_separator_run(db: Session):
    user, _headers = _user(db)
    scan = _scan(db, user)
    scan.vendor_nif = "296123456"
    scan.invoice_number = "FT; 2026/012"
    db.commit()
    result = import_purchases(
        db,
        user_id=user.id,
        taxpayer_nif=TAXPAYER,
        invoices=[_purchase("FT 2026/12")],
    )
    db.commit()
    assert result.linked_existing == (scan.id,)
    assert result.created == ()


def test_import_does_not_link_a_glued_letter_series_to_a_spaced_one(db: Session):
    user, _headers = _user(db)
    scan = _scan(db, user)
    scan.vendor_nif = "296123456"
    scan.invoice_number = "FTA 2026/12"
    db.commit()
    result = import_purchases(
        db,
        user_id=user.id,
        taxpayer_nif=TAXPAYER,
        invoices=[_purchase("FT A 2026/12")],
    )
    db.commit()
    assert result.linked_existing == ()
    assert len(result.created) == 1

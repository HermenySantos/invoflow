"""QA gate 9. Tighter series tokens, a confirm re-check, and a printed-pair flag."""

from __future__ import annotations

import pytest

from app.schemas.document import (
    SERIES_MISMATCH_DETAIL,
    SERIES_OVERRIDE_WARNING,
    invoice_series_prefix,
)
from app.services.ocr_extract import extract_fields
from tests.test_qa_gate_ocr import _stored_receipt


def _suggest(text: str):
    fields = extract_fields(text)
    assert fields.document_type == "unclassified"
    assert fields.invoice_number is None
    return fields.suggested_type, fields.suggested_invoice_number


@pytest.mark.parametrize(
    ("number", "prefix"),
    [
        ("Fr. 12", None),
        ("FRA 2026/12", None),
        ("FRA2026/12", None),
        ("frete 12", None),
        ("fr001", None),
        ("FS2026/12", None),
        ("FT2026/1", None),
        ("NC2026/5", "NC"),
        ("ND2026/3", "ND"),
        ("NC.A/5", "NC"),
        ("NCA/5", "NC"),
        ("N/C A/5", "NC"),
        ("N C A/5", "NC"),
        ("NC-A/5", "NC"),
        ("N\u200bC A/5", "NC"),
        ("\ufeffNC A/5", "NC"),
        ("N\u00adC A/5", "NC"),
        ("\u0143\u0106 A/5", "NC"),
        ("N\u0301C\u0301 A/5", "NC"),
        ("N\u2010C A/5", "NC"),
        ("N\u2013C", "NC"),
        ("N\u2044C A/5", "NC"),
        ("\u0274\u1d04 A/5", "NC"),
        ("\ua4e0C A/5", "NC"),
        ("\ua4e0\ua4da A/5", "NC"),
    ],
)
def test_series_token_rule(number, prefix):
    assert invoice_series_prefix(number) == prefix


def test_false_prefixes_can_be_saved_on_an_ft(client, db, mock_user_headers):
    stored = _stored_receipt(db, document_type="FT", invoice_number="FT A/1", status="needs_review")
    for number in ("Fr. 12", "FRA 2026/12", "FS2026/12", "FT2026/1"):
        saved = client.patch(
            f"/api/documents/{stored.id}",
            headers=mock_user_headers,
            json={"invoice_number": number},
        )
        assert saved.status_code == 200, number
        assert saved.json()["invoice_number"] == number


def test_glued_nc_and_lookalikes_mismatch_an_ft(client, db, mock_user_headers):
    stored = _stored_receipt(db, document_type="FT", invoice_number="FT A/1", status="needs_review")
    for number in (
        "NC2026/5",
        "N\u200bC A/5",
        "\ufeffNC A/5",
        "N\u00adC A/5",
        "\u0143\u0106 A/5",
        "N\u2010C",
        "N\u2044C A/5",
        "\u0274\u1d04 A/5",
        "\ua4e0\ua4da A/5",
    ):
        rejected = client.patch(
            f"/api/documents/{stored.id}",
            headers=mock_user_headers,
            json={"invoice_number": number},
        )
        assert rejected.status_code == 422, number
        assert rejected.json()["detail"] == SERIES_MISMATCH_DETAIL


def test_status_only_confirm_rechecks_a_legacy_mismatch(client, db, mock_user_headers):
    stored = _stored_receipt(
        db,
        status="needs_review",
        document_type="NC",
        invoice_number="FT A/12",
        ocr_raw_response=None,
    )
    rejected = client.patch(
        f"/api/documents/{stored.id}",
        headers=mock_user_headers,
        json={"status": "ready"},
    )
    assert rejected.status_code == 422
    assert rejected.json()["detail"] == SERIES_MISMATCH_DETAIL
    db.refresh(stored)
    assert stored.status == "needs_review"

    notes = client.patch(
        f"/api/documents/{stored.id}",
        headers=mock_user_headers,
        json={"review_notes": "ainda por rever"},
    )
    assert notes.status_code == 200

    # The flag cannot turn a credit note numbered as an invoice into a ready row.
    allowed = client.patch(
        f"/api/documents/{stored.id}",
        headers=mock_user_headers,
        json={"status": "ready", "accept_series_mismatch": True},
    )
    assert allowed.status_code == 422
    assert allowed.json()["detail"] == SERIES_MISMATCH_DETAIL
    db.refresh(stored)
    assert stored.status == "needs_review"
    assert stored.series_mismatch_accepted is False


def test_unreadable_qr_allows_a_printed_at_pair_only_with_the_flag(client, db, mock_user_headers):
    """No QR payload, so FR + FT 2026/12 is a user-entered pair, not an AT exemption."""
    stored = _stored_receipt(
        db,
        status="needs_review",
        document_type="unclassified",
        invoice_number=None,
        ocr_raw_response='{"ocr":"unreadable"}',
    )
    rejected = client.patch(
        f"/api/documents/{stored.id}",
        headers=mock_user_headers,
        json={"document_type": "FR", "invoice_number": "FT 2026/12", "status": "ready"},
    )
    assert rejected.status_code == 422
    assert rejected.json()["detail"] == SERIES_MISMATCH_DETAIL

    allowed = client.patch(
        f"/api/documents/{stored.id}",
        headers=mock_user_headers,
        json={
            "document_type": "FR",
            "invoice_number": "FT 2026/12",
            "status": "ready",
            "accept_series_mismatch": True,
        },
    )
    assert allowed.status_code == 200, allowed.json()
    body = allowed.json()
    assert body["document_type"] == "FR"
    assert body["invoice_number"] == "FT 2026/12"
    assert body["at_invoice_number"] is None
    assert any(item["message"] == SERIES_OVERRIDE_WARNING for item in body["validation_warnings"])


@pytest.mark.parametrize(
    "signal",
    [
        "Documento de crédito",
        "CRÉDITO A FAVOR DO CLIENTE",
        "N/€C n.º 7",
        "NOTA CRÉDITO",
        "Nota Cr.",
    ],
)
def test_new_credit_wordings_suggest_nothing(signal):
    page = "\n".join(
        [
            "Mercearia do Largo",
            "Fatura n.º FT A/12 de 31-03-2026",
            signal,
            "Total 12,30",
        ]
    )
    assert _suggest(page) == (None, None), signal


def test_a_clean_credit_title_still_suggests_its_own_number():
    assert _suggest("Nota de crédito NC Q2/7\nTotal 10,00") == ("NC", "NC Q2/7")

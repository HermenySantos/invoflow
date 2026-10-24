"""QA gate 7. A suggestion is not a control, and a series prefix has to match the type."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.schemas.document import SERIES_MISMATCH_DETAIL, invoice_series_prefix
from app.services.ocr_extract import extract_fields
from tests.test_qa_gate_ocr import _stored_receipt


def _suggest(text: str):
    fields = extract_fields(text)
    assert fields.document_type == "unclassified"
    assert fields.invoice_number is None
    assert fields.needs_review is True
    return fields.suggested_type, fields.suggested_invoice_number


@pytest.mark.parametrize(
    ("number", "prefix"),
    [
        ("FT A/12", "FT"),
        ("NC-A/5", "NC"),
        ("NCA/5", "NC"),
        ("N/C", "NC"),
        ("N/C n.º 7", "NC"),
        ("N.C 1", "NC"),
        ("N-C 1", "NC"),
        ("  fs 1", "FS"),
        ("FR A/5", "FR"),
        ("ND-1", "ND"),
        ("INV-100", None),
        ("CN-2026-7", None),
        ("Q2/7", None),
        ("FRANGO", None),
        ("", None),
        (None, None),
    ],
)
def test_invoice_series_prefix(number, prefix):
    assert invoice_series_prefix(number) == prefix


def test_number_comes_only_from_the_title_line():
    assert _suggest("Fatura\nFT A/12\nTotal 12,30") == ("FT", None)
    assert _suggest("Nota de crédito\nNC Q2/7\nTotal 10,00") == ("NC", None)
    assert _suggest("Fatura FT A/12\nTotal 12,30") == ("FT", "FT A/12")
    assert _suggest("Nota de crédito NC Q2/7\nTotal 10,00") == ("NC", "NC Q2/7")
    assert _suggest("Nota de\ncrédito NC Q2/7\nTotal 10,00") == ("NC", "NC Q2/7")
    assert _suggest("Credit note CN-2026-7\nInvoice FT A/12\nTotal 10,00") == ("NC", None)


def test_a_qualifier_line_suggests_nothing():
    """'Nota de crédito: só mediante devolução' is not a title, and it conflicts with the FT."""
    assert _suggest(
        "Fatura FT A/12\nNota de crédito: só mediante devolução\nTotal 12,30"
    ) == (None, None)
    assert _suggest(
        "Fatura FT A/12\nNota de débito: só mediante acordo\nTotal 12,30"
    ) == (None, None)
    assert _suggest("Nota de crédito: só mediante devolução\nTotal 12,30") == (None, None)


def test_clean_credit_title_still_suggests_its_own_number():
    suggested = _suggest(
        "\n".join(
            [
                "Padaria Exemplo Lda",
                "Fatura n.º FT A/12 de 31-03-2026",
                "Nota de crédito NC Q2/7",
                "Total 10,00",
            ]
        )
    )
    assert suggested == ("NC", "NC Q2/7")


@pytest.mark.parametrize(
    ("number", "doc_type", "ok"),
    [
        ("FT A/12", "NC", False),
        ("NC-A/5", "FT", False),
        ("NCA/5", "FT", False),
        ("N/C", "FT", False),
        ("N/C n.º 7", "FT", False),
        ("  FT A/12", "NC", False),
        ("NC-A/5", "NC", True),
        ("NCA/5", "NC", True),
        ("N/C n.º 7", "NC", True),
        ("FT A/12", "FT", True),
        ("INV-100", "NC", True),
        ("CN-2026-7", "FT", True),
        ("Q2/7", "NC", True),
        ("FRANGO", "NC", True),
        ("", "FT", True),
    ],
)
def test_series_prefix_must_match_the_chosen_type(
    client, db, mock_user_headers, number, doc_type, ok
):
    stored = _stored_receipt(
        db,
        document_type="unclassified",
        status="needs_review",
        invoice_number="TEMP",
    )
    patched = client.patch(
        f"/api/documents/{stored.id}",
        headers=mock_user_headers,
        json={"document_type": doc_type, "invoice_number": number, "status": "ready"},
    )
    db.refresh(stored)
    if ok:
        assert patched.status_code == 200, patched.text
        assert stored.document_type == doc_type
        assert stored.status == "ready"
    else:
        assert patched.status_code == 422
        assert patched.json()["detail"] == SERIES_MISMATCH_DETAIL
        assert stored.document_type == "unclassified"
        assert stored.invoice_number == "TEMP"
        assert stored.status == "needs_review"


def test_confirming_uses_the_stored_number(client, db, mock_user_headers):
    """A confirm that sends only the type still 422s when the stored number is another series."""
    stored = _stored_receipt(
        db,
        document_type="unclassified",
        status="needs_review",
        invoice_number="FT A/12",
    )
    patched = client.patch(
        f"/api/documents/{stored.id}",
        headers=mock_user_headers,
        json={"document_type": "NC", "status": "ready"},
    )
    assert patched.status_code == 422
    assert patched.json()["detail"] == SERIES_MISMATCH_DETAIL
    db.refresh(stored)
    assert stored.document_type == "unclassified"
    assert stored.invoice_number == "FT A/12"
    assert stored.status == "needs_review"

    agreed = client.patch(
        f"/api/documents/{stored.id}",
        headers=mock_user_headers,
        json={"document_type": "FT", "status": "ready"},
    )
    assert agreed.status_code == 200
    db.refresh(stored)
    assert stored.document_type == "FT"
    assert stored.status == "ready"


def test_unclassified_draft_keeps_vendor_and_amount_edits(client, db, mock_user_headers):
    stored = _stored_receipt(
        db,
        document_type="unclassified",
        status="needs_review",
        vendor_name="Antes",
        invoice_number="FT A/12",
    )
    patched = client.patch(
        f"/api/documents/{stored.id}",
        headers=mock_user_headers,
        json={
            "vendor_name": "Padaria Nova",
            "document_date": "2026-03-31",
            "gross_amount": "15.00",
            "vat_amount": "2.30",
            "net_amount": "12.70",
            "document_type": "unclassified",
            "invoice_number": "FT A/12",
            "status": "needs_review",
        },
    )
    assert patched.status_code == 200, patched.text
    db.refresh(stored)
    assert stored.status == "needs_review"
    assert stored.document_type == "unclassified"
    assert stored.vendor_name == "Padaria Nova"
    assert stored.gross_amount == Decimal("15.00")
    assert stored.vat_amount == Decimal("2.30")
    assert stored.net_amount == Decimal("12.70")
    assert stored.invoice_number == "FT A/12"

    rejected = client.patch(
        f"/api/documents/{stored.id}",
        headers=mock_user_headers,
        json={"document_type": "NC", "status": "ready"},
    )
    assert rejected.status_code == 422
    assert rejected.json()["detail"] == SERIES_MISMATCH_DETAIL
    db.refresh(stored)
    assert stored.status == "needs_review"
    assert stored.vendor_name == "Padaria Nova"


def test_cited_ft_number_cannot_be_saved_on_a_credit_note(client, db, mock_user_headers):
    """These wordings are not new deny-list entries. The stored pair is what is rejected."""
    samples = (
        "Fatura FT A/12\nNOTA CRÉDITO\nTotal 10,00",
        "Fatura FT A/12\nNota Cr.\nTotal 10,00",
        "Fatura FT A/12\nN/C n.º 7\nTotal 10,00",
        "Documento retificativo\nFatura FT A/12\nTotal 10,00",
        "Fatura FT A/12\nEstorno\nTotal 10,00",
        "Fatura FT A/12\nDevolução\nTotal 10,00",
        "Fatura FT A/12\nCredit memo\nTotal 10,00",
        "Refund\nInvoice FT A/12\nTotal 10,00",
        "Credit memo CM-7\nInvoice FT A/12\nTotal 10,00",
        "Nota de crédit0\nFatura FT A/12\nTotal 10,00",
        "Nota de cr€dito\nFatura FT A/12\nTotal 10,00",
        "Nota de abono\nFatura FT A/12\nTotal 10,00",
    )
    stored = _stored_receipt(
        db,
        document_type="unclassified",
        status="needs_review",
        invoice_number=None,
    )
    for text in samples:
        fields = extract_fields(text)
        number = fields.suggested_invoice_number
        if invoice_series_prefix(number) != "FT":
            number = "FT A/12"
        rejected = client.patch(
            f"/api/documents/{stored.id}",
            headers=mock_user_headers,
            json={"document_type": "NC", "invoice_number": number, "status": "ready"},
        )
        assert rejected.status_code == 422, text
        assert rejected.json()["detail"] == SERIES_MISMATCH_DETAIL, text
    db.refresh(stored)
    assert stored.document_type == "unclassified"
    assert stored.status == "needs_review"
    assert stored.invoice_number is None

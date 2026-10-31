"""QA gate 8. The series check runs only when the type or number changes, and not on an AT pair."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.models.document import Document
from app.schemas.document import SERIES_MISMATCH_DETAIL, invoice_series_prefix
from app.services.efatura import EFaturaInvoice, VatLine, import_purchases
from app.services.ocr import OCRResult, _apply_invoice_qr
from app.services.ocr_extract import extract_fields
from app.services.pt_qr import parse_invoice_qr
from tests.test_qa_gate_ocr import SYNTHETIC_NIF, _stored_receipt

# AT may number an FR "FT …" or an ND "NC …". The internal code is not field D.
AT_PAIRS = (
    ("FR", "FT 2026/12"),
    ("FR", "FTR A/12"),
    ("FS", "FT A/12"),
    ("FS", "FR 1/5"),
    ("ND", "NC A/3"),
)

_CYRILLIC_ES = "\u0421"  # С, looks like C
_CYRILLIC_EN = "\u041d"  # Н, the H-shaped letter, folded to N
_FULLWIDTH_NC = "\uff2e\uff23"  # ＮＣ


def _suggest(text: str):
    fields = extract_fields(text)
    assert fields.document_type == "unclassified"
    assert fields.invoice_number is None
    return fields.suggested_type, fields.suggested_invoice_number


def _qr(code: str, number: str):
    parsed = parse_invoice_qr(
        f"A:{SYNTHETIC_NIF}*B:999999990*C:PT*D:{code}*E:N*F:20260115*G:{number}*"
        "H:ATCUD*I1:PT*I7:10.00*I8:2.30*N:2.30*O:12.30*Q:abcd*R:1"
    )
    assert parsed is not None
    assert parsed.document_type == code
    assert parsed.invoice_number == number
    return parsed


def _qr_row(db, code: str, number: str, *, status: str = "ready") -> Document:
    applied = _apply_invoice_qr(
        OCRResult(vendor_name="Ana Exemplo", backend="tesseract", confidence=90, needs_review=True),
        _qr(code, number),
    )
    assert applied.document_type == code
    assert applied.at_document_type == code
    assert applied.invoice_number == number
    assert applied.needs_review is False
    return _stored_receipt(
        db,
        status=status,
        document_type=applied.document_type,
        at_document_type=applied.at_document_type,
        invoice_number=applied.invoice_number,
        ocr_raw_response=applied.raw_response,
    )


@pytest.mark.parametrize(
    ("number", "prefix"),
    [
        ("frete 12", None),
        ("fr001", None),
        ("FS2026/12", None),
        ("FRA2026/12", None),
        ("F T A/12", "FT"),
        ("nc a/5", "NC"),
        ("N C A/5", "NC"),
        ("NC.A/5", "NC"),
        ("N.C. A/5", "NC"),
        ("N/C A/5", "NC"),
        ("NC-A/5", "NC"),
        ("NCA/5", "NC"),
        ("  NC A/5  ", "NC"),
        ("NC\tA/5", "NC"),
        ("NC\u00a0A/5", "NC"),
        (f"N{_CYRILLIC_ES} A/5", "NC"),
        (f"{_CYRILLIC_EN}C A/5", "NC"),
        (f"{_FULLWIDTH_NC} A/5", "NC"),
    ],
)
def test_series_token_is_a_word_and_folds_confusables(number, prefix):
    assert invoice_series_prefix(number) == prefix


def test_lookalike_nc_numbers_are_rejected_on_an_ft(client, db, mock_user_headers):
    stored = _stored_receipt(db, document_type="FT", invoice_number="FT A/1")
    for number in (f"N{_CYRILLIC_ES} A/5", f"{_CYRILLIC_EN}C A/5", f"{_FULLWIDTH_NC} A/5"):
        rejected = client.patch(
            f"/api/documents/{stored.id}",
            headers=mock_user_headers,
            json={"invoice_number": number},
        )
        assert rejected.status_code == 422, number
        assert rejected.json()["detail"] == SERIES_MISMATCH_DETAIL


def test_ordinary_words_are_not_a_series_mismatch(client, db, mock_user_headers):
    stored = _stored_receipt(db, document_type="FT", invoice_number="FT A/1")
    for number in ("frete 12", "fr001", "FS2026/12", "FRA2026/12"):
        saved = client.patch(
            f"/api/documents/{stored.id}",
            headers=mock_user_headers,
            json={"invoice_number": number},
        )
        assert saved.status_code == 200, number
        assert saved.json()["invoice_number"] == number


@pytest.mark.parametrize(("code", "number"), AT_PAIRS)
def test_qr_at_pair_allows_category_deductible_notes_and_confirm(
    client, db, mock_user_headers, code, number
):
    stored = _qr_row(db, code, number)
    document_id = stored.id

    for payload in (
        {"expense_category": "food"},
        {"deductible_pct_override": 50},
        {"review_notes": "conferido"},
        {"status": "needs_review"},
        {"status": "ready"},
        {"document_type": code, "invoice_number": number, "expense_category": "utilities"},
    ):
        response = client.patch(
            f"/api/documents/{document_id}",
            headers=mock_user_headers,
            json=payload,
        )
        assert response.status_code == 200, (code, number, payload, response.json())
        body = response.json()
        assert body["document_type"] == code
        assert body["invoice_number"] == number
        assert body["at_document_type"] == code
        assert body["at_invoice_number"] == number

    away = client.patch(
        f"/api/documents/{document_id}",
        headers=mock_user_headers,
        json={"invoice_number": "NC Z/1"},
    )
    assert away.status_code == 422
    assert away.json()["detail"] == SERIES_MISMATCH_DETAIL
    db.refresh(stored)
    assert stored.document_type == code
    assert stored.invoice_number == number


def test_restoring_the_at_pair_is_not_a_mismatch(client, db, mock_user_headers):
    stored = _qr_row(db, "FR", "FT 2026/12")
    changed = client.patch(
        f"/api/documents/{stored.id}",
        headers=mock_user_headers,
        json={"invoice_number": "INV-9"},
    )
    assert changed.status_code == 200
    restored = client.patch(
        f"/api/documents/{stored.id}",
        headers=mock_user_headers,
        json={"document_type": "FR", "invoice_number": "FT 2026/12"},
    )
    assert restored.status_code == 200
    assert restored.json()["invoice_number"] == "FT 2026/12"
    assert restored.json()["at_invoice_number"] == "FT 2026/12"


def test_legacy_mismatch_allows_unrelated_edits(client, db, mock_user_headers):
    stored = _stored_receipt(
        db,
        status="ready",
        document_type="NC",
        invoice_number="FT A/12",
        at_document_type=None,
        ocr_raw_response=None,
    )
    for payload in (
        {"expense_category": "food"},
        {"deductible_pct_override": 25},
        {"review_notes": "nota antiga"},
    ):
        response = client.patch(
            f"/api/documents/{stored.id}",
            headers=mock_user_headers,
            json=payload,
        )
        assert response.status_code == 200, payload
        assert response.json()["document_type"] == "NC"
        assert response.json()["invoice_number"] == "FT A/12"

    # A status-only confirm is checked again. A credit note numbered as an invoice stays blocked.
    rejected = client.patch(
        f"/api/documents/{stored.id}",
        headers=mock_user_headers,
        json={"status": "ready"},
    )
    assert rejected.status_code == 422
    assert rejected.json()["detail"] == SERIES_MISMATCH_DETAIL

    rejected = client.patch(
        f"/api/documents/{stored.id}",
        headers=mock_user_headers,
        json={"document_type": "FS"},
    )
    assert rejected.status_code == 422
    assert rejected.json()["detail"] == SERIES_MISMATCH_DETAIL


def _efatura(code: str, number: str, atcud: str) -> EFaturaInvoice:
    return EFaturaInvoice(
        document_type=code,
        invoice_number=number,
        issue_date=date(2026, 3, 2),
        issuer_nif="500829993",
        acquirer_nif="555555555",
        acquirer_country="PT",
        fiscal_status="normal",
        lines=(VatLine("IVA", "PT", "NOR", Decimal("23"), Decimal("10"), Decimal("2.30"), None),),
        tax_payable=Decimal("2.30"),
        net_total=Decimal("10.00"),
        gross_total=Decimal("12.30"),
        atcud=atcud,
        issuer_name="Loja",
    )


@pytest.mark.parametrize(("code", "number"), AT_PAIRS)
def test_efatura_at_pair_can_be_recategorised_and_confirmed(
    client, db, mock_user_headers, code, number
):
    owner = _stored_receipt(db)
    imported = import_purchases(
        db,
        user_id=owner.user_id,
        taxpayer_nif="555555555",
        invoices=[_efatura(code, number, f"V8{code}{number}")],
    )
    db.commit()
    assert imported.created, (code, number)
    document_id = imported.created[0]
    row = db.get(Document, document_id)
    assert row.document_type == code
    assert row.invoice_number == number
    assert row.status == "needs_review"
    assert row.ocr_raw_response == '{"source":"efatura"}'

    category = client.patch(
        f"/api/documents/{document_id}",
        headers=mock_user_headers,
        json={"expense_category": "food"},
    )
    assert category.status_code == 200, category.json()
    assert category.json()["at_document_type"] == code
    assert category.json()["at_invoice_number"] == number
    assert category.json()["expense_category"] == "food"

    notes = client.patch(
        f"/api/documents/{document_id}",
        headers=mock_user_headers,
        json={"review_notes": "e-fatura", "deductible_pct_override": 40},
    )
    assert notes.status_code == 200, notes.json()

    confirmed = client.patch(
        f"/api/documents/{document_id}",
        headers=mock_user_headers,
        json={"status": "ready"},
    )
    assert confirmed.status_code == 200, confirmed.json()
    assert confirmed.json()["status"] == "ready"
    assert confirmed.json()["document_type"] == code
    assert confirmed.json()["invoice_number"] == number


@pytest.mark.parametrize(
    "signal",
    [
        "NOTA CRÉDITO",
        "Nota Cr.",
        "N/C n.º 7",
        "Documento retificativo",
        "Estorno",
        "Devolução",
        "Credit memo",
        "Refund",
        "Credit memo CM-7",
        "N/C A/5",
        "NC-A/5",
        "NCA/5",
    ],
)
def test_credit_signals_suggest_neither_fatura_nor_an_ft_number(signal):
    page = "\n".join(
        [
            "Padaria Exemplo Lda",
            "Fatura n.º FT A/12 de 31-03-2026",
            signal,
            "Total 12,30",
        ]
    )
    assert _suggest(page) == (None, None), signal


def test_a_clean_credit_title_still_suggests_its_own_number():
    assert _suggest("Nota de crédito NC Q2/7\nTotal 10,00") == ("NC", "NC Q2/7")
    assert _suggest(
        "Fatura FT A/12\nNota de crédito: só mediante devolução\nTotal 12,30"
    ) == (None, None)

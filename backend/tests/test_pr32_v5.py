"""QA gate 5. Without an AT QR, nothing is confirmed and nothing gets a concrete type."""

from __future__ import annotations

import io
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from pypdf import PdfReader
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.user import User
from app.services.efatura import EFaturaInvoice, VatLine, import_purchases
from app.services.export import ExportService
from app.services.iva_adjust import EXCLUDED_HEADING, contributions
from app.services.ocr import OCRResult, _apply_invoice_qr, finalize_non_qr
from app.services.ocr_extract import extract_fields
from app.services.pt_qr import parse_invoice_qr
from tests.test_export import PT_CSV_HEADERS, read_csv
from tests.test_qa_gate_ocr import SYNTHETIC_NIF


def _qr(code: str):
    parsed = parse_invoice_qr(
        f"A:{SYNTHETIC_NIF}*B:999999990*C:PT*D:{code}*E:N*F:20260115*G:{code} A/1*"
        "H:ATCUD*I1:PT*I7:10.00*I8:2.30*N:2.30*O:12.30*Q:abcd*R:1"
    )
    assert parsed is not None
    return parsed


def _reading(text: str):
    fields = extract_fields(text)
    assert fields.document_type == "unclassified"
    assert fields.invoice_number is None
    assert fields.needs_review is True
    return fields


def test_azure_confident_negative_total_stays_unclassified_and_in_review():
    result = finalize_non_qr(
        OCRResult(
            backend="azure",
            vendor_name="Shop",
            gross_amount=Decimal("-10"),
            vat_amount=Decimal("-1.87"),
            net_amount=Decimal("-8.13"),
            confidence=99,
            needs_review=False,
            invoice_number="TX-9",
            document_type="FT",
        )
    )
    assert result.gross_amount == Decimal("10")
    assert result.vat_amount == Decimal("1.87")
    assert result.net_amount == Decimal("8.13")
    assert result.document_type == "unclassified"
    assert result.invoice_number is None
    assert result.suggested_invoice_number is None
    assert result.needs_review is True


def test_garbled_credit_titles_do_not_suggest_a_purchase_or_an_origin_number():
    for text in (
        "N0TA DE CRÉDITO\nFatura de origem FT A/12\nTotal 10,00",
        "Credit Note\nFatura de origem FT A/12\nTotal 10,00",
        "Notade crédito\nTotal 10,00",
    ):
        fields = _reading(text)
        assert fields.suggested_type == "NC", text
        assert fields.suggested_invoice_number is None, text
    for text in (
        "Fatura retificativa\nTotal 10,00",
        "Fatura de anulação\nTotal 10,00",
    ):
        fields = _reading(text)
        assert fields.suggested_type is None, text
        assert fields.suggested_invoice_number is None, text


def test_trailing_minus_and_parentheses_are_absolute_and_unclassified():
    for text in ("Total 12,30-", "Total (12,30)"):
        fields = _reading(text)
        assert fields.gross_amount == Decimal("12.30"), text
        assert fields.suggested_type is None


def test_nc_series_under_a_fatura_title_is_not_the_number():
    fields = _reading("Fatura\nNC A/12\nTotal 12,30")
    assert fields.suggested_type is None
    assert fields.suggested_invoice_number is None
    same_line = _reading("Fatura NC A/9\nTotal 12,30")
    assert same_line.suggested_type is None
    assert same_line.suggested_invoice_number is None


def test_other_at_qr_types_stay_unclassified_and_out_of_totals():
    for code in ("PF", "OR", "RG", "GT"):
        applied = _apply_invoice_qr(
            OCRResult(vendor_name="Ana Exemplo", backend="tesseract", confidence=99),
            _qr(code),
        )
        assert applied.document_type == "unclassified", code
        assert applied.at_document_type == code
        assert applied.needs_review is True
        assert applied.invoice_number == f"{code} A/1"
        document = SimpleNamespace(
            id=code,
            status="needs_review",
            document_type=applied.document_type,
            net_amount=applied.net_amount,
            vat_amount=applied.vat_amount,
            gross_amount=applied.gross_amount,
            vendor_nif=SYNTHETIC_NIF,
            created_at=None,
            document_date=date(2026, 1, 15),
        )
        assert contributions([document]) == []


def test_concrete_qr_types_can_confirm():
    applied = _apply_invoice_qr(
        OCRResult(vendor_name="Ana Exemplo", backend="tesseract", confidence=40, needs_review=True),
        _qr("NC"),
    )
    assert applied.document_type == "NC"
    assert applied.at_document_type == "NC"
    assert applied.needs_review is False
    assert applied.invoice_number == "NC A/1"
    assert applied.gross_amount == Decimal("12.30")


def test_ref_parenthetical_is_skipped_and_the_real_number_is_kept():
    fields = _reading("Fatura (ref. FT B/99) FT A/12\nTotal 12,30")
    assert fields.suggested_type == "FT"
    assert fields.suggested_invoice_number == "FT A/12"


def test_number_on_the_line_below_the_title():
    """The number has to sit on the title line. The next line is left out."""
    fields = _reading("Fatura\nFT A/12\nTotal 12,30")
    assert fields.suggested_type == "FT"
    assert fields.suggested_invoice_number is None


def test_no_title_suggests_nothing():
    fields = _reading("Ana Exemplo\nTotal 12,30\nIVA 2,30")
    assert fields.suggested_type is None
    assert fields.suggested_invoice_number is None


def test_fatura_recibo_suggests_fr():
    fields = _reading("Fatura/Recibo FR A/5\nTotal 12,30")
    assert fields.suggested_type == "FR"
    assert fields.suggested_invoice_number == "FR A/5"


def test_exports_list_rows_left_out_of_the_totals():
    counted = Document(
        id="11111111-aaaa-bbbb-cccc-000000000001",
        user_id="u",
        status="ready",
        storage_key="u/a.jpg",
        original_filename="a.jpg",
        mime_type="image/jpeg",
        vendor_name="Pingo Doce",
        document_date=date(2026, 9, 15),
        net_amount=Decimal("10.00"),
        vat_amount=Decimal("2.30"),
        gross_amount=Decimal("12.30"),
        document_type="FT",
        expense_category="office",
    )
    waiting = Document(
        id="22222222-aaaa-bbbb-cccc-000000000002",
        user_id="u",
        status="needs_review",
        storage_key="u/b.jpg",
        original_filename="b.jpg",
        mime_type="image/jpeg",
        vendor_name="Por rever",
        document_date=date(2026, 9, 16),
        net_amount=Decimal("8.13"),
        vat_amount=Decimal("1.87"),
        gross_amount=Decimal("10.00"),
        document_type="unclassified",
        at_document_type="PF",
        expense_category="office",
    )
    service = ExportService()
    service.storage = type("S", (), {"get_file": lambda self, key: b"bytes"})()
    archive_bytes, _name = service.generate_export(None, "u", [counted, waiting], "2026-09")
    import zipfile

    archive = zipfile.ZipFile(io.BytesIO(archive_bytes))
    rows = read_csv(archive)
    assert rows[0] == PT_CSV_HEADERS
    assert waiting.id not in {row[0] for row in rows}
    assert counted.id in {row[0] for row in rows}
    review = archive.read("documentos_por_rever.csv").decode("utf-8")
    assert EXCLUDED_HEADING in review
    assert "Por rever" in review
    assert "PF" in review
    pdf_text = "\n".join(
        page.extract_text() or "" for page in PdfReader(io.BytesIO(archive.read("summary.pdf"))).pages
    )
    assert EXCLUDED_HEADING in pdf_text
    originals = [name for name in archive.namelist() if name.startswith("receipts/")]
    assert len(originals) == 1


def test_projection_lists_the_same_excluded_heading(client, db: Session):
    clerk_id = "v5-projection"
    user = User(clerk_id=clerk_id, email="v5@example.com")
    db.add(user)
    db.commit()
    db.add(Document(
        user_id=user.id,
        status="needs_review",
        storage_key=f"{clerk_id}/waiting.jpg",
        original_filename="waiting.jpg",
        mime_type="image/jpeg",
        vendor_name="Por rever",
        document_date=date(2026, 2, 2),
        net_amount=Decimal("10.00"),
        vat_amount=Decimal("2.30"),
        gross_amount=Decimal("12.30"),
        document_type="unclassified",
        expense_category="office",
    ))
    db.commit()
    projection = client.get(
        "/api/summary/projection",
        params={"year": 2026, "quarter": 1, "as_of": "2026-03-31"},
        headers={"X-Mock-User-Id": clerk_id},
    )
    assert projection.status_code == 200, projection.text
    body = projection.json()
    assert body["excluded_heading"] == EXCLUDED_HEADING
    assert body["excluded_documents"]
    assert body["excluded_documents"][0]["vendor_name"] == "Por rever"
    assert body["confirmed_deductible_to_date"] == "0.00"


def test_efatura_keeps_a_concrete_at_type_and_reviews_the_others(db: Session):
    user = User(clerk_id="v5-efatura", email="efatura-v5@example.com")
    db.add(user)
    db.commit()

    def invoice(code: str) -> EFaturaInvoice:
        return EFaturaInvoice(
            document_type=code,
            invoice_number=f"{code} A/1",
            issue_date=date(2026, 2, 1),
            issuer_nif="500829993",
            acquirer_nif="555555555",
            acquirer_country="PT",
            fiscal_status="normal",
            lines=(VatLine("IVA", "PT", "NOR", Decimal("23"), Decimal("10"), Decimal("2.30"), None),),
            tax_payable=Decimal("2.30"),
            net_total=Decimal("10.00"),
            gross_total=Decimal("12.30"),
            issuer_name="Loja",
        )

    ft = import_purchases(db, user_id=user.id, taxpayer_nif="555555555", invoices=[invoice("FT")])
    db.commit()
    stored = db.get(Document, ft.created[0])
    assert stored.document_type == "FT"
    assert stored.at_document_type == "FT"
    assert stored.status == "needs_review"
    assert stored.ocr_raw_response == '{"source":"efatura"}'

    for code in ("PF", "OR", "RG", "GT"):
        outcome = import_purchases(
            db, user_id=user.id, taxpayer_nif="555555555", invoices=[invoice(code)]
        )
        db.commit()
        assert outcome.created, code
        row = db.get(Document, outcome.created[0])
        assert row.document_type == "unclassified", code
        assert row.at_document_type == code
        assert row.status == "needs_review"
        assert contributions([row]) == []

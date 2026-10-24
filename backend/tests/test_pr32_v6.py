"""QA gate 6. Suggestions never pre-confirm a cited invoice, and the lists agree."""

from __future__ import annotations

import io
import json
import uuid
import zipfile
from datetime import date, datetime
from decimal import Decimal

from pypdf import PdfReader
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.user import User
from app.schemas.document import NULL_TYPE_DETAIL
from app.services.document_type_backfill import backfill_document_types, restore_document_types
from app.services.export import ExportService
from app.services.iva_adjust import EXCLUDED_HEADING, contributions
from app.services.ocr_extract import extract_fields
from tests.test_export import read_csv
from tests.test_qa_gate_ocr import _stored_receipt


def _suggest(text: str):
    fields = extract_fields(text)
    assert fields.document_type == "unclassified"
    assert fields.invoice_number is None
    assert fields.needs_review is True
    return fields.suggested_type, fields.suggested_invoice_number


def test_s6_cited_fatura_above_a_credit_title_suggests_the_credit_note():
    """Real Tesseract lines: the Nota title wins over 'Fatura n.º FT A/12 de <date>'."""
    suggested = _suggest(
        "\n".join(
            [
                "Padaria Exemplo Lda",
                "Fatura n.º FT A/12 de 31-03-2026",
                "Nota de crédito NC Q2/7",
                "NIF 123456002",
                "Data 31-03-2026",
                "IVA 23% 8,13 1,87",
                "Total 10,00",
            ]
        )
    )
    assert suggested == ("NC", "NC Q2/7")
    assert _suggest("Nota de crédito NC Q2/7\nTotal 10,00") == ("NC", "NC Q2/7")


def test_s2_s4_credit_signals_never_suggest_ft():
    samples = (
        "Fatura: FT A/12\nN0TA DE CRÉDITO\nTotal 10,00",
        "Fatura FT A/12\nTotal a creditar 10,00",
        "Fatura FT A/12\nEste documento é uma nota de crédito\nTotal 10,00",
        "Fatura FT A/12\nTotal 12,30-",
        "Fatura FT A/12\nTotal (12,30)",
        "Fatura rectificativa R-7\nTotal 10,00",
        "Fatura retificativa FT A/13\nTotal 10,00",
        "Fatura NC/A/5\nTotal 10,00",
        "Fatura NC A/5\nTotal 10,00",
        "Fatura\nNC 2026A5\nTotal 10,00",
        "Fatura\nNº: NC 5\nTotal 10,00",
    )
    for text in samples:
        kind, number = _suggest(text)
        assert kind not in {"FT", "FS", "FR"}, text
        assert number != "FT A/12", text
        assert number is None or not str(number).startswith("FT"), text


def test_s1_citation_numbers_are_not_suggested():
    assert _suggest("Notade crédito\nFatura FT A/12\nTotal 10,00") == ("NC", None)
    assert _suggest("Credit note CN-2026-7\nInvoice FT A/12\nTotal 10,00") == ("NC", None)
    assert _suggest("Credit Note\nFatura FT A/12\nTotal 10,00") == ("NC", None)
    assert _suggest("Nota de crédlto\nFatura FT A/12\nTotal 10,00") == ("NC", None)
    assert _suggest("Fatura FT A/12\nTotal 10,00") == ("FT", "FT A/12")


def test_s5_an_nc_suggestion_never_carries_an_ft_series_number():
    kind, number = _suggest("Nota de crédito\nFatura FT A/12\nTotal 10,00")
    assert kind == "NC"
    assert number is None


def test_unparenthesised_ref_keeps_the_number_after_nº():
    assert _suggest("Fatura ref FT B/99 n.º FT A/12\nTotal 12,30") == ("FT", "FT A/12")
    assert _suggest("Fatura (ref. FT B/99) FT A/12\nTotal 12,30") == ("FT", "FT A/12")


def test_a_plain_fatura_number_line_is_still_the_title():
    assert _suggest("Fatura n.º FT A/12 de 31-03-2026\nTotal 12,30") == ("FT", "FT A/12")
    assert _suggest("ND A/3\nTotal 12,30") == (None, "ND A/3")
    assert _suggest("Fatura\nTotal-12,30")[0] == "FT"


def test_n0_null_document_type_is_422(client, db, mock_user_headers):
    stored = _stored_receipt(db, document_type="FT", status="ready")
    patched = client.patch(
        f"/api/documents/{stored.id}",
        headers=mock_user_headers,
        json={"document_type": None},
    )
    assert patched.status_code == 422
    assert patched.json()["detail"] == NULL_TYPE_DETAIL
    db.refresh(stored)
    assert stored.document_type == "FT"


def test_x3_pdf_excluded_list_says_when_it_is_capped():
    documents = []
    for index in range(60):
        documents.append(
            Document(
                id=f"33333333-aaaa-bbbb-cccc-{index:012d}",
                user_id="u",
                status="needs_review",
                storage_key=f"u/{index}.jpg",
                original_filename=f"{index}.jpg",
                mime_type="image/jpeg",
                vendor_name=f"Fora {index}",
                document_date=date(2026, 9, 1),
                net_amount=Decimal("8.13"),
                vat_amount=Decimal("1.87"),
                gross_amount=Decimal("10.00"),
                document_type="unclassified",
                expense_category="office",
            )
        )
    service = ExportService()
    service.storage = type("S", (), {"get_file": lambda self, key: b"bytes"})()
    archive_bytes, _name = service.generate_export(None, "u", documents, "2026-09")
    archive = zipfile.ZipFile(io.BytesIO(archive_bytes))
    review = archive.read("documentos_por_rever.csv").decode("utf-8")
    assert EXCLUDED_HEADING in review
    assert all(f"Fora {index}" in review for index in range(60))
    pdf_text = "\n".join(
        page.extract_text() or "" for page in PdfReader(io.BytesIO(archive.read("summary.pdf"))).pages
    )
    assert "e mais 10, ver CSV" in pdf_text
    assert read_csv(archive)[0]


def test_x2_projection_lists_typed_rows_still_in_review(client, db: Session):
    clerk_id = "v6-projection"
    user = User(clerk_id=clerk_id, email="v6-projection@example.com")
    db.add(user)
    db.commit()
    db.add(
        Document(
            user_id=user.id,
            status="needs_review",
            storage_key=f"{clerk_id}/fs.jpg",
            original_filename="fs.jpg",
            mime_type="image/jpeg",
            vendor_name="FS pendente",
            document_date=date(2026, 2, 2),
            net_amount=Decimal("4.00"),
            vat_amount=Decimal("0.92"),
            gross_amount=Decimal("4.92"),
            document_type="FS",
            expense_category="office",
        )
    )
    db.add(
        Document(
            user_id=user.id,
            status="needs_review",
            storage_key=f"{clerk_id}/ft.jpg",
            original_filename="ft.jpg",
            mime_type="image/jpeg",
            vendor_name="FT e-Fatura",
            document_date=date(2026, 2, 3),
            net_amount=Decimal("8.13"),
            vat_amount=Decimal("1.87"),
            gross_amount=Decimal("10.00"),
            document_type="FT",
            expense_category="office",
            ocr_raw_response='{"source":"efatura"}',
        )
    )
    db.commit()
    projection = client.get(
        "/api/summary/projection",
        params={"year": 2026, "quarter": 1, "as_of": "2026-03-31"},
        headers={"X-Mock-User-Id": clerk_id},
    )
    assert projection.status_code == 200, projection.text
    body = projection.json()
    listed = {item["vendor_name"]: item["reason"] for item in body["excluded_documents"]}
    assert listed["FS pendente"] == "por rever"
    assert listed["FT e-Fatura"] == "por rever"
    assert body["confirmed_deductible_to_date"] == "0.00"
    pending = contributions(db.query(Document).filter(Document.user_id == user.id).all())
    assert {row.document.vendor_name for row in pending} == {"FS pendente", "FT e-Fatura"}


def test_summary_and_exports_agree_on_cancelled_and_duplicates(client, db: Session):
    clerk_id = "v6-agree"
    user = User(clerk_id=clerk_id, email="v6-agree@example.com")
    db.add(user)
    db.commit()
    common = dict(
        user_id=user.id,
        mime_type="image/jpeg",
        document_date=date(2026, 9, 15),
        net_amount=Decimal("8.13"),
        vat_amount=Decimal("1.87"),
        gross_amount=Decimal("10.00"),
        expense_category="office",
        status="ready",
    )
    db.add(
        Document(
            storage_key=f"{clerk_id}/nc.jpg",
            original_filename="nc.jpg",
            vendor_name="Anulada",
            invoice_number="NC A/1",
            document_type="NC",
            ocr_raw_response=json.dumps(
                {"file_sha256": "cancelled", "qr": {"document_type": "NC", "fiscal_status": "A"}}
            ),
            **common,
        )
    )
    db.add(
        Document(
            storage_key=f"{clerk_id}/old.jpg",
            original_filename="old.jpg",
            vendor_name="Copia",
            invoice_number="FT A/9",
            document_type="FT",
            created_at=datetime(2026, 9, 1, 8, 0, 0),
            ocr_raw_response=json.dumps({"file_sha256": "same-file"}),
            **common,
        )
    )
    db.add(
        Document(
            storage_key=f"{clerk_id}/new.jpg",
            original_filename="new.jpg",
            vendor_name="Original",
            invoice_number="FT A/9",
            document_type="FT",
            created_at=datetime(2026, 9, 2, 8, 0, 0),
            ocr_raw_response=json.dumps({"file_sha256": "same-file"}),
            **common,
        )
    )
    db.commit()
    summary = client.get(
        "/api/summary",
        params={"period_type": "month", "year": 2026, "month": 9},
        headers={"X-Mock-User-Id": clerk_id},
    )
    assert summary.status_code == 200, summary.text
    body = summary.json()
    reasons = {item["vendor_name"]: item["reason"] for item in body["excluded_documents"]}
    assert reasons["Anulada"] == "anulado"
    assert reasons["Copia"] == "duplicado"
    assert "Original" not in reasons
    assert body["total_vat"] == "1.87"

    documents = db.query(Document).filter(Document.user_id == user.id).all()
    service = ExportService()
    service.storage = type("S", (), {"get_file": lambda self, key: b"bytes"})()
    archive_bytes, _name = service.generate_export(None, user.id, documents, "2026-09")
    archive = zipfile.ZipFile(io.BytesIO(archive_bytes))
    review = archive.read("documentos_por_rever.csv").decode("utf-8")
    assert "Anulada" in review and "anulado" in review
    assert "Copia" in review and "duplicado" in review
    for row in review.splitlines():
        if "Anulada" in row or "Copia" in row:
            assert "por rever" not in row
    pdf_text = "\n".join(
        page.extract_text() or "" for page in PdfReader(io.BytesIO(archive.read("summary.pdf"))).pages
    )
    assert "anulado" in pdf_text
    assert "duplicado" in pdf_text


def test_backfill_does_not_rewrite_non_json_raw_text(db: Session):
    user = User(clerk_id=f"v6-raw-{uuid.uuid4().hex[:8]}", email="v6-raw@example.com")
    db.add(user)
    db.commit()
    common = dict(
        user_id=user.id,
        mime_type="image/jpeg",
        net_amount=Decimal("8.13"),
        vat_amount=Decimal("1.87"),
        gross_amount=Decimal("10.00"),
    )
    text_row = Document(
        storage_key="v6/text.jpg",
        original_filename="text.jpg",
        status="ready",
        document_type="FT",
        ocr_raw_response="Processing error",
        **common,
    )
    list_row = Document(
        storage_key="v6/list.jpg",
        original_filename="list.jpg",
        status="needs_review",
        document_type="FT",
        ocr_raw_response="[1, 2]",
        **common,
    )
    json_row = Document(
        storage_key="v6/json.jpg",
        original_filename="json.jpg",
        status="ready",
        document_type="NC",
        ocr_raw_response=json.dumps({"qr": {"document_type": "NC"}}),
        **common,
    )
    db.add_all([text_row, list_row, json_row])
    db.commit()
    backfill_document_types(db.connection())
    db.commit()
    db.expire_all()
    assert text_row.ocr_raw_response == "Processing error"
    assert text_row.document_type == "unclassified"
    assert text_row.status == "needs_review"
    assert list_row.ocr_raw_response == "[1, 2]"
    assert list_row.document_type == "unclassified"
    assert json.loads(json_row.ocr_raw_response)["qr"]["document_type"] == "NC"
    assert "_type_backup" in json.loads(json_row.ocr_raw_response)
    assert json_row.document_type == "NC"
    assert json_row.status == "ready"
    restore_document_types(db.connection())
    db.commit()
    db.expire_all()
    assert text_row.ocr_raw_response == "Processing error"
    assert list_row.ocr_raw_response == "[1, 2]"
    assert json.loads(json_row.ocr_raw_response) == {"qr": {"document_type": "NC"}}
    assert json_row.document_type == "NC"
    assert json_row.status == "ready"

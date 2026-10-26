"""QA gate 10. The printed-pair flag is not a general series override."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import date
from decimal import Decimal

import pytest
from pypdf import PdfReader

from app.models.audit_log import AuditLog
from app.models.document import Document
from app.schemas.document import SERIES_MISMATCH_DETAIL, invoice_series_prefix
from app.services.efatura import import_purchases
from app.services.export import ExportService
from app.services.iva_adjust import ACCEPTED_MISMATCH_HEADING
from tests.test_pr32_v8 import _efatura, _qr_row
from tests.test_qa_gate_ocr import _stored_receipt


@pytest.mark.parametrize(
    ("number", "prefix"),
    [
        ("Fr.12", None),
        ("Fs.12", None),
        ("Nc.12", None),
        ("NC1", None),
        ("nd.2026", None),
        ("Fr. 12", None),
        ("FRA 2026/12", None),
        ("NC.A/5", "NC"),
        ("fr.a", "FR"),
        ("NC2026/5", "NC"),
        ("ND2026/3", "ND"),
        ("NC1/5", "NC"),
    ],
)
def test_dot_digit_and_bare_nc1_are_not_a_series(number, prefix):
    assert invoice_series_prefix(number) == prefix


def test_abbreviations_save_on_an_ft_and_real_series_do_not(client, db, mock_user_headers):
    stored = _stored_receipt(db, document_type="FT", invoice_number="FT A/1", status="needs_review")
    for number in ("Fr.12", "Fs.12", "Nc.12", "NC1", "nd.2026"):
        saved = client.patch(
            f"/api/documents/{stored.id}",
            headers=mock_user_headers,
            json={"invoice_number": number},
        )
        assert saved.status_code == 200, number
        assert saved.json()["invoice_number"] == number

    for number in ("NC.A/5", "fr.a", "NC2026/5", "NC1/5"):
        rejected = client.patch(
            f"/api/documents/{stored.id}",
            headers=mock_user_headers,
            json={"invoice_number": number, "document_type": "FT"},
        )
        assert rejected.status_code == 422, number
        assert rejected.json()["detail"] == SERIES_MISMATCH_DETAIL

    # Dot then a letter is FR, inside the invoice family, so the flag can accept it.
    # A credit series on the same FT cannot.
    accepted = client.patch(
        f"/api/documents/{stored.id}",
        headers=mock_user_headers,
        json={"invoice_number": "fr.a", "document_type": "FT", "accept_series_mismatch": True},
    )
    assert accepted.status_code == 200, accepted.json()
    refused = client.patch(
        f"/api/documents/{stored.id}",
        headers=mock_user_headers,
        json={"invoice_number": "NC.A/5", "document_type": "FT", "accept_series_mismatch": True},
    )
    assert refused.status_code == 422
    assert refused.json()["detail"] == SERIES_MISMATCH_DETAIL


def test_readable_qr_rejects_a_mismatch_even_with_the_flag(client, db, mock_user_headers):
    stored = _qr_row(db, "FR", "FT 2026/12", status="ready")
    for payload in (
        {
            "document_type": "NC",
            "invoice_number": "FT 2026/12",
            "status": "ready",
            "accept_series_mismatch": True,
        },
        {
            "document_type": "FT",
            "invoice_number": "NC X/1",
            "status": "ready",
            "accept_series_mismatch": True,
        },
        {
            "document_type": "FR",
            "invoice_number": "NC X/1",
            "status": "ready",
            "accept_series_mismatch": True,
        },
    ):
        rejected = client.patch(
            f"/api/documents/{stored.id}",
            headers=mock_user_headers,
            json=payload,
        )
        assert rejected.status_code == 422, payload
        assert rejected.json()["detail"] == SERIES_MISMATCH_DETAIL
    db.refresh(stored)
    assert stored.document_type == "FR"
    assert stored.invoice_number == "FT 2026/12"
    assert stored.series_mismatch_accepted is False


def test_efatura_row_rejects_a_mismatch_even_with_the_flag(client, db, mock_user_headers):
    owner = _stored_receipt(db)
    imported = import_purchases(
        db,
        user_id=owner.user_id,
        taxpayer_nif="555555555",
        invoices=[_efatura("FR", "FT 2026/12", "V10QR")],
    )
    db.commit()
    document_id = imported.created[0]
    rejected = client.patch(
        f"/api/documents/{document_id}",
        headers=mock_user_headers,
        json={
            "document_type": "FS",
            "invoice_number": "FR 9/9",
            "accept_series_mismatch": True,
        },
    )
    assert rejected.status_code == 422
    assert rejected.json()["detail"] == SERIES_MISMATCH_DETAIL


@pytest.mark.parametrize(
    ("document_type", "number"),
    [
        ("NC", "FT A/12"),
        ("ND", "FT 2026/12"),
        ("FT", "NC A/5"),
        ("FR", "ND2026/3"),
        ("NC", "ND A/3"),
    ],
)
def test_credit_boundary_is_refused_even_with_the_flag(
    client, db, mock_user_headers, document_type, number
):
    stored = _stored_receipt(
        db,
        status="needs_review",
        document_type="unclassified",
        invoice_number=None,
        ocr_raw_response=None,
    )
    rejected = client.patch(
        f"/api/documents/{stored.id}",
        headers=mock_user_headers,
        json={
            "document_type": document_type,
            "invoice_number": number,
            "status": "ready",
            "accept_series_mismatch": True,
        },
    )
    assert rejected.status_code == 422, (document_type, number)
    assert rejected.json()["detail"] == SERIES_MISMATCH_DETAIL
    db.refresh(stored)
    assert stored.series_mismatch_accepted is False


def test_nc_numbered_as_an_ft_does_not_swallow_the_efatura_invoice(db):
    stored = _stored_receipt(
        db,
        status="needs_review",
        document_type="NC",
        invoice_number="FT A/12",
        vendor_nif="500829993",
        document_date=date(2026, 3, 2),
        ocr_raw_response=None,
    )
    debit = Document(
        user_id=stored.user_id,
        status="needs_review",
        storage_key="nd.jpg",
        original_filename="nd.jpg",
        mime_type="image/jpeg",
        vendor_nif="500829993",
        vendor_name="Armazem do Cais",
        invoice_number="FT A/12",
        document_type="ND",
        document_date=date(2026, 3, 2),
        net_amount=Decimal("10.00"),
        vat_amount=Decimal("2.30"),
        gross_amount=Decimal("12.30"),
    )
    db.add(debit)
    db.commit()
    imported = import_purchases(
        db,
        user_id=stored.user_id,
        taxpayer_nif="555555555",
        invoices=[_efatura("FT", "FT A/12", "V10FT")],
    )
    db.commit()
    assert imported.linked_existing == ()
    assert len(imported.created) == 1
    assert imported.created[0] not in {stored.id, debit.id}


def test_efatura_still_links_an_unclassified_row_and_an_ft(db):
    plain = _stored_receipt(
        db,
        document_type="unclassified",
        invoice_number="FT A/77",
        vendor_nif="500829993",
        status="needs_review",
    )
    linked = import_purchases(
        db,
        user_id=plain.user_id,
        taxpayer_nif="555555555",
        invoices=[_efatura("FT", "FT A/77", "V10PLAIN")],
    )
    db.commit()
    assert plain.id in linked.linked_existing
    assert linked.created == ()

    same = Document(
        user_id=plain.user_id,
        status="needs_review",
        storage_key="ft.jpg",
        original_filename="ft.jpg",
        mime_type="image/jpeg",
        vendor_nif="500829993",
        invoice_number="FT A/78",
        document_type="FT",
        net_amount=Decimal("10.00"),
        vat_amount=Decimal("2.30"),
        gross_amount=Decimal("12.30"),
    )
    db.add(same)
    db.commit()
    again = import_purchases(
        db,
        user_id=plain.user_id,
        taxpayer_nif="555555555",
        invoices=[_efatura("FT", "FT A/78", "V10SAME")],
    )
    db.commit()
    assert same.id in again.linked_existing


def test_printed_invoice_pair_is_stored_audited_and_listed(client, db, mock_user_headers):
    stored = _stored_receipt(
        db,
        status="needs_review",
        document_type="unclassified",
        invoice_number=None,
        ocr_raw_response='{"ocr":"unreadable"}',
        vendor_name="Oficina do Bairro",
        document_date=date(2026, 3, 15),
        expense_category="utilities",
    )
    rejected = client.patch(
        f"/api/documents/{stored.id}",
        headers=mock_user_headers,
        json={"document_type": "FR", "invoice_number": "FT 2026/12", "status": "ready"},
    )
    assert rejected.status_code == 422

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
    assert body["series_mismatch_accepted"] is True
    assert body["status"] == "ready"
    db.refresh(stored)
    assert stored.series_mismatch_accepted is True

    entry = (
        db.query(AuditLog)
        .filter(AuditLog.entity_id == stored.id, AuditLog.action == "series_mismatch_accepted")
        .one()
    )
    assert entry.user_id == stored.user_id
    assert entry.created_at is not None
    changes = json.loads(entry.changes_json)
    assert changes["document_type"]["new"] == "FR"
    assert changes["invoice_number"]["new"] == "FT 2026/12"
    assert changes["series_mismatch_accepted"]["new"] is True
    assert changes["accepted_at"]["new"]

    later = client.patch(
        f"/api/documents/{stored.id}",
        headers=mock_user_headers,
        json={"status": "ready"},
    )
    assert later.status_code == 422
    notes = client.patch(
        f"/api/documents/{stored.id}",
        headers=mock_user_headers,
        json={"review_notes": "par impresso"},
    )
    assert notes.status_code == 200
    db.refresh(stored)
    assert stored.series_mismatch_accepted is True

    summary = client.get(
        "/api/summary",
        params={"period_type": "quarter", "year": 2026, "quarter": 1},
        headers=mock_user_headers,
    )
    assert summary.status_code == 200, summary.text
    listed = summary.json()["series_mismatch_documents"]
    assert listed[0]["id"] == stored.id
    assert listed[0]["document_type"] == "FR"
    assert listed[0]["invoice_number"] == "FT 2026/12"
    assert summary.json()["series_mismatch_heading"] == ACCEPTED_MISMATCH_HEADING
    assert all(item["id"] != stored.id for item in summary.json()["excluded_documents"])
    assert Decimal(summary.json()["deductible_vat"]) == Decimal("2.30")

    projection = client.get(
        "/api/summary/projection",
        params={"year": 2026, "quarter": 1, "as_of": "2026-03-31"},
        headers=mock_user_headers,
    )
    assert projection.status_code == 200, projection.text
    projected = projection.json()["series_mismatch_documents"]
    assert projected[0]["invoice_number"] == "FT 2026/12"
    assert projection.json()["series_mismatch_heading"] == ACCEPTED_MISMATCH_HEADING

    service = ExportService()
    service.storage = type("S", (), {"get_file": lambda self, key: b"bytes"})()
    archive_bytes, _name = service.generate_export(db, stored.user_id, [stored], "2026-Q1")
    archive = zipfile.ZipFile(io.BytesIO(archive_bytes))
    accepted_csv = archive.read("pares_aceites.csv").decode("utf-8-sig")
    assert ACCEPTED_MISMATCH_HEADING in accepted_csv
    assert "FT 2026/12" in accepted_csv
    assert "FR" in accepted_csv
    summary_csv = archive.read("summary.csv").decode("utf-8-sig")
    assert summary_csv.splitlines()[0].startswith("ID;Data;Fornecedor;NIF;")
    pdf_text = "\n".join(
        page.extract_text() or "" for page in PdfReader(io.BytesIO(archive.read("summary.pdf"))).pages
    )
    assert ACCEPTED_MISMATCH_HEADING in pdf_text
    assert "FT 2026/12" in pdf_text

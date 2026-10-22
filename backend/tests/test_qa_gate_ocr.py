"""QA gate on the real-OCR branch.

Synthetic NIF 123456002 has a valid mod-11 check digit and replaces the real
company number that used to sit in these fixtures.
"""

from __future__ import annotations

import asyncio
import io
import logging
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas

from app.core.config import get_settings
from app.core.startup import ConfigurationError, validate_configuration
from app.schemas.document import DocumentUpdate
from app.services.iva_adjust import contributions
from app.services.ocr import OCRService, TesseractProbeError, resolve_ocr_backend, tesseract_gap
from app.services.ocr_extract import extract_fields
from app.services.storage import get_storage_service

SYNTHETIC_NIF = "123456002"
_JPEG = b"\xff\xd8\xff\xd9"


def _text_pdf(lines: list[str]) -> bytes:
    buffer = io.BytesIO()
    sheet = canvas.Canvas(buffer, pagesize=(420, 640))
    y = 600
    for line in lines:
        sheet.drawString(36, y, line)
        y -= 22
    sheet.save()
    return buffer.getvalue()


def _process(pdf: bytes, monkeypatch):
    monkeypatch.setattr(get_settings(), "ocr_backend", "tesseract")
    monkeypatch.setattr(get_settings(), "ollama_base_url", "")
    return asyncio.run(OCRService().process_document(pdf, "application/pdf"))


def test_issue_date_wins_over_text_due_date_end_to_end(monkeypatch):
    pdf = _text_pdf(
        [
            "Papelaria Exemplo Lda",
            f"NIF: {SYNTHETIC_NIF}",
            "Fatura FT A/12",
            "Data de emissao: 31-03-2026",
            "Vencimento: 30 de abril de 2026",
            "IVA 23% 10,00 2,30",
            "Total 12,30",
        ]
    )
    result = _process(pdf, monkeypatch)
    assert result.backend == "tesseract"
    assert (result.document_date, result.needs_review) == (date(2026, 3, 31), False)


def test_letterhead_text_date_beats_invoice_date():
    fields = extract_fields("Lisboa, 1 de maio de 2026\nData: 15/06/2026\nTotal 12,30")
    assert fields.document_date == date(2026, 6, 15)


def test_ambiguous_issue_dates_need_review():
    fields = extract_fields(
        "Loja Exemplo\n"
        f"NIF: {SYNTHETIC_NIF}\n"
        "Data: 15/06/2026\n"
        "Data de emissao: 31-03-2026\n"
        "IVA 23% 2,30\n"
        "Total 12,30"
    )
    assert fields.document_date == date(2026, 6, 15)
    assert fields.needs_review is True


def test_same_issue_date_twice_is_not_ambiguous():
    fields = extract_fields(
        "Loja Exemplo\n"
        f"NIF: {SYNTHETIC_NIF}\n"
        "Data: 15/06/2026\n"
        "Data de emissão: 15/06/2026\n"
        "IVA 23% 2,30\n"
        "Total 12,30"
    )
    assert fields.document_date == date(2026, 6, 15)
    assert fields.needs_review is False


def test_due_date_alone_is_not_the_issue_date():
    fields = extract_fields("Vencimento: 30 de abril de 2026\nTotal 12,30")
    assert fields.document_date is None
    assert fields.needs_review is True


def test_positive_invoice_iva_not_flipped():
    fields = extract_fields(
        f"Loja Exemplo\nNIF {SYNTHETIC_NIF}\nData 2026-03-31\nIVA 23%-2,30\nTotal 12,30"
    )
    assert (fields.vat_amount, fields.net_amount) == (Decimal("2.30"), Decimal("10.00"))


def test_total_hyphen_separator_not_negative():
    assert extract_fields("Total-12,30").gross_amount == Decimal("12.30")
    assert extract_fields("Total:-12,30").gross_amount == Decimal("12.30")
    assert extract_fields("Total EUR-12,30").gross_amount == Decimal("12.30")


def test_spaced_minus_on_a_positive_invoice_is_negative():
    assert extract_fields("Total -12,30").gross_amount == Decimal("-12.30")
    assert extract_fields("Total: -12,30").gross_amount == Decimal("-12.30")


def test_ocr_only_credit_note_nets_negative():
    fields = extract_fields("Nota de credito NC Q2\nData 2026-04-15\nIVA 23% 1,87\nTotal -10,00")
    assert fields.invoice_number == "NC Q2"
    assert fields.gross_amount == Decimal("-10.00")
    assert fields.vat_amount == Decimal("-1.87")
    assert fields.net_amount == Decimal("-8.13")


def test_credit_note_glued_minus_stays_negative():
    assert extract_fields("Nota de credito NC Q2\nTotal-10,00").gross_amount == Decimal("-10.00")


def test_credit_note_negative_gross_counts_in_iva_netting():
    document = SimpleNamespace(
        id="nc1",
        status="ready",
        net_amount=Decimal("-8.13"),
        vat_amount=Decimal("-1.87"),
        gross_amount=Decimal("-10.00"),
        ocr_raw_response='{"backend":"tesseract"}',
        created_at=None,
        document_date=date(2026, 4, 15),
        vendor_nif=SYNTHETIC_NIF,
    )
    assert contributions([document])[0].vat == Decimal("-1.87")
    assert contributions([document])[0].net == Decimal("-8.13")
    assert contributions([document])[0].gross == Decimal("-10.00")


def test_review_form_can_save_ocr_credit_note_gross():
    updated = DocumentUpdate(gross_amount=Decimal("-10.00"), vendor_name="x", status="ready")
    assert updated.gross_amount == Decimal("-10.00")
    assert updated.vat_amount is None


def test_review_patch_saves_negative_credit_note(client: TestClient, mock_user_headers: dict):
    upload = client.post(
        "/api/documents/upload-url",
        headers=mock_user_headers,
        json={"filename": "nc.jpg", "content_type": "image/jpeg"},
    )
    storage_key = upload.json()["storage_key"]
    client.put(get_storage_service().get_upload_url(storage_key, "image/jpeg"), content=_JPEG)
    created = client.post(
        "/api/documents",
        headers=mock_user_headers,
        json={
            "storage_key": storage_key,
            "original_filename": "nc.jpg",
            "mime_type": "image/jpeg",
            "file_size": len(_JPEG),
        },
    )
    document_id = created.json()["id"]
    response = client.patch(
        f"/api/documents/{document_id}",
        headers=mock_user_headers,
        json={
            "vendor_name": "x",
            "status": "ready",
            "gross_amount": "-10.00",
            "vat_amount": "-1.87",
            "net_amount": "-8.13",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert Decimal(str(body["gross_amount"])) == Decimal("-10.00")
    assert Decimal(str(body["vat_amount"])) == Decimal("-1.87")
    assert Decimal(str(body["net_amount"])) == Decimal("-8.13")


def test_series_prefix_not_doubled():
    assert extract_fields("FT FT2026/1").invoice_number == "FT2026/1"


def test_credit_note_number_not_original_invoice():
    fields = extract_fields("Referente a fatura FT A/12\nNota de credito NC Q2/7\nTotal -10,00")
    assert fields.invoice_number == "NC Q2/7"


def test_abbreviated_portuguese_months():
    assert extract_fields("Data: 15/set/2026\nTotal 1,00").document_date == date(2026, 9, 15)
    assert extract_fields("Data: 2 de fev. de 2026\nTotal 1,00").document_date == date(2026, 2, 2)
    assert extract_fields("Data: 15 de set. de 2026\nTotal 1,00").document_date == date(2026, 9, 15)


def test_crashing_binary_is_not_reported_as_missing_packs(monkeypatch):
    monkeypatch.setattr(get_settings(), "ocr_backend", "tesseract")
    monkeypatch.setattr("app.services.ocr.tesseract_available", lambda: True)

    def boom():
        raise TesseractProbeError("crash")

    monkeypatch.setattr("app.services.ocr.tesseract_languages", boom)
    assert tesseract_gap() == "the tesseract binary failed to run"
    with pytest.raises(ConfigurationError, match="failed to run") as raised:
        validate_configuration()
    assert "language packs are missing" not in str(raised.value)


def test_corrupt_language_pack_fails_the_load_check(monkeypatch):
    monkeypatch.setattr(get_settings(), "ocr_backend", "tesseract")
    monkeypatch.setattr("app.services.ocr.tesseract_available", lambda: True)
    monkeypatch.setattr("app.services.ocr.tesseract_languages", lambda: frozenset({"por", "eng", "osd"}))
    monkeypatch.setattr("app.services.ocr.tesseract_packs_load", lambda: False)
    gap = tesseract_gap()
    assert gap == "language packs failed to load (tesseract-ocr-por, tesseract-ocr-eng)"
    assert "are missing" not in gap
    with pytest.raises(ConfigurationError, match="failed to load"):
        validate_configuration()


def test_unknown_ocr_backend_is_not_silent_mock(monkeypatch, caplog):
    monkeypatch.setattr(get_settings(), "ocr_backend", "tesseract-ocr")
    with caplog.at_level(logging.ERROR, logger="app.services.ocr"):
        assert resolve_ocr_backend() == "tesseract-ocr"
    assert any("not a known backend" in record.message for record in caplog.records)
    with pytest.raises(ConfigurationError, match="not a known backend"):
        validate_configuration()
    result = asyncio.run(OCRService().process_document(b"%PDF-1.4", "application/pdf"))
    assert result.backend == "tesseract-ocr"
    assert result.error == "Unknown OCR backend tesseract-ocr"


def test_production_refuses_mock_and_auto(monkeypatch):
    monkeypatch.setattr(get_settings(), "app_env", "production")
    monkeypatch.setattr("app.services.ocr.tesseract_gap", lambda: None)
    for backend in ("auto", "mock"):
        monkeypatch.setattr(get_settings(), "ocr_backend", backend)
        with pytest.raises(ConfigurationError, match="OCR_BACKEND must be tesseract or azure"):
            validate_configuration()


def test_auto_fallback_marks_health_degraded_in_production(client: TestClient, monkeypatch):
    monkeypatch.setattr(get_settings(), "ocr_backend", "auto")
    monkeypatch.setattr(get_settings(), "app_env", "production")
    monkeypatch.setattr("app.services.ocr.tesseract_available", lambda: False)
    with pytest.raises(ConfigurationError, match="OCR_BACKEND must be tesseract or azure"):
        validate_configuration()
    health = client.get("/health")
    assert health.status_code == 503
    body = health.json()
    assert body["status"] == "degraded"
    assert body["ocr_backend"] == "mock"
    assert body["tesseract"] is False

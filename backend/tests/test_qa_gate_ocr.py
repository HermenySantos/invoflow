"""QA gate on the real-OCR branch.

123456002 is a synthetic placeholder, not verified unissued. Decreto-Lei
n.º 14/2013, art. 4.º n.º 2, assigns first digit 1-4 to a pessoa singular,
so the number is not a company NIF. It is not proven unissued.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import shutil
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from reportlab.pdfgen import canvas
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.startup import ConfigurationError, validate_configuration
from app.models.document import Document
from app.models.user import User
from app.schemas.document import AMOUNT_MISMATCH_DETAIL, DocumentUpdate
from app.services.categorization import deductible_vat_split
from app.services.iva_adjust import _signed, contributions, credit_note_warnings, fiscal_mark
from app.services.legacy_amounts import repair_legacy_negative_amounts
from app.services.ocr import (
    OCRService,
    TesseractProbeError,
    probe_tesseract_language,
    resolve_ocr_backend,
    tesseract_gap,
)
from app.services.ocr_extract import extract_fields
from app.services.storage import get_storage_service

# Pessoa singular range (DL 14/2013 art. 4.º). Not a company. Not verified unissued.
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
            "Ana Exemplo",
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
        "Ana Exemplo\n"
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
        "Fatura FT A/12\n"
        "Ana Exemplo\n"
        f"NIF: {SYNTHETIC_NIF}\n"
        "Data: 15/06/2026\n"
        "Data de emissão: 15/06/2026\n"
        "IVA 23% 2,30\n"
        "Total 12,30"
    )
    assert fields.document_date == date(2026, 6, 15)
    assert fields.document_type == "FT"
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


def test_spaced_minus_is_stored_positive_and_needs_review():
    fields = extract_fields("Total -12,30")
    assert fields.gross_amount == Decimal("12.30")
    assert fields.document_type == "unclassified"
    assert fields.needs_review is True
    assert extract_fields("Total: -12,30").gross_amount == Decimal("12.30")


def test_same_line_issue_date_beats_due_date():
    fields = extract_fields("Data: 31-03-2026   Vencimento: 30-04-2026\nTotal 12,30")
    assert fields.document_date == date(2026, 3, 31)
    assert fields.needs_review is True


def test_due_matches_on_word_boundaries():
    fields = extract_fields("overdue 30-04-2026\nTotal 1,00")
    assert fields.document_date == date(2026, 4, 30)


def test_discount_line_is_not_the_total():
    assert extract_fields("Desconto -2,00").gross_amount is None
    fields = extract_fields("Total 12,30 Desconto -2,00")
    assert fields.gross_amount == Decimal("12.30")
    assert fields.document_type == "unclassified"


def test_positive_printed_ocr_credit_note_is_nc_and_needs_review():
    fields = extract_fields(
        "Nota de credito NC Q2\n"
        f"NIF {SYNTHETIC_NIF}\n"
        "Data 2026-04-15\n"
        "IVA 23% 1,87\n"
        "Total 10,00"
    )
    assert fields.document_type == "unclassified"
    assert fields.invoice_number == "NC Q2"
    assert (fields.gross_amount, fields.vat_amount, fields.net_amount) == (
        Decimal("10.00"),
        Decimal("1.87"),
        Decimal("8.13"),
    )
    assert fields.needs_review is True


def test_printed_minus_credit_note_stores_absolute_amounts():
    fields = extract_fields("Nota de credito NC Q2\nData 2026-04-15\nIVA 23% 1,87\nTotal -10,00")
    assert fields.document_type == "unclassified"
    assert fields.invoice_number == "NC Q2"
    assert fields.gross_amount == Decimal("10.00")
    assert fields.vat_amount == Decimal("1.87")
    assert fields.net_amount == Decimal("8.13")
    assert fields.needs_review is True


def test_credit_note_glued_hyphen_is_not_a_minus():
    fields = extract_fields("Nota de credito NC Q2\nTotal-10,00")
    assert fields.gross_amount == Decimal("10.00")
    assert fields.document_type == "unclassified"


def test_footer_mention_does_not_make_a_credit_note():
    fields = extract_fields(
        "Fatura FT A/12\n"
        f"NIF {SYNTHETIC_NIF}\n"
        "Data: 31-03-2026\n"
        "IVA 23% 2,30\n"
        "Total 12,30\n"
        "\n"
        "Obrigado\n"
        "emitimos nota de credito em 30 dias"
    )
    assert fields.document_type == "unclassified"
    assert fields.invoice_number == "FT A/12"
    assert fields.gross_amount == Decimal("12.30")
    assert fields.needs_review is True


def test_plano_nc_does_not_change_parsing():
    fields = extract_fields(
        "Fatura FT A/12\n"
        f"NIF {SYNTHETIC_NIF}\n"
        "Data: 31-03-2026\n"
        "Plano nc\n"
        "IVA 23% 2,30\n"
        "Total 12,30"
    )
    assert fields.document_type == "FT"
    assert fields.invoice_number == "FT A/12"
    assert fields.gross_amount == Decimal("12.30")


def test_ft_that_cites_an_nc_keeps_the_ft_number():
    fields = extract_fields("Fatura FT A/12\nReferente a nota de credito NC Q2/7\nTotal 12,30")
    assert fields.invoice_number == "FT A/12"
    assert fields.document_type == "unclassified"
    assert fields.needs_review is True


def test_ocr_credit_note_nets_by_type_and_warns_without_an_invoice():
    fields = extract_fields("Nota de credito NC Q2\nData 2026-04-15\nIVA 23% 1,87\nTotal 10,00")
    document = SimpleNamespace(
        id="nc-ocr",
        status="ready",
        net_amount=fields.net_amount,
        vat_amount=fields.vat_amount,
        gross_amount=fields.gross_amount,
        invoice_number=fields.invoice_number,
        ocr_raw_response=json.dumps({"backend": "tesseract", "document_type": fields.document_type}),
        expense_category="utilities",
        deductible_pct_override=None,
        created_at=None,
        document_date=date(2026, 4, 15),
        vendor_nif=SYNTHETIC_NIF,
        vendor_name="Ana Exemplo",
        document_type="NC",
    )
    assert fields.document_type == "unclassified"
    counted = contributions([document])[0]
    assert (counted.vat, counted.net, counted.gross) == (
        Decimal("-1.87"),
        Decimal("-8.13"),
        Decimal("-10.00"),
    )
    warnings = credit_note_warnings([document], [])
    assert any("nota de crédito sem fatura associada" in warning for warning in warnings)


def test_negative_fields_do_not_cancel_an_nc_type():
    document = SimpleNamespace(
        id="nc-bad",
        status="ready",
        net_amount=Decimal("8.13"),
        vat_amount=Decimal("1.87"),
        gross_amount=Decimal("-10.00"),
        ocr_raw_response='{"qr":{"document_type":"NC"}}',
        expense_category="utilities",
        deductible_pct_override=None,
        created_at=None,
        document_date=date(2026, 4, 15),
        vendor_nif=SYNTHETIC_NIF,
    )
    # The type still applies the minus after abs. The triple does not add up
    # (8.13 + 1.87 != -10), so the counted totals leave the row out.
    assert _signed(document, fiscal_mark(document)).vat == Decimal("-1.87")
    assert contributions([document]) == []
    confirmed, pending = deductible_vat_split([document])
    assert confirmed == Decimal("0.00")
    assert pending == Decimal("0.00")


def test_ft_with_all_negative_amounts_counts_positive():
    document = SimpleNamespace(
        id="ft-neg",
        status="ready",
        net_amount=Decimal("-8.13"),
        vat_amount=Decimal("-1.87"),
        gross_amount=Decimal("-10.00"),
        ocr_raw_response='{"qr":{"document_type":"FT"}}',
        created_at=None,
        document_date=date(2026, 3, 31),
        vendor_nif=SYNTHETIC_NIF,
    )
    counted = contributions([document])[0]
    assert (counted.vat, counted.net, counted.gross) == (
        Decimal("1.87"),
        Decimal("8.13"),
        Decimal("10.00"),
    )


def test_mixed_signs_and_inconsistent_amounts_are_rejected():
    with pytest.raises(ValidationError):
        DocumentUpdate(gross_amount=Decimal("10.00"), vat_amount=Decimal("-1.87"), net_amount=Decimal("8.13"))
    with pytest.raises(ValidationError):
        DocumentUpdate(gross_amount=Decimal("-10.00"))
    with pytest.raises(ValidationError, match="O valor líquido mais o IVA tem de ser igual ao total"):
        DocumentUpdate(
            gross_amount=Decimal("12.30"),
            vat_amount=Decimal("1.00"),
            net_amount=Decimal("10.00"),
        )
    assert DocumentUpdate(
        gross_amount=Decimal("10.00"),
        vat_amount=Decimal("1.87"),
        net_amount=Decimal("8.13"),
    ).gross_amount == Decimal("10.00")


def test_review_patch_rejects_a_negative_credit_note(client: TestClient, db: Session, mock_user_headers: dict):
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
    stored = db.query(Document).filter(Document.id == document_id).one()
    stored.status = "ready"
    stored.vendor_name = "Ana Exemplo"
    stored.vendor_nif = SYNTHETIC_NIF
    stored.document_date = date(2026, 4, 15)
    stored.net_amount = Decimal("8.13")
    stored.vat_amount = Decimal("1.87")
    stored.gross_amount = Decimal("10.00")
    stored.expense_category = "utilities"
    stored.ocr_raw_response = json.dumps({"qr": {"document_type": "NC", "fiscal_status": "N"}})
    db.commit()

    rejected = client.patch(
        f"/api/documents/{document_id}",
        headers=mock_user_headers,
        json={"gross_amount": "-10.00", "status": "ready"},
    )
    assert rejected.status_code == 422
    db.refresh(stored)
    assert stored.gross_amount == Decimal("10.00")
    confirmed, pending = deductible_vat_split([stored])
    assert confirmed == Decimal("-1.87")
    assert pending == Decimal("0.00")

    partial = client.patch(
        f"/api/documents/{document_id}",
        headers=mock_user_headers,
        json={"gross_amount": "100.50"},
    )
    assert partial.status_code == 422
    assert partial.json()["detail"] == AMOUNT_MISMATCH_DETAIL
    db.refresh(stored)
    assert stored.gross_amount == Decimal("10.00")
    assert stored.net_amount == Decimal("8.13")
    assert stored.vat_amount == Decimal("1.87")


def test_series_prefix_not_doubled():
    assert extract_fields("FT FT2026/1").invoice_number == "FT2026/1"


def test_credit_note_number_not_original_invoice():
    fields = extract_fields("Nota de credito NC Q2/7\nReferente a fatura FT A/12\nTotal -10,00")
    assert fields.invoice_number == "NC Q2/7"
    assert fields.document_type == "unclassified"


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


def _eng_traineddata() -> Path | None:
    found = sorted(Path("/usr/share").glob("**/eng.traineddata"))
    return found[0] if found else None


@pytest.mark.ocr_corpus
def test_corrupt_por_pack_file_fails_the_load_check(tmp_path):
    """Runs Tesseract against a real corrupt por.traineddata. Not a monkeypatch."""
    if shutil.which("tesseract") is None:
        pytest.skip("tesseract binary is not installed")
    eng = _eng_traineddata()
    if eng is None:
        pytest.skip("eng.traineddata is not installed")
    shutil.copy(eng, tmp_path / "eng.traineddata")
    (tmp_path / "por.traineddata").write_bytes(b"this is not a tesseract language pack\n")
    failure = probe_tesseract_language("por", tessdata_dir=str(tmp_path))
    assert failure is not None
    assert "tesseract-ocr-por" in failure
    assert "missing" not in failure
    assert probe_tesseract_language("eng", tessdata_dir=str(tmp_path)) is None


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
    import app.services.ocr as ocr_module

    ocr_module._unknown_backend_logged = False
    monkeypatch.setattr(get_settings(), "ocr_backend", "tesseract-ocr")
    with caplog.at_level(logging.ERROR, logger="app.services.ocr"):
        assert resolve_ocr_backend() == "tesseract-ocr"
        assert resolve_ocr_backend() == "tesseract-ocr"
    errors = [record for record in caplog.records if "not a known backend" in record.message]
    assert len(errors) == 1
    assert errors[0].levelno == logging.ERROR
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


def _complete_ft(*extra: str) -> str:
    return "\n".join(
        [
            "Ana Exemplo",
            f"NIF: {SYNTHETIC_NIF}",
            "Data: 15/06/2026",
            "Data de emissão: 15/06/2026",
            "Fatura FT A/12",
            "IVA 23% 2,30",
            "Total 12,30",
            *extra,
        ]
    )


@pytest.mark.parametrize(
    "line",
    [
        "Regulariza NC Q2/7",
        "Anula a NC Q2/7",
        "Nota de credito: NC Q2/7",
    ],
)
def test_citation_and_field_lines_do_not_type_the_document(line: str):
    fields = extract_fields(_complete_ft(line))
    assert fields.document_type == "unclassified"
    assert fields.invoice_number == "FT A/12"
    assert fields.gross_amount == Decimal("12.30")
    assert fields.needs_review is True


def test_title_that_cites_an_invoice_keeps_its_own_number():
    fields = extract_fields(
        "Ana Exemplo\n"
        "Nota de crédito NC Q2/7 referente à fatura FT A/12\n"
        f"NIF: {SYNTHETIC_NIF}\n"
        "Data: 15/06/2026\n"
        "Data de emissão: 15/06/2026\n"
        "IVA 23% 1,87\n"
        "Total 10,00"
    )
    assert fields.document_type == "unclassified"
    assert fields.invoice_number == "NC Q2/7"
    assert fields.gross_amount == Decimal("10.00")
    assert fields.needs_review is True


def test_credit_title_below_the_letterhead_is_still_nc():
    letterhead = "\n".join(f"Linha de cabecalho {index}" for index in range(1, 9))
    fields = extract_fields(
        f"{letterhead}\n"
        "Nota de crédito NC Q2/7\n"
        f"NIF: {SYNTHETIC_NIF}\n"
        "Data: 15/06/2026\n"
        "Data de emissão: 15/06/2026\n"
        "IVA 23% 1,87\n"
        "Total 10,00"
    )
    assert fields.document_type == "unclassified"
    assert fields.invoice_number == "NC Q2/7"
    assert fields.needs_review is True


def test_broken_base_iva_total_is_not_auto_confirmed():
    fields = extract_fields(
        "Ana Exemplo\n"
        f"NIF: {SYNTHETIC_NIF}\n"
        "Data: 15/06/2026\n"
        "Data de emissão: 15/06/2026\n"
        "Base 10,00\n"
        "IVA 2,30\n"
        "Total 15,00"
    )
    assert (fields.net_amount, fields.vat_amount, fields.gross_amount) == (
        Decimal("10.00"),
        Decimal("2.30"),
        Decimal("15.00"),
    )
    assert fields.document_type == "unclassified"
    assert fields.needs_review is True


def _stored_receipt(db: Session, **overrides) -> Document:
    """A row owned by the mock user, without spending the upload rate limit."""
    user = User(clerk_id="test-user-001", email="test@example.com")
    db.add(user)
    db.commit()
    fields = dict(
        user_id=user.id,
        status="needs_review",
        storage_key=f"{user.clerk_id}/recibo.jpg",
        original_filename="recibo.jpg",
        mime_type="image/jpeg",
        vendor_name="Ana Exemplo",
        vendor_nif=SYNTHETIC_NIF,
        expense_category="utilities",
        document_type="FT",
        net_amount=Decimal("10.00"),
        vat_amount=Decimal("2.30"),
        gross_amount=Decimal("12.30"),
    )
    fields.update(overrides)
    document = Document(**fields)
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


def test_iva_one_field_patch_then_ready_is_rejected(
    client: TestClient, db: Session, mock_user_headers: dict
):
    stored = _stored_receipt(db)
    document_id = stored.id

    partial = client.patch(
        f"/api/documents/{document_id}",
        headers=mock_user_headers,
        json={"vat_amount": "9.99"},
    )
    assert partial.status_code == 200
    assert partial.json()["document_type"] == "FT"
    db.refresh(stored)
    assert stored.vat_amount == Decimal("9.99")
    assert stored.status == "needs_review"
    confirmed, pending = deductible_vat_split([stored])
    assert confirmed == Decimal("0.00")
    assert pending == Decimal("0.00")

    for next_status in ("ready", "accountant_review"):
        rejected = client.patch(
            f"/api/documents/{document_id}",
            headers=mock_user_headers,
            json={"status": next_status},
        )
        assert rejected.status_code == 422
        assert rejected.json()["detail"] == AMOUNT_MISMATCH_DETAIL
        db.refresh(stored)
        assert stored.status == "needs_review"


def test_receipt_gross_correction_saves_when_net_is_sent(
    client: TestClient, db: Session, mock_user_headers: dict
):
    stored = _stored_receipt(db)
    document_id = stored.id

    missing_net = client.patch(
        f"/api/documents/{document_id}",
        headers=mock_user_headers,
        json={"gross_amount": "15.00", "vat_amount": "2.30", "status": "ready"},
    )
    assert missing_net.status_code == 422
    assert missing_net.json()["detail"] == AMOUNT_MISMATCH_DETAIL
    db.refresh(stored)
    assert stored.gross_amount == Decimal("12.30")
    assert stored.status == "needs_review"

    saved = client.patch(
        f"/api/documents/{document_id}",
        headers=mock_user_headers,
        json={
            "gross_amount": "15.00",
            "vat_amount": "2.30",
            "net_amount": "12.70",
            "status": "ready",
        },
    )
    assert saved.status_code == 200
    body = saved.json()
    assert Decimal(str(body["gross_amount"])) == Decimal("15.00")
    assert Decimal(str(body["vat_amount"])) == Decimal("2.30")
    assert Decimal(str(body["net_amount"])) == Decimal("12.70")
    assert body["status"] == "ready"
    db.refresh(stored)
    confirmed, pending = deductible_vat_split([stored])
    assert confirmed == Decimal("2.30")
    assert pending == Decimal("0.00")


def test_reviewer_type_change_reruns_netting(
    client: TestClient, db: Session, mock_user_headers: dict
):
    stored = _stored_receipt(
        db,
        status="ready",
        document_type="NC",
        net_amount=Decimal("8.13"),
        vat_amount=Decimal("1.87"),
        gross_amount=Decimal("10.00"),
        ocr_raw_response=json.dumps({"qr": {"document_type": "NC", "fiscal_status": "N"}}),
    )
    document_id = stored.id
    fetched = client.get(f"/api/documents/{document_id}", headers=mock_user_headers)
    assert fetched.status_code == 200
    assert fetched.json()["document_type"] == "NC"
    assert deductible_vat_split([stored])[0] == Decimal("-1.87")

    changed = client.patch(
        f"/api/documents/{document_id}",
        headers=mock_user_headers,
        json={"document_type": "FT"},
    )
    assert changed.status_code == 200
    assert changed.json()["document_type"] == "FT"
    db.refresh(stored)
    assert stored.document_type == "FT"
    assert stored.status == "needs_review"
    confirmed, pending = deductible_vat_split([stored])
    assert confirmed == Decimal("0.00")
    assert pending == Decimal("1.87")

    rejected = client.patch(
        f"/api/documents/{document_id}",
        headers=mock_user_headers,
        json={"document_type": "nota"},
    )
    assert rejected.status_code == 422
    db.refresh(stored)
    assert stored.document_type == "FT"


def test_legacy_negative_amounts_become_absolute_credit_notes(db: Session):
    user = User(clerk_id=f"legacy-{uuid.uuid4().hex[:8]}", email="")
    db.add(user)
    db.commit()
    document = Document(
        user_id=user.id,
        status="ready",
        storage_key=f"{user.clerk_id}/old.jpg",
        original_filename="old.jpg",
        mime_type="image/jpeg",
        vendor_nif=SYNTHETIC_NIF,
        expense_category="utilities",
        document_date=date(2026, 4, 15),
        net_amount=Decimal("-8.13"),
        vat_amount=Decimal("1.87"),
        gross_amount=Decimal("-10.00"),
    )
    db.add(document)
    db.commit()

    repair_legacy_negative_amounts(db.connection())
    db.commit()
    repair_legacy_negative_amounts(db.connection())
    db.commit()
    db.refresh(document)

    assert document.document_type == "unclassified"
    assert document.status == "needs_review"
    assert document.net_amount == Decimal("8.13")
    assert document.vat_amount == Decimal("1.87")
    assert document.gross_amount == Decimal("10.00")
    assert contributions([document]) == []

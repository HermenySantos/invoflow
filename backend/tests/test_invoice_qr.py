"""
The Portuguese invoice QR (AT) is read before OCR and its amounts win.
"""

import builtins
import io
import logging
import uuid
from datetime import date
from decimal import Decimal

import pytest
import zxingcpp
from pypdf import PdfReader
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from app.services.ocr import _pdf_first_page_image
from app.services.pt_qr import parse_invoice_qr, read_invoice_qr
from app.services.storage import get_storage_service

MAINLAND = (
    "A:123456002*B:999999990*C:PT*D:FT*E:N*F:20260915*G:FT A/12*H:ABCD1234-12*"
    "I1:PT*I3:10.00*I4:0.60*I7:20.00*I8:4.60*N:5.20*O:35.20*Q:abcd*R:1234"
)


def fatura_photo(payload: str) -> Image.Image:
    """A white 'paper' with some smudged text and the QR in a corner."""
    page = Image.new("RGB", (600, 800), "white")
    draw = ImageDraw.Draw(page)
    draw.text((40, 40), "Pingo Doce", fill="black")
    draw.text((40, 300), "I V A  ..  ,  ?", fill=(180, 180, 180))  # unreadable IVA line
    qr = zxingcpp.write_barcode_to_image(zxingcpp.create_barcode(payload, zxingcpp.BarcodeFormat.QRCode), scale=4)
    page.paste(Image.fromarray(qr).convert("RGB"), (380, 560))
    return page


def test_mainland_qr_with_two_rates():
    qr = parse_invoice_qr(MAINLAND)
    assert qr.vendor_nif == "123456002"
    assert qr.document_date == date(2026, 9, 15)
    assert qr.invoice_number == "FT A/12"
    assert qr.net_amount == Decimal("30.00")
    assert qr.vat_amount == Decimal("5.20")
    assert qr.gross_amount == Decimal("35.20")
    assert qr.vat_rate is None
    assert [entry["rate"] for entry in qr.breakdown] == ["6.00", "23.00"]


def test_madeira_qr_with_one_rate():
    qr = parse_invoice_qr("A:511111111*F:20260901*G:FS B/3*I1:PT-MA*I7:50.00*I8:11.00*N:11.00*O:61.00")
    assert qr.vat_rate == Decimal("22.00")
    assert qr.net_amount == Decimal("50.00")


def test_other_qr_codes_are_ignored():
    assert parse_invoice_qr("https://example.com/menu") is None


def test_qr_is_found_in_a_photo():
    assert read_invoice_qr(fatura_photo(MAINLAND)).gross_amount == Decimal("35.20")


def test_upload_stores_the_qr_totals(client: TestClient):
    document = _upload(client, _png_bytes(fatura_photo(MAINLAND)), "fatura.png", "image/png")

    assert document["vendor_nif"] == "123456002"
    assert document["invoice_number"] == "FT A/12"
    assert document["document_date"] == "2026-09-15"
    assert document["gross_amount"] == "35.20"
    assert document["vat_amount"] == "5.20"
    assert document["net_amount"] == "30.00"


def test_upload_reads_an_at_qr_embedded_in_a_pdf(client: TestClient):
    document = _upload(client, _pdf_bytes(fatura_photo(MAINLAND)), "fatura.pdf", "application/pdf")

    assert document["vendor_nif"] == "123456002"
    assert document["invoice_number"] == "FT A/12"
    assert document["document_date"] == "2026-09-15"
    assert document["gross_amount"] == "35.20"
    assert document["vat_amount"] == "5.20"
    assert document["net_amount"] == "30.00"


def test_upload_reads_the_qr_on_a_narrow_thermal_receipt(client: TestClient):
    """80 mm by 3000 pt is a long till roll, not a page that is huge in both directions."""
    content = _thermal_pdf(MAINLAND)
    box = PdfReader(io.BytesIO(content)).pages[0].mediabox
    short, long = sorted((abs(float(box.width)), abs(float(box.height))))
    assert short == pytest.approx(80 * mm, rel=0.01)
    assert long == pytest.approx(3000, rel=0.01)

    document = _upload(client, content, "talao.pdf", "application/pdf")

    assert document["vendor_nif"] == "123456002"
    assert document["invoice_number"] == "FT A/12"
    assert document["gross_amount"] == "35.20"
    assert document["status"] != "failed"


def test_missing_poppler_logs_a_warning(monkeypatch, caplog):
    import pdf2image
    from pdf2image.exceptions import PDFInfoNotInstalledError

    def boom(*_args, **_kwargs):
        raise PDFInfoNotInstalledError("poppler is not installed")

    monkeypatch.setattr(pdf2image, "convert_from_bytes", boom)
    with caplog.at_level(logging.WARNING, logger="app.services.ocr"):
        assert _pdf_first_page_image(b"%PDF-1.4") is None
    assert any("poppler" in record.message.lower() for record in caplog.records)


def test_missing_pdf2image_logs_a_warning(monkeypatch, caplog):
    real_import = builtins.__import__

    def guarded(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "pdf2image" or name.startswith("pdf2image."):
            raise ImportError("pdf2image is not installed")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded)
    with caplog.at_level(logging.WARNING, logger="app.services.ocr"):
        assert _pdf_first_page_image(b"%PDF-1.4") is None
    assert any("pdf2image" in record.message for record in caplog.records)


def _png_bytes(page: Image.Image) -> bytes:
    buffer = io.BytesIO()
    page.save(buffer, format="PNG")
    return buffer.getvalue()


def _thermal_pdf(payload: str) -> bytes:
    """A till roll: 80 mm wide and 3000 pt long, with the AT QR near the bottom."""
    width_pt = 80 * mm
    height_pt = 3000
    qr = Image.fromarray(
        zxingcpp.write_barcode_to_image(
            zxingcpp.create_barcode(payload, zxingcpp.BarcodeFormat.QRCode),
            scale=8,
        )
    ).convert("RGB")
    png = io.BytesIO()
    qr.save(png, format="PNG")
    png.seek(0)
    out = io.BytesIO()
    pdf = canvas.Canvas(out, pagesize=(width_pt, height_pt))
    pdf.drawString(8, height_pt - 24, "Talão")
    pdf.drawImage(ImageReader(png), 12, 24, width=width_pt - 24, height=width_pt - 24)
    pdf.save()
    return out.getvalue()


def _pdf_bytes(page: Image.Image) -> bytes:
    png = io.BytesIO(_png_bytes(page))
    out = io.BytesIO()
    pdf = canvas.Canvas(out, pagesize=(page.width, page.height))
    pdf.drawImage(ImageReader(png), 0, 0, width=page.width, height=page.height)
    pdf.save()
    return out.getvalue()


def _upload(client: TestClient, content: bytes, filename: str, mime_type: str) -> dict:
    headers = {"X-Mock-User-Id": f"test-user-{uuid.uuid4().hex[:8]}"}
    key = f"{headers['X-Mock-User-Id']}/2026/09/{uuid.uuid4().hex[:8]}_{filename}"
    client.put(get_storage_service().get_upload_url(key, mime_type), content=content)
    created = client.post(
        "/api/documents",
        json={
            "storage_key": key,
            "original_filename": filename,
            "file_size": len(content),
            "mime_type": mime_type,
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    document = client.get(f"/api/documents/{created.json()['id']}", headers=headers)
    assert document.status_code == 200, document.text
    return document.json()

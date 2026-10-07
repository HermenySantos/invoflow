"""
The Portuguese invoice QR (AT) is read before OCR and its amounts win.
"""

import io
import uuid
from datetime import date
from decimal import Decimal

import zxingcpp
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app.services.pt_qr import parse_invoice_qr, read_invoice_qr
from app.services.storage import get_storage_service

MAINLAND = (
    "A:503504564*B:999999990*C:PT*D:FT*E:N*F:20260915*G:FT A/12*H:ABCD1234-12*"
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
    assert qr.vendor_nif == "503504564"
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
    headers = {"X-Mock-User-Id": f"test-user-{uuid.uuid4().hex[:8]}"}
    buffer = io.BytesIO()
    fatura_photo(MAINLAND).save(buffer, format="PNG")
    key = f"{headers['X-Mock-User-Id']}/2026/09/{uuid.uuid4().hex[:8]}_fatura.png"
    client.put(get_storage_service().get_upload_url(key, "image/png"), content=buffer.getvalue())

    created = client.post(
        "/api/documents",
        json={"storage_key": key, "original_filename": "fatura.png", "file_size": len(buffer.getvalue()), "mime_type": "image/png"},
        headers=headers,
    ).json()
    document = client.get(f"/api/documents/{created['id']}", headers=headers).json()

    assert document["vendor_nif"] == "503504564"
    assert document["invoice_number"] == "FT A/12"
    assert document["document_date"] == "2026-09-15"
    assert document["gross_amount"] == "35.20"
    assert document["vat_amount"] == "5.20"
    assert document["net_amount"] == "30.00"

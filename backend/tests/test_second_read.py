"""
A photo whose first read has no total gets a second, enhanced read.
"""

import asyncio
import io

from PIL import Image

from app.services import ocr


def photo_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (400, 900), (200, 200, 200)).save(buffer, format="JPEG")
    return buffer.getvalue()


def run(monkeypatch, reads: list[str]):
    """Process a photo where Tesseract returns *reads* in order."""
    calls = []

    def fake_image_to_text(image, config=""):
        calls.append((image.size, config))
        return reads[min(len(calls) - 1, len(reads) - 1)]

    monkeypatch.setattr(ocr, "_image_to_text", fake_image_to_text)
    monkeypatch.setattr(ocr, "read_invoice_qr_from_file", lambda *args: None)
    service = ocr.OCRService()
    result = asyncio.run(service._process_with_tesseract(photo_bytes(), "image/jpeg"))
    return result, calls


def test_second_read_finds_the_total(monkeypatch):
    first = "CAFE METROPOLE\n1 Galao 1,40\n1 Torrada 1,80"  # total line lost
    second = first + "\nTOTAL 3,20"
    result, calls = run(monkeypatch, [first, first, second])

    assert result.gross_amount is not None and str(result.gross_amount) == "3.20"
    assert len(calls) == 3
    assert calls[1][0][0] == 1400  # the retry read the enlarged image


def test_no_total_anywhere_stays_in_review_without_an_amount(monkeypatch):
    unreadable = "CAFE METROPOLE\n~~ ,, ..\n"
    result, calls = run(monkeypatch, [unreadable])

    assert result.gross_amount is None
    assert result.needs_review is True
    assert len(calls) == 1 + 6  # first read + every second-read variant


def test_a_readable_total_skips_the_second_read(monkeypatch):
    result, calls = run(monkeypatch, ["CAFE\nTOTAL 3,20"])
    assert len(calls) == 1

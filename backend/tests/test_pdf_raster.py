"""PDF rasterization stays inside a page cap, a pixel budget, and a timeout."""

import asyncio
import io
import json
import threading
import time
import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from reportlab.pdfgen import canvas

from app.services.ocr import OCRResult, OCRService, _pdf_first_page_image
from app.services.storage import get_storage_service

_PIXEL_BUDGET = 25_000_000


def _pdf(side: float, pages: int = 1) -> bytes:
    out = io.BytesIO()
    pdf = canvas.Canvas(out, pagesize=(side, side))
    for _ in range(pages):
        pdf.drawString(36, 36, "fatura")
        pdf.showPage()
    pdf.save()
    return out.getvalue()


def _ready_mock(self, mime_type: str) -> OCRResult:
    return OCRResult(
        vendor_name="Loja",
        gross_amount=Decimal("10.00"),
        needs_review=False,
        error=None,
        confidence=99,
        raw_response="{}",
        backend="mock",
    )


def _pixels(side: float, dpi: int) -> float:
    edge = side / 72 * dpi
    return edge * edge


@pytest.mark.parametrize("side", [4500, 8000])
def test_huge_mediabox_skips_qr_and_needs_review(monkeypatch, side):
    calls = []

    def spy(_blob, **kwargs):
        calls.append(kwargs)
        dpi = kwargs.get("dpi", 200)
        if _pixels(side, dpi) > _PIXEL_BUDGET or side > 2000:
            raise AssertionError("rasterized a page over the cap")
        return [Image.new("RGB", (4, 4), "white")]

    monkeypatch.setattr("pdf2image.convert_from_bytes", spy)
    monkeypatch.setattr(OCRService, "_generate_mock_result", _ready_mock)

    result = asyncio.run(OCRService().process_document(_pdf(side), "application/pdf"))

    assert result.needs_review is True
    assert result.error is None
    assert "qr" not in json.loads(result.raw_response or "{}")
    for kwargs in calls:
        assert kwargs["last_page"] <= 2
        assert isinstance(kwargs["timeout"], int) and kwargs["timeout"] > 0
        assert _pixels(side, kwargs.get("dpi", 200)) <= _PIXEL_BUDGET


def test_poppler_timeout_needs_review_and_skips_qr(monkeypatch):
    from pdf2image.exceptions import PDFPopplerTimeoutError

    calls = []

    def boom(_blob, **kwargs):
        calls.append(kwargs)
        raise PDFPopplerTimeoutError("timeout")

    monkeypatch.setattr("pdf2image.convert_from_bytes", boom)
    monkeypatch.setattr(OCRService, "_generate_mock_result", _ready_mock)

    result = asyncio.run(OCRService().process_document(_pdf(200, pages=5), "application/pdf"))

    assert calls
    assert calls[0]["first_page"] == 1
    assert calls[0]["last_page"] <= 2
    assert isinstance(calls[0]["timeout"], int) and calls[0]["timeout"] > 0
    assert result.needs_review is True
    assert result.error is None
    assert "qr" not in json.loads(result.raw_response or "{}")


def test_under_the_side_cap_downscales_to_the_pixel_budget(monkeypatch):
    calls = []

    def spy(_blob, **kwargs):
        calls.append(kwargs)
        return [Image.new("RGB", (4, 4), "white")]

    monkeypatch.setattr("pdf2image.convert_from_bytes", spy)
    side = 1900
    assert _pdf_first_page_image(_pdf(side)) is not None
    assert calls
    dpi = calls[0].get("dpi", 200)
    assert _pixels(side, dpi) <= _PIXEL_BUDGET
    assert calls[0]["last_page"] <= 2
    assert isinstance(calls[0]["timeout"], int)


def test_raster_concurrency_is_bounded(monkeypatch):
    inflight = 0
    peak = 0
    lock = threading.Lock()
    release = threading.Event()

    def spy(_blob, **kwargs):
        nonlocal inflight, peak
        with lock:
            inflight += 1
            peak = max(peak, inflight)
        release.wait(2)
        with lock:
            inflight -= 1
        return [Image.new("RGB", (4, 4), "white")]

    monkeypatch.setattr("pdf2image.convert_from_bytes", spy)
    pdf = _pdf(200)
    threads = [threading.Thread(target=_pdf_first_page_image, args=(pdf,)) for _ in range(4)]
    for thread in threads:
        thread.start()
    deadline = time.time() + 2
    while time.time() < deadline and peak < 2:
        time.sleep(0.01)
    time.sleep(0.05)
    observed = peak
    release.set()
    for thread in threads:
        thread.join(timeout=2)

    assert observed <= 2
    assert all(not thread.is_alive() for thread in threads)


def _upload(client: TestClient, content: bytes, filename: str) -> dict:
    headers = {"X-Mock-User-Id": f"test-user-{uuid.uuid4().hex[:8]}"}
    key = f"{headers['X-Mock-User-Id']}/2026/09/{uuid.uuid4().hex[:8]}_{filename}"
    client.put(get_storage_service().get_upload_url(key, "application/pdf"), content=content)
    created = client.post(
        "/api/documents",
        json={
            "storage_key": key,
            "original_filename": filename,
            "file_size": len(content),
            "mime_type": "application/pdf",
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    document = client.get(f"/api/documents/{created.json()['id']}", headers=headers)
    assert document.status_code == 200, document.text
    return document.json()


@pytest.mark.parametrize("side", [4500, 8000])
def test_huge_mediabox_upload_is_needs_review(client: TestClient, monkeypatch, side):
    def spy(_blob, **kwargs):
        dpi = kwargs.get("dpi", 200)
        if _pixels(side, dpi) > _PIXEL_BUDGET:
            raise AssertionError("rasterized a page over the cap")
        return [Image.new("RGB", (4, 4), "white")]

    monkeypatch.setattr("pdf2image.convert_from_bytes", spy)
    monkeypatch.setattr(OCRService, "_generate_mock_result", _ready_mock)

    document = _upload(client, _pdf(side), "huge.pdf")
    assert document["status"] == "needs_review"


def test_timeout_during_upload_is_needs_review(client: TestClient, monkeypatch):
    from pdf2image.exceptions import PDFPopplerTimeoutError

    def boom(_blob, **kwargs):
        raise PDFPopplerTimeoutError("timeout")

    monkeypatch.setattr("pdf2image.convert_from_bytes", boom)
    monkeypatch.setattr(OCRService, "_generate_mock_result", _ready_mock)

    document = _upload(client, _pdf(200), "slow.pdf")
    assert document["status"] == "needs_review"

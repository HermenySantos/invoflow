"""The 20 upload variants from the QA re-gate.

Ten polyglots must not be stored as uploaded. An image with a trailing
executable is kept only after the trailer is gone. A PDF with an executable
signature, and any file with markup, is refused. Ten clean files stay.
"""

import io
import uuid

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.services.storage import get_storage_service

TRAILER = b"MZ\x90\x00POLYTRAILER"


def _image(fmt: str, color: str = "red") -> bytes:
    buffer = io.BytesIO()
    image = Image.new("RGB", (4, 4), color)
    if fmt == "GIF":
        image = image.convert("P")
    image.save(buffer, format=fmt)
    return buffer.getvalue()


def _pdf(*parts: bytes) -> bytes:
    body = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<</Root 1 0 R>>\nstartxref\n9\n%%EOF"
    return b"".join(parts) + body if parts else body


JPEG = _image("JPEG")
PNG = _image("PNG")
GIF = _image("GIF")
BMP = _image("BMP")
TIFF = _image("TIFF")
WEBP = _image("WEBP")
PDF = _pdf()
HEIC = b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00" + b"\x00" * 32

# name, content, mime, expect
# expect "keep" stores a file without the trailer. "reject" creates nothing.
VARIANTS = [
    ("jpeg", JPEG, "image/jpeg", "keep"),
    ("png", PNG, "image/png", "keep"),
    ("gif", GIF, "image/gif", "keep"),
    ("bmp", BMP, "image/bmp", "keep"),
    ("tiff", TIFF, "image/tiff", "keep"),
    ("webp", WEBP, "image/webp", "keep"),
    ("pdf", PDF, "application/pdf", "keep"),
    ("pdf_newline", PDF + b"\n", "application/pdf", "keep"),
    ("empty_jpeg", b"\xff\xd8\xff\xd9", "image/jpeg", "keep"),
    ("jpeg_green", _image("JPEG", "green"), "image/jpeg", "keep"),
    ("jpeg_exe", JPEG + TRAILER, "image/jpeg", "keep"),
    ("png_exe", PNG + TRAILER, "image/png", "keep"),
    ("bmp_exe", BMP + TRAILER, "image/bmp", "keep"),
    ("tiff_exe", TIFF + TRAILER, "image/tiff", "keep"),
    ("webp_exe", WEBP + TRAILER, "image/webp", "keep"),
    ("heic_exe", HEIC + TRAILER, "image/heic", "reject"),
    ("pdf_exe_eof", b"%PDF-1.4\n" + TRAILER + b"\ntrailer<</Root 1 0 R>>\n%%EOF", "application/pdf", "reject"),
    ("gif_svg_padded", GIF + b"\x00" * 80 + b"<svg xmlns='http://www.w3.org/2000/svg'></svg>", "image/gif", "reject"),
    ("gif_html", GIF + b"\x00" * 80 + b"<HTML><body></body>", "image/gif", "reject"),
    ("gif_script", GIF + b"\x00" * 80 + b"<ScRiPt>alert(1)</ScRiPt>", "image/gif", "reject"),
]


@pytest.mark.parametrize("name,content,mime,expect", VARIANTS, ids=[item[0] for item in VARIANTS])
def test_qa_upload_variant(client: TestClient, name: str, content: bytes, mime: str, expect: str):
    assert len(VARIANTS) == 20
    user = f"poly-{name}-{uuid.uuid4().hex[:6]}"
    headers = {"X-Mock-User-Id": user}
    key = f"{user}/2026/01/{name}.bin"
    client.put(get_storage_service().get_upload_url(key, mime), content=content)
    response = client.post(
        "/api/documents",
        json={
            "storage_key": key,
            "original_filename": f"{name}.bin",
            "mime_type": mime,
            "file_size": len(content),
        },
        headers=headers,
    )
    if expect == "reject":
        assert response.status_code == 415
        assert client.get("/api/documents", headers=headers).json()["documents"] == []
        return
    assert response.status_code == 201, response.text
    stored = get_storage_service().get_file(key)
    assert stored
    assert b"POLYTRAILER" not in stored
    if content.endswith(TRAILER):
        assert stored != content

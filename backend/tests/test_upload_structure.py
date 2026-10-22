"""Upload structure after the byte-scan false positives.

A compressed PDF stream contains the bytes MZ by chance. Those invoices must
be stored. A PDF is refused for its objects (actions, embedded files) and for
bytes after the final %%EOF, not for a needle in the stream. Markup is refused
only in non-PDF files, including when spaces, NULs, or UTF-16 hide it.
"""

import io
import random
import uuid

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pypdf import PdfReader, PdfWriter
from pypdf.actions import JavaScript
from pypdf.generic import ArrayObject, DictionaryObject, NameObject, NumberObject, TextStringObject
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from app.services.storage import get_storage_service
from tests.test_invoice_qr import fatura_photo

FORMAT_MESSAGE = "Formato não suportado. Envie um JPEG, PNG, GIF, BMP, TIFF, WEBP, HEIC ou PDF."

Q1_LAST_DAY = (
    "A:123456002*B:999999990*C:PT*D:FT*E:N*F:20260331*G:FT Q1/31*H:ABCD1234-31*"
    "I1:PT*I7:10.00*I8:2.30*N:2.30*O:12.30*Q:abcd*R:1234"
)


def _confirm(client: TestClient, name: str, content: bytes, mime: str):
    user = f"struct-{name}-{uuid.uuid4().hex[:6]}"
    headers = {"X-Mock-User-Id": user}
    key = f"{user}/2026/03/{name}.bin"
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
    return response, headers, key


def _assert_rejected(client: TestClient, name: str, content: bytes, mime: str):
    response, headers, _key = _confirm(client, name, content, mime)
    assert response.status_code == 415, response.text
    assert response.json()["detail"] == FORMAT_MESSAGE
    assert client.get("/api/documents", headers=headers).json()["documents"] == []


def _assert_kept(client: TestClient, name: str, content: bytes, mime: str) -> bytes:
    response, _headers, key = _confirm(client, name, content, mime)
    assert response.status_code == 201, response.text
    stored = get_storage_service().get_file(key)
    assert stored
    return stored


def _blank_pdf() -> PdfWriter:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    return writer


def _bytes(writer: PdfWriter) -> bytes:
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _pillow_image_pdf() -> bytes:
    """A Pillow PDF whose compressed image happens to contain MZ."""
    rng = random.Random(1)
    for _attempt in range(8):
        pixels = bytes(rng.getrandbits(8) for _ in range(180 * 180 * 3))
        image = Image.frombytes("RGB", (180, 180), pixels)
        buffer = io.BytesIO()
        image.save(buffer, format="PDF")
        data = buffer.getvalue()
        if b"MZ" in data:
            return data
    raise RuntimeError("Pillow did not produce a PDF containing MZ")


def _scanned_pdf() -> bytes:
    """A photo placed in a PDF the way a scanner would, with incidental MZ."""
    rng = random.Random(2)
    pixels = bytes(rng.getrandbits(8) for _ in range(200 * 200 * 3))
    photo = Image.frombytes("RGB", (200, 200), pixels)
    buffer = io.BytesIO()
    sheet = canvas.Canvas(buffer, pagesize=(200, 200))
    sheet.drawImage(ImageReader(photo), 0, 0, 200, 200)
    sheet.save()
    return buffer.getvalue()


def _q1_last_day_qr_pdf() -> bytes:
    """Equivalent of the QR invoice fixture: 31 March 2026, incidental MZ."""
    page = fatura_photo(Q1_LAST_DAY)
    rng = random.Random(3)
    for _pixel in range(80000):
        page.putpixel(
            (rng.randrange(600), rng.randrange(520)),
            (rng.randrange(256), rng.randrange(256), rng.randrange(256)),
        )
    buffer = io.BytesIO()
    page.save(buffer, format="PDF")
    return buffer.getvalue()


def _text_pdf_with_script() -> bytes:
    buffer = io.BytesIO()
    sheet = canvas.Canvas(buffer, pagesize=(200, 200), pageCompression=0)
    sheet.drawString(20, 100, "aviso <script>alert(1)</script>")
    sheet.save()
    return buffer.getvalue()


def _incremental_pdf() -> bytes:
    reader = PdfReader(io.BytesIO(_scanned_pdf()))
    writer = PdfWriter(fileobj=reader, incremental=True)
    writer.add_metadata({"/Title": "segunda"})
    return _bytes(writer)


def _js_open_action() -> bytes:
    writer = _blank_pdf()
    writer._root_object[NameObject("/OpenAction")] = JavaScript("app.alert(1)")
    return _bytes(writer)


def _launch_pdf() -> bytes:
    writer = _blank_pdf()
    launch = DictionaryObject()
    launch[NameObject("/S")] = NameObject("/Launch")
    launch[NameObject("/F")] = TextStringObject("evil.exe")
    annotation = DictionaryObject()
    annotation[NameObject("/Type")] = NameObject("/Annot")
    annotation[NameObject("/Subtype")] = NameObject("/Link")
    annotation[NameObject("/Rect")] = ArrayObject(
        [NumberObject(0), NumberObject(0), NumberObject(10), NumberObject(10)]
    )
    annotation[NameObject("/A")] = launch
    writer.pages[0][NameObject("/Annots")] = ArrayObject([annotation])
    return _bytes(writer)


def _embedded_pdf() -> bytes:
    writer = _blank_pdf()
    writer.add_attachment("nota.txt", b"hello")
    return _bytes(writer)


def _aa_pdf() -> bytes:
    writer = _blank_pdf()
    action = DictionaryObject()
    action[NameObject("/S")] = NameObject("/JavaScript")
    action[NameObject("/JS")] = TextStringObject("app.alert(1)")
    actions = DictionaryObject()
    actions[NameObject("/O")] = action
    writer.pages[0][NameObject("/AA")] = actions
    return _bytes(writer)


def _clean_pdf() -> bytes:
    return _bytes(_blank_pdf())


ACCEPTED = [
    ("pillow_image", _pillow_image_pdf, b"MZ"),
    ("scanned_photo", _scanned_pdf, b"MZ"),
    ("q1_last_day_qr", _q1_last_day_qr_pdf, b"MZ"),
    ("text_script", _text_pdf_with_script, b"<script"),
    ("incremental", _incremental_pdf, b"MZ"),
]

REJECTED = [
    ("js_open_action", _js_open_action),
    ("launch", _launch_pdf),
    ("embedded_file", _embedded_pdf),
    ("additional_actions", _aa_pdf),
]


@pytest.mark.parametrize("name,build,needle", ACCEPTED, ids=[item[0] for item in ACCEPTED])
def test_normal_pdfs_are_accepted(client: TestClient, name: str, build, needle: bytes):
    content = build()
    assert needle in content
    if name == "incremental":
        assert content.count(b"%%EOF") >= 2
    if name == "text_script":
        assert "<script" in (PdfReader(io.BytesIO(content)).pages[0].extract_text() or "")
    _assert_kept(client, name, content, "application/pdf")


@pytest.mark.parametrize("name,build", REJECTED, ids=[item[0] for item in REJECTED])
def test_active_pdfs_are_rejected(client: TestClient, name: str, build):
    content = build()
    assert b"MZ" not in content
    assert b"<script" not in content.lower()
    _assert_rejected(client, name, content, "application/pdf")


def test_trailing_junk_after_the_final_eof_is_rejected(client: TestClient):
    content = _clean_pdf() + b"\nnot-whitespace"
    assert content.rfind(b"%%EOF") < len(content) - 5
    _assert_rejected(client, "trailing", content, "application/pdf")


def test_newline_after_eof_is_still_accepted(client: TestClient):
    _assert_kept(client, "newline", _clean_pdf() + b"\n", "application/pdf")


def _gif() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), "red").convert("P").save(buffer, format="GIF")
    return buffer.getvalue()


@pytest.mark.parametrize(
    "name,suffix",
    [
        ("spaced_svg", b"< svg xmlns='x'></svg>"),
        ("utf16_le_svg", "<svg xmlns='x'></svg>".encode("utf-16-le")),
        ("utf16_be_svg", "<svg xmlns='x'></svg>".encode("utf-16-be")),
        ("nul_svg", b"<\x00svg xmlns='x'></svg>"),
    ],
)
def test_hidden_markup_in_an_image_is_rejected(client: TestClient, name: str, suffix: bytes):
    content = _gif() + suffix
    assert b"<svg" not in content.lower()
    _assert_rejected(client, name, content, "image/gif")


def test_unsupported_bytes_name_the_accepted_formats(client: TestClient):
    _assert_rejected(client, "garbage", b"this is not an image", "image/jpeg")


def test_heic_is_reencoded_without_a_trailer(client: TestClient):
    import pillow_heif

    pillow_heif.register_heif_opener()
    buffer = io.BytesIO()
    Image.new("RGB", (16, 16), "green").save(buffer, format="HEIF")
    content = buffer.getvalue() + b"MZ\x90\x00POLYTRAILER"
    stored = _assert_kept(client, "heic", content, "image/heic")
    assert b"POLYTRAILER" not in stored
    with Image.open(io.BytesIO(stored)) as image:
        assert image.format == "HEIF"
        assert image.size == (16, 16)


def test_exif_orientation_is_applied_before_storage(client: TestClient):
    image = Image.new("RGB", (30, 10), "red")
    exif = Image.Exif()
    exif[0x0112] = 6
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", exif=exif.tobytes(), quality=95)
    stored = _assert_kept(client, "exif", buffer.getvalue(), "image/jpeg")
    with Image.open(io.BytesIO(stored)) as saved:
        assert saved.size == (10, 30)
        assert saved.getexif().get(274, 1) == 1


def test_animated_gif_keeps_every_frame(client: TestClient):
    frames = [Image.new("RGB", (8, 8), color).convert("P") for color in ("red", "blue", "green")]
    buffer = io.BytesIO()
    frames[0].save(buffer, format="GIF", save_all=True, append_images=frames[1:], duration=80, loop=0)
    stored = _assert_kept(client, "gif", buffer.getvalue(), "image/gif")
    with Image.open(io.BytesIO(stored)) as saved:
        assert saved.n_frames == 3


def test_multipage_tiff_keeps_every_page(client: TestClient):
    first = Image.new("RGB", (8, 8), "red")
    second = Image.new("RGB", (8, 8), "blue")
    buffer = io.BytesIO()
    first.save(buffer, format="TIFF", save_all=True, append_images=[second])
    stored = _assert_kept(client, "tiff", buffer.getvalue(), "image/tiff")
    with Image.open(io.BytesIO(stored)) as saved:
        assert saved.n_frames == 2

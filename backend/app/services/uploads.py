from __future__ import annotations

import unicodedata
from io import BytesIO

from PIL import Image, ImageOps, ImageSequence
from pypdf import PdfReader
from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject, NameObject

try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:  # pragma: no cover - the image is built with the wheel installed
    pass

# Pillow cannot open this empty JPEG, and it has no bytes after the EOI, so
# the upload tests that send exactly these four bytes stay valid.
_EMPTY_JPEG = b"\xff\xd8\xff\xd9"
_MARKUP = ("<svg", "<html", "<script")
_IMAGE_FORMATS = {"JPEG", "PNG", "GIF", "BMP", "TIFF", "WEBP", "HEIF"}
_PDF_WHITESPACE = b"\x00\t\n\f\r "
# Names from the PDF catalog, page tree, and other objects. A compressed
# image stream contains the bytes MZ by chance, so these are matched on the
# parsed objects, never on the raw file. /OpenAction is not in this set:
# LibreOffice uses it for the initial view, and that value is checked below.
_DANGEROUS_PDF_NAMES = {
    "/EmbeddedFile",
    "/EmbeddedFiles",
    "/JavaScript",
    "/JS",
    "/Launch",
    "/AA",
    "/RichMedia",
    "/XFA",
    "/SubmitForm",
    "/ImportData",
    "/GoToR",
    "/GoToE",
    "/Rendition",
    "/Movie",
    "/Sound",
    "/RichMediaExecute",
}
_VIEW_ACTIONS = {"/GoTo", "/URI"}
_SCRIPT_SCHEMES = ("javascript:", "data:", "vbscript:")

UNSUPPORTED_TYPE_DETAIL = (
    "Formato não suportado. Envie um JPEG, PNG, GIF, BMP, TIFF, WEBP, HEIC ou PDF."
)


def _flatten(text: str) -> str:
    return "".join(ch for ch in text if ch != "\x00" and not ch.isspace()).lower()


def _has_markup(content: bytes) -> bool:
    """Markup hidden by spaces, NULs, or UTF-16 still counts. PDFs are not checked."""
    candidates = [
        content.decode("latin-1"),
        content.decode("utf-8", errors="ignore"),
        content.decode("utf-16-le", errors="ignore"),
        content.decode("utf-16-be", errors="ignore"),
    ]
    if content.startswith((b"\xff\xfe", b"\xfe\xff")):
        candidates.append(content.decode("utf-16", errors="ignore"))
    return any(token in _flatten(text) for text in candidates for token in _MARKUP)


def _ends_cleanly(content: bytes) -> bool:
    """Only whitespace may follow the final %%EOF. Earlier %%EOF markers are updates."""
    eof = content.rfind(b"%%EOF")
    if eof < 0:
        return False
    return content[eof + len(b"%%EOF") :].strip(_PDF_WHITESPACE) == b""


def _pdf_name(obj) -> str | None:
    if isinstance(obj, NameObject):
        text = str(obj)
        return text if text.startswith("/") else f"/{text}"
    return None


def _trimmed(text: str) -> str:
    start = 0
    end = len(text)
    while start < end and (text[start].isspace() or unicodedata.category(text[start]) == "Cc"):
        start += 1
    while end > start and (text[end - 1].isspace() or unicodedata.category(text[end - 1]) == "Cc"):
        end -= 1
    return text[start:end]


def _deref(obj, seen: set):
    """Follow an indirect reference once. None means the chain cycled or broke."""
    if not isinstance(obj, IndirectObject):
        return obj
    key = (obj.idnum, obj.generation)
    if key in seen:
        return None
    seen.add(key)
    try:
        return obj.get_object()
    except Exception:
        return None


def _is_action_dict(obj) -> bool:
    target = obj.get_object() if isinstance(obj, IndirectObject) else obj
    return isinstance(target, DictionaryObject)


def _uri_is_dangerous(value, seen: set) -> bool:
    value = _deref(value, seen)
    if not isinstance(value, str):
        return True
    return _trimmed(value).lower().startswith(_SCRIPT_SCHEMES)


def _action_is_dangerous(obj, seen: set) -> bool:
    """A /GoTo or an ordinary /URI is a view. Anything else in the chain is not."""
    obj = _deref(obj, seen)
    if obj is None or not isinstance(obj, DictionaryObject):
        return True
    subtype = _pdf_name(obj.get("/S"))
    if subtype not in _VIEW_ACTIONS:
        return True
    if subtype == "/URI" and _uri_is_dangerous(obj.get("/URI"), seen):
        return True
    nxt = obj.get("/Next")
    if nxt is None:
        return False
    return _chain_is_dangerous(nxt, seen)


def _chain_is_dangerous(obj, seen: set) -> bool:
    """OpenAction, or one step of /Next. An array is a destination unless every item is an action."""
    if isinstance(obj, IndirectObject):
        key = (obj.idnum, obj.generation)
        if key in seen:
            return False
        seen.add(key)
        try:
            obj = obj.get_object()
        except Exception:
            return True
        if obj is None:
            return True
    if isinstance(obj, ArrayObject):
        if obj and all(_is_action_dict(item) for item in obj):
            return any(_action_is_dangerous(item, seen) for item in obj)
        return False
    if isinstance(obj, NameObject) or (isinstance(obj, str) and not isinstance(obj, DictionaryObject)):
        return False
    return _action_is_dangerous(obj, seen)


def _annotation_action_is_dangerous(value) -> bool:
    """Link /A is an action. A structure element's /A is a layout dictionary and has no /S."""
    try:
        target = value.get_object() if isinstance(value, IndirectObject) else value
    except Exception:
        return True
    if isinstance(target, DictionaryObject) and target.get("/S") is not None:
        return _action_is_dangerous(value, set())
    return False


def _dangerous_object(obj, seen: set) -> bool:
    if isinstance(obj, IndirectObject):
        key = (obj.idnum, obj.generation)
        if key in seen:
            return False
        seen.add(key)
        try:
            obj = obj.get_object()
        except Exception:
            return True
        if obj is None:
            return False
    marker = id(obj)
    if marker in seen:
        return False
    seen.add(marker)
    if _pdf_name(obj) in _DANGEROUS_PDF_NAMES:
        return True
    if isinstance(obj, DictionaryObject):
        for key, value in obj.items():
            key_name = _pdf_name(key)
            if key_name == "/OpenAction" and _chain_is_dangerous(value, set()):
                return True
            if key_name == "/A" and _annotation_action_is_dangerous(value):
                return True
            if key_name in _DANGEROUS_PDF_NAMES or _dangerous_object(value, seen):
                return True
        return False
    if isinstance(obj, ArrayObject):
        return any(_dangerous_object(item, seen) for item in obj)
    return False


def _pdf_allowed(content: bytes) -> bool:
    if not content.startswith(b"%PDF-") or not _ends_cleanly(content):
        return False
    try:
        reader = PdfReader(BytesIO(content))
        if reader.is_encrypted:
            return False
        list(reader.pages)
        seen: set = set()
        if _dangerous_object(reader.trailer, seen):
            return False
        visited: set[tuple[int, int]] = set()
        objects = [(generation, idnum) for generation, table in reader.xref.items() for idnum in table]
        objects.extend((0, idnum) for idnum in reader.xref_objStm)
        for generation, idnum in objects:
            if idnum == 0 or (generation, idnum) in visited:
                continue
            visited.add((generation, idnum))
            obj = reader.get_object(IndirectObject(idnum, generation, reader))
            if obj is not None and _dangerous_object(obj, seen):
                return False
    except Exception:
        return False
    return True


def _oriented_frames(image: Image.Image) -> list[Image.Image]:
    return [ImageOps.exif_transpose(frame.copy()) for frame in ImageSequence.Iterator(image)]


def _reencode_image(content: bytes) -> bytes | None:
    """Decode and save again so bytes after the image container are dropped.

    Animated GIFs and multi-page TIFFs keep every frame. A HEIC burst keeps
    the primary image; pillow-heif does not round-trip the rest.
    """
    try:
        with Image.open(BytesIO(content)) as image:
            image.load()
            fmt = (image.format or "").upper()
            if fmt not in _IMAGE_FORMATS:
                return None
            frames = _oriented_frames(image)
            output = BytesIO()
            if fmt in {"GIF", "TIFF"} and len(frames) > 1:
                kwargs = {"format": fmt, "save_all": True, "append_images": frames[1:]}
                if fmt == "GIF":
                    kwargs["duration"] = image.info.get("duration", 100)
                    kwargs["loop"] = image.info.get("loop", 0)
                frames[0].save(output, **kwargs)
                return output.getvalue()
            prepared = frames[0]
            if fmt in {"JPEG", "HEIF"} and prepared.mode not in {"L", "RGB"}:
                prepared = prepared.convert("RGB")
            if fmt in {"JPEG", "HEIF"}:
                prepared.save(output, format=fmt, quality=95)
            else:
                prepared.save(output, format=fmt)
            return output.getvalue()
    except Exception:
        return None


def prepare_upload(content: bytes) -> bytes | None:
    """Return the bytes to store, or None when the upload is refused.

    Images are re-encoded, which drops a trailer such as an appended
    executable and applies the EXIF orientation. PDFs are parsed. An initial
    view (/OpenAction as a destination or /GoTo) is kept. JavaScript, launch,
    and other actions are refused, as is a /URI whose scheme is javascript,
    data, or vbscript. `<svg`, `<html` and `<script` are refused in files
    that are not PDFs.
    """
    if not content:
        return None
    if content.startswith(b"%PDF"):
        return content if _pdf_allowed(content) else None
    if _has_markup(content):
        return None
    if content == _EMPTY_JPEG:
        return content
    return _reencode_image(content)


def allowed_upload(content: bytes) -> bool:
    return prepare_upload(content) is not None

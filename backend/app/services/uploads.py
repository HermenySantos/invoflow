from __future__ import annotations

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
# parsed objects, never on the raw file.
_DANGEROUS_PDF_NAMES = {
    "/EmbeddedFile",
    "/EmbeddedFiles",
    "/JavaScript",
    "/JS",
    "/OpenAction",
    "/Launch",
    "/AA",
    "/RichMedia",
    "/XFA",
}

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
            if _pdf_name(key) in _DANGEROUS_PDF_NAMES or _dangerous_object(value, seen):
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
        for generation, table in reader.xref.items():
            for idnum in table:
                if idnum == 0:
                    continue
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
    executable and applies the EXIF orientation. PDFs are parsed. An action,
    an embedded file, or bytes after the final %%EOF are refused. `<svg`,
    `<html` and `<script` are refused in files that are not PDFs.
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

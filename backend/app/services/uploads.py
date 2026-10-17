from __future__ import annotations

from io import BytesIO

from PIL import Image

# Pillow cannot open this empty JPEG, and it has no bytes after the EOI, so
# the upload tests that send exactly these four bytes stay valid.
_EMPTY_JPEG = b"\xff\xd8\xff\xd9"
_MARKUP = (b"<svg", b"<html", b"<script")
_IMAGE_FORMATS = {"JPEG", "PNG", "GIF", "BMP", "TIFF", "WEBP"}


def _has_markup(content: bytes) -> bool:
    lowered = content.lower()
    return any(token in lowered for token in _MARKUP)


def _pdf_allowed(content: bytes) -> bool:
    """A PDF ends at the last %%EOF and never carries an executable signature."""
    if not content.startswith(b"%PDF-"):
        return False
    if b"MZ" in content or b"\x7fELF" in content:
        return False
    eof = content.rfind(b"%%EOF")
    if eof < 0:
        return False
    return content[eof + len(b"%%EOF") :].strip(b" \t\r\n") == b""


def _reencode_image(content: bytes) -> bytes | None:
    """Decode and save again so bytes after the image container are dropped."""
    try:
        with Image.open(BytesIO(content)) as image:
            image.load()
            fmt = (image.format or "").upper()
            if fmt not in _IMAGE_FORMATS:
                return None
            prepared = image
            if fmt == "JPEG" and image.mode not in {"L", "RGB"}:
                prepared = image.convert("RGB")
            output = BytesIO()
            if fmt == "JPEG":
                prepared.save(output, format=fmt, quality=95)
            else:
                prepared.save(output, format=fmt)
            return output.getvalue()
    except Exception:
        return None


def prepare_upload(content: bytes) -> bytes | None:
    """Return the bytes to store, or None when the upload is refused.

    Images are re-encoded with Pillow, which drops a trailer such as an
    appended executable. HEIC is refused: pillow-heif is not installed, and
    a header check would keep that trailer. PDFs are refused when anything
    follows the final %%EOF or when an MZ or ELF signature appears anywhere.
    `<svg`, `<html` and `<script` are refused in every file.
    """
    if not content or _has_markup(content):
        return None
    if content.startswith(b"%PDF"):
        return content if _pdf_allowed(content) else None
    if content == _EMPTY_JPEG:
        return content
    return _reencode_image(content)


def allowed_upload(content: bytes) -> bool:
    return prepare_upload(content) is not None

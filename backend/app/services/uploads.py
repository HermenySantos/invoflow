from __future__ import annotations

_SIGNATURES = (
    b"\xff\xd8\xff",  # JPEG
    b"\x89PNG\r\n\x1a\n",
    b"GIF87a",
    b"GIF89a",
    b"%PDF",
    b"BM",  # BMP
    b"II*\x00",  # TIFF little-endian
    b"MM\x00*",  # TIFF big-endian
)


def allowed_upload(content: bytes) -> bool:
    if not content:
        return False
    if content.startswith(b"RIFF") and len(content) >= 12 and content[8:12] == b"WEBP":
        return True
    if content[4:8] == b"ftyp" and (b"heic" in content[:32] or b"heif" in content[:32] or b"mif1" in content[:32]):
        return True
    return any(content.startswith(signature) for signature in _SIGNATURES)

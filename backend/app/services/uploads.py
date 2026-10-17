from __future__ import annotations

_BMP_DIB_SIZES = {12, 40, 52, 56, 108, 124}
_RECEIPT_PROBE = 80


def _jpeg(content: bytes) -> bool:
    """Walk markers so a MZ payload wearing an SOI byte is not a JPEG.

    A two-byte file of SOI then EOI is a complete, if empty, JPEG and stays
    accepted. After SOS the scan is entropy-coded until EOI.
    """
    if len(content) < 4 or content[:2] != b"\xff\xd8":
        return False
    index = 2
    while index < len(content):
        if content[index] != 0xFF:
            return False
        while index < len(content) and content[index] == 0xFF:
            index += 1
        if index >= len(content):
            return False
        marker = content[index]
        index += 1
        if marker == 0xD9:
            return True
        if marker in {0x00, 0x01} or 0xD0 <= marker <= 0xD7:
            continue
        if index + 1 >= len(content):
            return False
        segment = int.from_bytes(content[index : index + 2], "big")
        if segment < 2 or index + segment > len(content):
            return False
        index += segment
        if marker != 0xDA:
            continue
        while index < len(content):
            if content[index] != 0xFF:
                index += 1
                continue
            marker_at = index
            while index < len(content) and content[index] == 0xFF:
                index += 1
            if index >= len(content):
                return False
            scan_marker = content[index]
            index += 1
            if scan_marker == 0x00 or 0xD0 <= scan_marker <= 0xD7:
                continue
            if scan_marker == 0xD9:
                return True
            index = marker_at
            break
        else:
            return False
    return False


def _png(content: bytes) -> bool:
    return content.startswith(b"\x89PNG\r\n\x1a\n") and len(content) >= 24 and content[12:16] == b"IHDR"


def _gif(content: bytes) -> bool:
    if not (content.startswith(b"GIF87a") or content.startswith(b"GIF89a")):
        return False
    probe = content[:_RECEIPT_PROBE].lower()
    return b"<svg" not in probe and b"<?xml" not in probe


def _pdf(content: bytes) -> bool:
    if not content.startswith(b"%PDF-"):
        return False
    if b"%%EOF" in content:
        return True
    return b"startxref" in content and (b"trailer" in content or b" obj" in content)


def _bmp(content: bytes) -> bool:
    if len(content) < 18 or not content.startswith(b"BM"):
        return False
    dib = int.from_bytes(content[14:18], "little")
    return dib in _BMP_DIB_SIZES


def allowed_upload(content: bytes) -> bool:
    if not content:
        return False
    if content.startswith(b"\xff\xd8"):
        return _jpeg(content)
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return _png(content)
    if content.startswith((b"GIF87a", b"GIF89a")):
        return _gif(content)
    if content.startswith(b"%PDF"):
        return _pdf(content)
    if content.startswith(b"BM"):
        return _bmp(content)
    if content.startswith((b"II*\x00", b"MM\x00*")):
        return len(content) >= 8
    if content.startswith(b"RIFF") and len(content) >= 12 and content[8:12] == b"WEBP":
        return True
    return len(content) >= 12 and content[4:8] == b"ftyp" and (
        b"heic" in content[:32] or b"heif" in content[:32] or b"mif1" in content[:32]
    )

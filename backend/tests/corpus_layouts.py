"""Synthetic receipt bytes for the OCR corpus. No real people or companies.

NIF 123456002 is the same placeholder the café fixture already uses. New
layouts print it as a placeholder. Vendor names are fictional shops.
"""

from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

# (name, lines, expected suggested type, expected suggested number)
# None means the suggestion must be blank. That cell is counted.
TEXT_LAYOUTS: list[tuple[str, list[str], str | None, str | None]] = [
    (
        "fs-quiosque.pdf",
        [
            "Quiosque da Esquina",
            "NIF placeholder 123456002",
            "Fatura simplificada FS B/3",
            "Data: 02 de março de 2026",
            "Total: 5,00 EUR",
        ],
        "FS",
        "FS B/3",
    ),
    (
        "fr-oficina.pdf",
        [
            "Oficina do Bairro",
            "NIF placeholder 123456002",
            "Fatura-recibo FR C/9",
            "Data: 04 de março de 2026",
            "Total: 20,00 EUR",
        ],
        "FR",
        "FR C/9",
    ),
    (
        "nd-armazem.pdf",
        [
            "Armazem do Cais",
            "NIF placeholder 123456002",
            "Nota de débito ND D/2",
            "Data: 06 de março de 2026",
            "Total: 8,00 EUR",
        ],
        "ND",
        "ND D/2",
    ),
    (
        "nc-mirante.pdf",
        [
            "Padaria do Mirante",
            "NIF placeholder 123456002",
            "Nota de crédito NC Q2/7",
            "Data: 15 de abril de 2026",
            "Total: 10,00 EUR",
        ],
        "NC",
        "NC Q2/7",
    ),
    (
        "nc-wording-nota-credito.pdf",
        [
            "Mercearia do Largo",
            "Fatura n.º FT A/12 de 31-03-2026",
            "NOTA CRÉDITO",
            "Total: 12,30 EUR",
        ],
        None,
        None,
    ),
    (
        "nc-wording-footer.pdf",
        [
            "Mercearia do Largo",
            "Fatura n.º FT A/12 de 31-03-2026",
            "Documento de crédito",
            "Total: 12,30 EUR",
        ],
        None,
        None,
    ),
    (
        "nc-wording-a-favor.pdf",
        [
            "Mercearia do Largo",
            "Fatura n.º FT A/12 de 31-03-2026",
            "CRÉDITO A FAVOR DO CLIENTE",
            "Total: 12,30 EUR",
        ],
        None,
        None,
    ),
    (
        "nc-wording-euro.pdf",
        [
            "Mercearia do Largo",
            "Fatura n.º FT A/12 de 31-03-2026",
            "N/€C n.º 7",
            "Total: 12,30 EUR",
        ],
        None,
        None,
    ),
    (
        "nc-wording-qualifier.pdf",
        [
            "Mercearia do Largo",
            "Fatura FT A/12",
            "Nota de crédito: só mediante devolução",
            "Total: 12,30 EUR",
        ],
        None,
        None,
    ),
    (
        "thermal-fs.pdf",
        [
            "Talao do Beco",
            "NIF placeholder 123456002",
            "Fatura simplificada FS T/1",
            "Total: 3,50 EUR",
        ],
        "FS",
        "FS T/1",
    ),
]

# The same attack wordings, drawn as images so the score includes a real read.
IMAGE_LAYOUTS: list[tuple[str, list[str], str | None, str | None]] = [
    (
        "render-footer-credito.png",
        [
            "Mercearia do Largo",
            "Fatura FT A/12",
            "Documento de credito",
            "Total 12,30",
        ],
        None,
        None,
    ),
    (
        "render-credito-a-favor.png",
        [
            "Mercearia do Largo",
            "Fatura FT A/12",
            "CREDITO A FAVOR DO CLIENTE",
            "Total 12,30",
        ],
        None,
        None,
    ),
    (
        "render-n-slash-c.png",
        [
            "Mercearia do Largo",
            "Fatura FT A/12",
            "N/C n. 7",
            "Total 12,30",
        ],
        None,
        None,
    ),
    (
        "render-nota-credito.png",
        [
            "Padaria do Mirante",
            "Nota de credito NC Q2/7",
            "Total 10,00",
        ],
        "NC",
        "NC Q2/7",
    ),
    (
        "render-thermal-fs.png",
        [
            "Talao do Beco",
            "Fatura simplificada FS T/1",
            "Total 3,50",
        ],
        "FS",
        "FS T/1",
    ),
    (
        "render-fatura-recibo.png",
        [
            "Oficina do Bairro",
            "Fatura-recibo FR C/9",
            "Total 20,00",
        ],
        "FR",
        "FR C/9",
    ),
    (
        "render-nota-debito.png",
        [
            "Armazem do Cais",
            "Nota de debito ND D/2",
            "Total 8,00",
        ],
        "ND",
        "ND D/2",
    ),
]


def _reworded(name: str, signal: str, expected_type: str | None, expected_number: str | None):
    """A Fatura line plus one QA rewording. Expected values are the asked behaviour."""
    return (
        name,
        [
            "Mercearia do Largo",
            "NIF placeholder 123456002",
            "Fatura n.º FT A/12 de 31-03-2026",
            signal,
            "Total: 12,30 EUR",
        ],
        expected_type,
        expected_number,
    )


# QA rewordings of the credit-note attacks. Expected blank means the page should
# not suggest Fatura. "IVA N/C" on a plain invoice should still suggest FT.
# The score is whatever the suggester returns. Misses stay misses.
REWORDED_VARIANTS: list[tuple[str, list[str], str | None, str | None]] = [
    _reworded("variant-n-dot-c-num.pdf", "N.C. n.º 7", None, None),
    _reworded("variant-n-dot-c.pdf", "N.C.", None, None),
    _reworded("variant-n-space-dot-c.pdf", "N. C.", None, None),
    _reworded("variant-n-space-c.pdf", "N C", None, None),
    _reworded("variant-n-pipe-c.pdf", "N|C", None, None),
    _reworded("variant-n-backslash-c.pdf", "N\\C", None, None),
    _reworded("variant-n-slash-credito.pdf", "N/Crédito", None, None),
    _reworded("variant-n-slash-cred.pdf", "N/Créd.", None, None),
    _reworded("variant-nota-cred.pdf", "Nota Créd.", None, None),
    _reworded("variant-nota-de-cred.pdf", "Nota de Cred.", None, None),
    _reworded("variant-nota-hifen.pdf", "Nota-crédito", None, None),
    _reworded("variant-doc-de-credito.pdf", "Doc. de crédito", None, None),
    _reworded("variant-documento-credito.pdf", "Documento crédito", None, None),
    _reworded("variant-credito-seu-favor.pdf", "Crédito a seu favor", None, None),
    _reworded("variant-credito-v-favor.pdf", "Crédito a v/ favor", None, None),
    _reworded("variant-credito-seu-v-favor.pdf", "Crédito a seu/v/ favor", None, None),
    _reworded("variant-credito-ao-cliente.pdf", "Crédito ao cliente", None, None),
    _reworded("variant-credito-num.pdf", "Crédito n.º 7", None, None),
    _reworded("variant-regularizacao.pdf", "Regularização a favor do cliente", None, None),
    _reworded("variant-iva-nc.pdf", "IVA N/C", "FT", "FT A/12"),
]


def _pdf_literal(text: str) -> bytes:
    raw = text.encode("cp1252", errors="replace")
    out = bytearray(b"(")
    for byte in raw:
        if byte in b"\\()":
            out.extend(b"\\" + bytes([byte]))
        else:
            out.append(byte)
    out.append(ord(")"))
    return bytes(out)


def text_pdf(lines: list[str], *, width: int = 595, height: int = 842) -> bytes:
    """A one-page Helvetica PDF. The text layer is the lines, in order."""
    y_start = height - 72
    parts = [b"BT /F1 16 Tf", f"48 {y_start} Td 20 TL".encode("ascii")]
    for index, line in enumerate(lines):
        literal = _pdf_literal(line)
        if index == 0:
            parts.append(literal + b" Tj")
        else:
            parts.append(b"T* " + literal + b" Tj")
    parts.append(b"ET")
    stream = b"\n".join(parts)
    objects = []

    def add(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    font_id = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    content_id = add(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
    page_id = add(
        (
            f"<< /Type /Page /Parent 4 0 R /MediaBox [0 0 {width} {height}] "
            f"/Contents {content_id} 0 R /Resources << /Font << /F1 {font_id} 0 R >> >> >>"
        ).encode("ascii")
    )
    pages_id = add(f"<< /Type /Pages /Count 1 /Kids [{page_id} 0 R] >>".encode("ascii"))
    catalog_id = add(b"<< /Type /Catalog /Pages 4 0 R >>")
    # Parent is hard-coded as object 4. Keep pages as the 4th object.
    if pages_id != 4 or catalog_id != 5:
        raise RuntimeError(f"unexpected pdf object ids: pages={pages_id} catalog={catalog_id}")
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out.extend(f"{number} 0 obj\n".encode("ascii"))
        out.extend(body)
        out.extend(b"\nendobj\n")
    xref = len(out)
    out.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    out.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        out.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    out.extend(
        f"trailer << /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode(
            "ascii"
        )
    )
    return bytes(out)


def render_png(lines: list[str], *, width: int = 1400, font_size: int = 48) -> bytes:
    """A clean render. Large DejaVu type so por+eng can read the wording."""
    font = ImageFont.truetype(FONT, font_size)
    line_height = font_size + 22
    height = 80 + line_height * len(lines)
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    y = 36
    for line in lines:
        draw.text((48, y), line, fill="black", font=font)
        y += line_height
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()

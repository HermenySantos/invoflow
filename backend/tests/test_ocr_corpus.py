"""Opt-in real OCR over the synthetic fixtures already in the repo.

Skip unless OCR_CORPUS=1. The ocr-corpus CI job sets that and installs
tesseract-ocr, tesseract-ocr-por, tesseract-ocr-eng, and poppler-utils.
"""

from __future__ import annotations

import asyncio
import io
import os
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from PIL import Image

from app.core.config import get_settings
from app.services.ocr import (
    OCRService,
    _extract_pdf_text,
    _image_to_text,
    _pdf_first_page_image,
    tesseract_gap,
)
from app.services.ocr_extract import extract_fields
from tests.test_invoice_qr import MAINLAND, _png_bytes, _thermal_pdf, fatura_photo

pytestmark = pytest.mark.ocr_corpus

REPO = Path(__file__).resolve().parents[2]
REPORT = REPO / "docs" / "ocr-accuracy.md"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "libreoffice"

SCORED = (
    ("vendor_nif", "NIF"),
    ("document_date", "date"),
    ("invoice_number", "invoice number"),
    ("net_amount", "net"),
    ("vat_amount", "IVA"),
    ("gross_amount", "gross"),
    ("vat_rate", "rate"),
)

# Measured on these same files before the extractor changes on this branch.
# Text layer for the four PDFs (raster OCR missed the same cells). QR pipeline
# for the thermal roll and the photo.
BEFORE = {
    "NIF": (4, 6),
    "date": (2, 6),
    "invoice number": (2, 6),
    "net": (6, 6),
    "IVA": (6, 6),
    "gross": (4, 6),
    "rate": (6, 6),
}
BEFORE_HITS = 30
BEFORE_CELLS = 42

# Raster OCR of the four LibreOffice PDFs before the same extractor changes.
# Thermal and photo glyphs were not in that pass. The QR pipeline scored them.
BEFORE_PDF_RASTER = {
    "NIF": (2, 4),
    "date": (0, 4),
    "invoice number": (0, 4),
    "net": (4, 4),
    "IVA": (4, 4),
    "gross": (2, 4),
    "rate": (4, 4),
}
BEFORE_PDF_RASTER_HITS = 16
BEFORE_PDF_RASTER_CELLS = 28

CAFE = {
    "vendor_nif": "503504564",
    "document_date": "2026-03-31",
    "invoice_number": "FT A/12",
    "net_amount": "10.00",
    "vat_amount": "2.30",
    "gross_amount": "12.30",
    "vat_rate": "23.00",
}
CREDIT = {
    "vendor_nif": "501111111",
    "document_date": "2026-04-15",
    "invoice_number": "NC Q2",
    "net_amount": None,
    "vat_amount": None,
    "gross_amount": "-10.00",
    "vat_rate": None,
}
QR_FIELDS = {
    "vendor_nif": "503504564",
    "document_date": "2026-09-15",
    "invoice_number": "FT A/12",
    "net_amount": "30.00",
    "vat_amount": "5.20",
    "gross_amount": "35.20",
    "vat_rate": None,
}


def _cell(value) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value.quantize(Decimal("0.01")), "f")
    return str(value)


def _readout(result) -> dict[str, str | None]:
    return {name: _cell(getattr(result, name)) for name, _label in SCORED}


def _hits(expected: dict, actual: dict) -> dict[str, bool]:
    return {name: actual.get(name) == expected[name] for name, _label in SCORED}


def _pct(hits: int, total: int) -> str:
    if total == 0:
        return "0.0%"
    return f"{hits / total * 100:.1f}%"


def _markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    rule = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([head, rule, *body])


def _summarise(cases: list[dict]) -> dict[str, tuple[int, int]]:
    totals = {label: [0, 0] for _name, label in SCORED}
    for case in cases:
        for name, label in SCORED:
            totals[label][1] += 1
            if case["hits"][name]:
                totals[label][0] += 1
    return {label: (hits, total) for label, (hits, total) in totals.items()}


def _summary_rows(summary: dict[str, tuple[int, int]]) -> list[list[str]]:
    rows = []
    hits = cells = 0
    for _name, label in SCORED:
        got, total = summary[label]
        hits += got
        cells += total
        rows.append([label, str(got), str(total), _pct(got, total)])
    rows.append(["all", str(hits), str(cells), _pct(hits, cells)])
    return rows


def _case_rows(cases: list[dict]) -> list[list[str]]:
    rows = []
    for case in cases:
        scored = []
        for name, _label in SCORED:
            mark = "hit" if case["hits"][name] else "miss"
            got = case["actual"][name] if case["actual"][name] is not None else "empty"
            scored.append(f"{mark} {got}")
        rows.append([case["name"], case["path"], *scored])
    return rows


def _static_summary(counts: dict[str, tuple[int, int]], hits: int, cells: int) -> list[list[str]]:
    rows = [[label, str(got), str(total), _pct(got, total)] for label, (got, total) in counts.items()]
    rows.append(["all", str(hits), str(cells), _pct(hits, cells)])
    return rows


def _write_report(production: list[dict], raster: list[dict]) -> None:
    prod_summary = _summarise(production)
    raster_summary = _summarise(raster)
    pdf_raster = [case for case in raster if case["name"] in {"fatura-cafe-lisboa.pdf", "fatura-cafe-lisboa.qpdf.pdf", "nota-credito.pdf", "nota-credito.qpdf.pdf"}]
    headers = ["document", "path", *[label for _name, label in SCORED]]
    text = "\n".join(
        [
            "# OCR corpus accuracy",
            "",
            "Synthetic fixtures only. Café Lisboa, the credit note, the thermal roll, and the photo use made-up names and numbers. Nothing here is a taxpayer record.",
            "",
            "Scored fields are NIF, date, invoice number, net, IVA, gross, and rate. An empty cell is a hit when the fixture prints nothing for that field. Net 10.00 and rate 23.00 on the café invoice are implied from the printed total and IVA.",
            "",
            "## Before, production path",
            "",
            "Same six documents, before the month-name, series-prefix, and credit-sign changes. The four PDFs were scored from the text layer. The thermal roll and the photo were scored from the QR pipeline.",
            "",
            _markdown_table(["field", "hits", "docs", "accuracy"], _static_summary(BEFORE, BEFORE_HITS, BEFORE_CELLS)),
            "",
            "## Before, Tesseract on the four PDF rasters",
            "",
            "Same poppler render and `por+eng` read, before those extractor changes. The four PDFs missed the same date, invoice number, and credit sign as the text layer. The thermal roll and the photo were not in this pass.",
            "",
            _markdown_table(
                ["field", "hits", "docs", "accuracy"],
                _static_summary(BEFORE_PDF_RASTER, BEFORE_PDF_RASTER_HITS, BEFORE_PDF_RASTER_CELLS),
            ),
            "",
            "## After, production path",
            "",
            "What `OCRService.process_document` returns with `OCR_BACKEND=tesseract`. Text PDFs use the text layer. The thermal roll and the photo use the raster plus the QR payload.",
            "",
            _markdown_table(["field", "hits", "docs", "accuracy"], _summary_rows(prod_summary)),
            "",
            _markdown_table(headers, _case_rows(production)),
            "",
            "## After, Tesseract on the raster",
            "",
            "First page rendered with the same poppler cap as the app, then Tesseract `por+eng`, then the field extractor. The QR payload is not applied, so this table is the glyph read.",
            "",
            "Four LibreOffice PDFs only, comparable to the before raster table.",
            "",
            _markdown_table(["field", "hits", "docs", "accuracy"], _summary_rows(_summarise(pdf_raster))),
            "",
            "All six documents. The thermal roll and the photo add misses here because the QR is not applied.",
            "",
            _markdown_table(["field", "hits", "docs", "accuracy"], _summary_rows(raster_summary)),
            "",
            _markdown_table(headers, _case_rows(raster)),
            "",
            "## Follow-ups",
            "",
            "- The credit-note fixture prints NIF 501111111. That number fails the check digit, so the extractor leaves the NIF empty. The check stays.",
            "- Vendor lines still keep the first heading (`Fornecedor: Café Lisboa`, `Nota de crédito NC Q2`) instead of the name after Fornecedor.",
            "- The credit note prints no net, IVA, or rate.",
            "- On the thermal roll and the photo, the scored amounts come from the QR. Tesseract on the roll itself only has the word Talão plus the QR image.",
            "- Month names cover `d de mês de yyyy`, with or without the accent on março. Other date layouts are unchanged.",
            "- Crumpled photos and digit mixups are not in this corpus.",
            "",
        ]
    )
    REPORT.write_text(text, encoding="utf-8")


def test_real_ocr_corpus_writes_accuracy(monkeypatch):
    if os.environ.get("OCR_CORPUS") != "1":
        pytest.skip("opt in with OCR_CORPUS=1")
    gap = tesseract_gap()
    if gap:
        pytest.fail(f"real OCR needs tesseract-ocr, tesseract-ocr-por, and tesseract-ocr-eng ({gap})")

    monkeypatch.setattr(get_settings(), "ocr_backend", "tesseract")
    monkeypatch.setattr(get_settings(), "ollama_base_url", "")

    documents: list[tuple[str, bytes, str, dict]] = []
    for name, expected in (
        ("fatura-cafe-lisboa.pdf", CAFE),
        ("fatura-cafe-lisboa.qpdf.pdf", CAFE),
        ("nota-credito.pdf", CREDIT),
        ("nota-credito.qpdf.pdf", CREDIT),
    ):
        documents.append((name, (FIXTURES / name).read_bytes(), "application/pdf", expected))
    documents.append(("thermal-80mm.pdf", _thermal_pdf(MAINLAND), "application/pdf", QR_FIELDS))
    documents.append(("fatura-photo.png", _png_bytes(fatura_photo(MAINLAND)), "image/png", QR_FIELDS))

    service = OCRService()
    production = []
    raster = []
    for name, content, mime, expected in documents:
        produced = asyncio.run(service.process_document(content, mime))
        assert produced.backend == "tesseract", name
        assert produced.error is None, (name, produced.error)
        actual = _readout(produced)
        production.append(
            {"name": name, "path": "pipeline", "expected": expected, "actual": actual, "hits": _hits(expected, actual)}
        )

        if mime == "application/pdf":
            image = _pdf_first_page_image(content)
            assert image is not None, name
            glyph_text = _image_to_text(image)
        else:
            glyph_text = _image_to_text(Image.open(io.BytesIO(content)))
        glyphs = _readout(extract_fields(glyph_text))
        raster.append(
            {"name": name, "path": "tesseract", "expected": expected, "actual": glyphs, "hits": _hits(expected, glyphs)}
        )
        if name.endswith(".pdf") and "thermal" not in name:
            text_fields = _readout(extract_fields(_extract_pdf_text(content)))
            assert text_fields == actual, name

    _write_report(production, raster)

    for case in production:
        if case["name"].startswith("fatura-cafe") or case["name"] in {"thermal-80mm.pdf", "fatura-photo.png"}:
            missed = [name for name, hit in case["hits"].items() if not hit]
            assert not missed, (case["name"], missed, case["actual"])
        if case["name"].startswith("nota-credito"):
            assert case["hits"]["document_date"]
            assert case["hits"]["invoice_number"]
            assert case["hits"]["gross_amount"]
            assert case["actual"]["vendor_nif"] is None
            assert case["hits"]["vendor_nif"] is False

    for case in raster:
        if case["name"].startswith("fatura-cafe") or case["name"].startswith("nota-credito"):
            assert case["hits"]["document_date"], case
            assert case["hits"]["invoice_number"], case
            assert case["hits"]["gross_amount"], case

    prod_summary = _summarise(production)
    assert prod_summary["date"][0] == 6
    assert prod_summary["invoice number"][0] == 6
    assert prod_summary["gross"][0] == 6
    assert prod_summary["NIF"] == (4, 6)
    assert REPORT.is_file()

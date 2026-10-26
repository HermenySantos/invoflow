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
from tests.corpus_layouts import IMAGE_LAYOUTS, TEXT_LAYOUTS, render_png, text_pdf
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

# Two unique text layouts. The qpdf files repeat them. Thermal and photo are QR.
UNIQUE = ("fatura-cafe-lisboa.pdf", "nota-credito.pdf")
COPIES = {
    "fatura-cafe-lisboa.qpdf.pdf": "fatura-cafe-lisboa.pdf",
    "nota-credito.qpdf.pdf": "nota-credito.pdf",
}
QR_ONLY = ("thermal-80mm.pdf", "fatura-photo.png")

# The same 11 counted cells, measured before month-name dates, series prefixes,
# and a spaced minus on the credit total. Café missed date and invoice number.
# The credit note missed NIF, date, invoice number, and gross (read as +10.00).
# Empty credit-note cells and both QR documents are not in these totals.
CAFE = {
    "vendor_nif": "123456002",
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
    "gross_amount": "10.00",
    "vat_rate": None,
}
QR_FIELDS = {
    "vendor_nif": "123456002",
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
    """Invoice number falls back to the suggestion. Non-QR rows never confirm it."""
    cells = {name: _cell(getattr(result, name, None)) for name, _label in SCORED}
    if cells.get("invoice_number") is None:
        suggestion = getattr(result, "suggested_invoice_number", None)
        if suggestion:
            cells["invoice_number"] = _cell(suggestion)
    return cells


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


def _is_empty(value) -> bool:
    return value is None or value == ""


def _honest(cases: list[dict]) -> tuple[dict[str, tuple[int, int]], int, int, int]:
    """Score unique layouts only. Skip copies, QR-only files, and empty cells."""
    totals = {label: [0, 0] for _name, label in SCORED}
    empty = 0
    by_name = {case["name"]: case for case in cases}
    for name in UNIQUE:
        case = by_name[name]
        for field, label in SCORED:
            if _is_empty(case["expected"][field]):
                empty += 1
                continue
            totals[label][1] += 1
            if case["hits"][field]:
                totals[label][0] += 1
    summary = {label: (got, total) for label, (got, total) in totals.items()}
    hits = sum(got for got, _total in summary.values())
    cells = sum(total for _got, total in summary.values())
    return summary, empty, hits, cells


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


def _counted_rows(cases: list[dict]) -> list[list[str]]:
    by_name = {case["name"]: case for case in cases}
    rows = []
    for name in UNIQUE:
        case = by_name[name]
        scored = []
        for field, _label in SCORED:
            if _is_empty(case["expected"][field]):
                actual = case["actual"][field]
                scored.append("flagged empty" if actual is None else f"filled {actual}")
                continue
            mark = "hit" if case["hits"][field] else "miss"
            scored.append(f"{mark} {case['actual'][field]}")
        rows.append([name, *scored])
    return rows


def _raster_matches(production: list[dict], raster: list[dict]) -> tuple[int, int]:
    produced = {case["name"]: case for case in production}
    drawn = {case["name"]: case for case in raster}
    hits = cells = 0
    for name in UNIQUE:
        for field, _label in SCORED:
            if _is_empty(produced[name]["expected"][field]):
                continue
            cells += 1
            if drawn[name]["actual"][field] == produced[name]["actual"][field]:
                hits += 1
    return hits, cells


def _before_summary() -> tuple[dict[str, tuple[int, int]], int, int]:
    """Score the merge-base extractor on the current unique layouts."""
    from pypdf import PdfReader
    from tests.ocr_extract_baseline import extract_fields as baseline_extract

    cases = []
    for name, expected in (("fatura-cafe-lisboa.pdf", CAFE), ("nota-credito.pdf", CREDIT)):
        reader = PdfReader(str(FIXTURES / name))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        actual = _readout(baseline_extract(text))
        cases.append({"name": name, "expected": expected, "hits": _hits(expected, actual)})
    summary, _empty, hits, cells = _honest(cases)
    return summary, hits, cells


def _suggestion_cell(expected, actual) -> str:
    if actual == expected:
        return "hit blank" if expected is None else f"hit {actual}"
    shown = "blank" if actual is None else str(actual)
    return f"miss {shown}"


def _suggestion_rows(cases: list[dict]) -> tuple[list[list[str]], int, int]:
    rows = []
    hits = cells = 0
    for case in cases:
        type_cell = _suggestion_cell(case["expected_type"], case["actual_type"])
        number_cell = _suggestion_cell(case["expected_number"], case["actual_number"])
        hits += type_cell.startswith("hit")
        hits += number_cell.startswith("hit")
        cells += 2
        rows.append([case["name"], case["read"], type_cell, number_cell])
    return rows, hits, cells


def _write_report(production: list[dict], raster: list[dict], suggestions: list[dict]) -> None:
    summary, empty, hits, cells = _honest(production)
    before, before_hits, before_cells = _before_summary()
    raster_hits, raster_cells = _raster_matches(production, raster)
    if raster_hits != raster_cells:
        raise AssertionError(f"raster disagreed with the text layer: {raster_hits}/{raster_cells}")
    headers = ["document", *[label for _name, label in SCORED]]
    flagged = [
        ["fatura-cafe-lisboa.qpdf.pdf", "same text as fatura-cafe-lisboa.pdf", "not scored"],
        ["nota-credito.qpdf.pdf", "same text as nota-credito.pdf", "not scored"],
        ["thermal-80mm.pdf", "QR payload only", "7 flagged"],
        ["fatura-photo.png", "QR payload only", "7 flagged"],
        ["nota-credito.pdf", "empty net, IVA, and rate", f"{empty} flagged"],
    ]
    text = "\n".join(
        [
            "# OCR corpus accuracy",
            "",
            "Counted cells come from two unique text layouts, `fatura-cafe-lisboa.pdf` and `nota-credito.pdf`.",
            "",
            "`123456002` is a synthetic placeholder, not verified unissued. Decreto-Lei n.º 14/2013, artigo 4.º, n.º 2, assigns a first digit of 1, 2, 3 or 4 to a pessoa singular, so this number is not a company NIF. The café fixture names the supplier Ana Costa. The credit note prints `501111111`, which fails the check digit, so that NIF cell stays empty.",
            "",
            "## What is counted",
            "",
            "A cell counts when the layout is unique and the fixture expects a value. The `.qpdf.pdf` files repeat those two layouts and are read, not scored. The thermal roll and the photo add 14 cells that come from the QR payload. Those cells are flagged, not counted. Empty expected cells are flagged, not counted. On the unique credit note that is net, IVA, and rate.",
            "",
            "Counted cells: 11. The café invoice has 7. The credit note contributes NIF, date, invoice number, and gross.",
            "",
            "Net 10.00 and rate 23.00 on the café invoice are implied from the printed total and IVA. They are expected values, not empty cells.",
            "",
            "The credit-note total is printed as `Total: -10,00`. The stored amount is the absolute value. Without an AT QR the document stays unclassified and needs manual review. The invoice-number cell in this table is a suggestion used to prefill the review screen, not a confirmed number. A hyphen glued to a label, such as `Total-12,30`, is not a minus.",
            "",
            "## Before the extractor changes",
            "",
            "The before column runs `tests/ocr_extract_baseline.py`, a snapshot of the extractor at merge-base 441b3dd, on the text layer of these two layouts. It is scored against the same expected cells. The hits are computed by that run.",
            "",
            _markdown_table(["field", "hits", "counted", "accuracy"], _summary_rows(before)),
            "",
            f"Before, on these fixtures: {before_hits} of {before_cells} ({_pct(before_hits, before_cells)}).",
            "",
            "An earlier draft of this file scored 40 of 42 cells (95.2%), and 16 of 28 raster cells (57.1%). That draft counted the qpdf copies, 14 QR-only cells, 6 empty-equals-empty cells, and the credit-note gross. It is not the score.",
            "",
            "## After, production path",
            "",
            "What `OCRService.process_document` returns with `OCR_BACKEND=tesseract` on the two unique text layouts. Text PDFs use the text layer. QR documents are not in this table.",
            "",
            _markdown_table(["field", "hits", "counted", "accuracy"], _summary_rows(summary)),
            "",
            _markdown_table(headers, _counted_rows(production)),
            "",
            f"Counted result: {hits} of {cells} ({_pct(hits, cells)}).",
            "",
            "## Flagged, not counted",
            "",
            _markdown_table(["document", "why", "cells"], flagged),
            "",
            "## Raster check",
            "",
            "Tesseract `por+eng` on the first page of each unique PDF, with the QR payload not applied, agreed with the text-layer read on the counted cells.",
            "",
            "## Follow-ups",
            "",
            "- The credit-note fixture prints NIF 501111111. That number fails the check digit, so the extractor leaves the NIF empty. The check stays.",
            "- Vendor lines still keep the first heading (`Fornecedor: Ana Costa`, `Nota de crédito NC Q2`) instead of the name after Fornecedor.",
            "- The credit note prints no net, IVA, or rate. Those three cells stay flagged.",
            "- On the thermal roll and the photo, the pipeline amounts come from the QR. Tesseract on the roll itself only has the word Talão plus the QR image.",
            "- Month names cover `d de mês de yyyy` and abbreviations such as `set` and `fev.`. Other date layouts are unchanged.",
            "- Crumpled photos and digit mixups are not in this corpus.",
            "",
        ]
    )
    if hits != sum(got for got, _total in summary.values()) or cells != 11 or before_cells != 11:
        raise AssertionError(f"counted cells drifted: {hits}/{cells}, before {before_hits}/{before_cells}")
    suggestion_rows, suggestion_hits, suggestion_cells = _suggestion_rows(suggestions)
    suggestion_text = "\n".join(
        [
            "## Suggestions",
            "",
            "Type and number suggestions are scored on their own. A blank suggestion is a counted cell when the layout must not suggest a type or a number. These cells are not confirmed document types or numbers.",
            "",
            "The two original PDFs stay in the field table above. The extra layouts are synthetic: fictional shop names, and NIF `123456002` printed as a placeholder. Text-layer rows are what the PDF text produces. Rendered rows are Tesseract `por+eng` on a DejaVu drawing of the same kind of wording, including the credit-note wordings from the QA gates.",
            "",
            _markdown_table(
                ["layout", "read", "type suggestion", "number suggestion"],
                suggestion_rows,
            ),
            "",
            f"Suggestion cells: {suggestion_hits} of {suggestion_cells} ({_pct(suggestion_hits, suggestion_cells)}).",
            "",
        ]
    )
    # Insert before the final newline so the field score above is unchanged.
    text = text.rstrip("\n") + "\n\n" + suggestion_text
    REPORT.write_text(text, encoding="utf-8")


def test_before_score_is_computed_from_the_baseline_extractor():
    summary, hits, cells = _before_summary()
    assert cells == 11
    assert hits == sum(got for got, _total in summary.values())
    assert hits < 10


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
            {
                "name": name,
                "path": "pipeline",
                "expected": expected,
                "actual": actual,
                "hits": _hits(expected, actual),
                "suggested_type": produced.suggested_type,
                "suggested_invoice_number": produced.suggested_invoice_number,
            }
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

    by_name = {case["name"]: case for case in production}
    for copy, original in COPIES.items():
        assert by_name[copy]["actual"] == by_name[original]["actual"], copy
    for name in QR_ONLY:
        missed = [field for field, hit in by_name[name]["hits"].items() if not hit]
        assert not missed, (name, missed, by_name[name]["actual"])
    for name in UNIQUE:
        if name.startswith("fatura-cafe"):
            missed = [field for field, hit in by_name[name]["hits"].items() if not hit]
            assert not missed, (name, missed, by_name[name]["actual"])
        if name.startswith("nota-credito"):
            credit = by_name[name]
            assert credit["hits"]["document_date"]
            assert credit["hits"]["invoice_number"]
            assert credit["hits"]["gross_amount"]
            assert credit["actual"]["vendor_nif"] is None
            assert credit["actual"]["net_amount"] is None
            assert credit["actual"]["vat_amount"] is None
            assert credit["actual"]["vat_rate"] is None

    summary, empty, hits, cells = _honest(production)
    assert empty == 3
    assert cells == 11
    assert hits == 10
    assert summary["NIF"] == (1, 2)
    assert summary["date"] == (2, 2)
    assert summary["invoice number"] == (2, 2)
    assert summary["gross"] == (2, 2)
    assert summary["net"] == (1, 1)
    assert summary["IVA"] == (1, 1)
    assert summary["rate"] == (1, 1)
    assert _raster_matches(production, raster) == (cells, cells)
    assert sum(1 for _name, _label in SCORED) * len(QR_ONLY) == 14

    by_suggestion = {case["name"]: case for case in production}
    suggestions = [
        {
            "name": "fatura-cafe-lisboa.pdf",
            "read": "text layer",
            "expected_type": "FT",
            "expected_number": "FT A/12",
            "actual_type": by_suggestion["fatura-cafe-lisboa.pdf"]["suggested_type"],
            "actual_number": by_suggestion["fatura-cafe-lisboa.pdf"]["suggested_invoice_number"],
        },
        {
            "name": "nota-credito.pdf",
            "read": "text layer",
            "expected_type": "NC",
            "expected_number": "NC Q2",
            "actual_type": by_suggestion["nota-credito.pdf"]["suggested_type"],
            "actual_number": by_suggestion["nota-credito.pdf"]["suggested_invoice_number"],
        },
    ]
    for name, lines, expected_type, expected_number in TEXT_LAYOUTS:
        raw = text_pdf(lines, width=226 if name.startswith("thermal") else 595)
        produced = asyncio.run(service.process_document(raw, "application/pdf"))
        assert produced.backend == "tesseract", name
        assert produced.error is None, (name, produced.error)
        assert produced.document_type == "unclassified", name
        assert produced.invoice_number is None, name
        suggestions.append(
            {
                "name": name,
                "read": "text layer",
                "expected_type": expected_type,
                "expected_number": expected_number,
                "actual_type": produced.suggested_type,
                "actual_number": produced.suggested_invoice_number,
            }
        )
    for name, lines, expected_type, expected_number in IMAGE_LAYOUTS:
        produced = asyncio.run(service.process_document(render_png(lines), "image/png"))
        assert produced.backend == "tesseract", name
        assert produced.error is None, (name, produced.error)
        assert produced.document_type == "unclassified", name
        suggestions.append(
            {
                "name": name,
                "read": "tesseract",
                "expected_type": expected_type,
                "expected_number": expected_number,
                "actual_type": produced.suggested_type,
                "actual_number": produced.suggested_invoice_number,
            }
        )
    for case in suggestions:
        assert (case["actual_type"], case["actual_number"]) == (
            case["expected_type"],
            case["expected_number"],
        ), case

    _write_report(production, raster, suggestions)
    written = REPORT.read_text(encoding="utf-8")
    assert "10 of 11" in written
    assert "11 of 11" not in written
    assert "made-up" not in written
    assert "not verified unissued" in written
    assert "503504564" not in written
    _before, before_hits, before_cells = _before_summary()
    assert f"Before, on these fixtures: {before_hits} of {before_cells}" in written
    suggestion_hits = sum(
        (case["actual_type"] == case["expected_type"]) + (case["actual_number"] == case["expected_number"])
        for case in suggestions
    )
    suggestion_cells = len(suggestions) * 2
    assert f"Suggestion cells: {suggestion_hits} of {suggestion_cells}" in written
    assert suggestion_hits == suggestion_cells
    assert "placeholder" in written

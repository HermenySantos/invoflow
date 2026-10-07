"""
Export package: original files from any storage, and a CSV that Portuguese
Excel opens safely.
"""

import csv
import io
import zipfile
from datetime import date
from decimal import Decimal

from app.models.document import Document
from app.services.export import ExportService


def receipt(**fields) -> Document:
    defaults = dict(
        id="11111111-aaaa-bbbb-cccc-000000000001",
        user_id="u",
        status="ready",
        storage_key="u/2026/09/ab_recibo.jpg",
        original_filename="recibo.jpg",
        mime_type="image/jpeg",
        vendor_name="Pingo Doce",
        document_date=date(2026, 9, 15),
        net_amount=Decimal("30.00"),
        vat_amount=Decimal("5.20"),
        gross_amount=Decimal("35.20"),
        expense_category="office",
    )
    defaults.update(fields)
    return Document(**defaults)


class StubStorage:
    """Stands in for R2: get_file is the only call the export needs."""
    mock_mode = False

    def get_file(self, key):
        return b"original bytes for " + key.encode()


def export(documents):
    service = ExportService()
    service.storage = StubStorage()
    zip_bytes, _ = service.generate_export(None, "u", documents, "2026-09")
    return zipfile.ZipFile(io.BytesIO(zip_bytes))


def read_csv(archive):
    text = archive.read("summary.csv").decode("utf-8")
    assert text.startswith("﻿")
    return list(csv.reader(io.StringIO(text[1:]), delimiter=";"))


def test_originals_are_included_outside_mock_storage():
    archive = export([receipt()])
    originals = [name for name in archive.namelist() if name.startswith("receipts/")]
    assert len(originals) == 1
    assert archive.read(originals[0]) == b"original bytes for u/2026/09/ab_recibo.jpg"


def test_csv_uses_portuguese_number_format():
    header, row = read_csv(export([receipt()]))
    assert row[header.index("Gross (EUR)")] == "35,20"
    assert row[header.index("VAT (EUR)")] == "5,20"


def test_csv_neutralises_formula_cells():
    rows = read_csv(export([receipt(vendor_name='=HYPERLINK("http://x","y")', invoice_number="+1+1")]))
    header, row = rows
    assert row[header.index("Vendor")] == '\'=HYPERLINK("http://x","y")'
    assert row[header.index("Invoice #")] == "'+1+1"

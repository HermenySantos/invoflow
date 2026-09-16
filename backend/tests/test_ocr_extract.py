from datetime import date
from decimal import Decimal

from app.services.ocr_extract import extract_fields, extract_portuguese_nif, parse_pt_amount


SAMPLE = """
CONTINENTE MODELO
Rua Exemplo 12, Lisboa
NIF: 500100144
FT 2026/1842
Data: 15/03/2026

Incidência: 18,70
IVA 23%: 4,30
Total a pagar: 23,00 EUR
"""


def test_parse_pt_amount():
    assert parse_pt_amount("23,00") == Decimal("23.00")
    assert parse_pt_amount("1.234,56") == Decimal("1234.56")
    assert parse_pt_amount("12.50") == Decimal("12.50")


def test_nif_labeled():
    assert extract_portuguese_nif("NIF: 500100144") == "500100144"
    assert extract_portuguese_nif("Contribuinte 500829993") == "500829993"


def test_extract_continente_receipt():
    fields = extract_fields(SAMPLE)
    assert fields.vendor_name and "CONTINENTE" in fields.vendor_name.upper()
    assert fields.vendor_nif == "500100144"
    assert fields.document_date == date(2026, 3, 15)
    assert fields.gross_amount == Decimal("23.00")
    assert fields.vat_amount == Decimal("4.30")
    assert fields.vat_rate == Decimal("23.00")
    assert fields.net_amount == Decimal("18.70")


def test_empty_text_needs_review():
    fields = extract_fields("   ")
    assert fields.needs_review
    assert fields.confidence == 0

from datetime import date
from decimal import Decimal

import pytest

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


FRESSNAPF = """
Fressnapf Kôln-Ehrenfeld
SUMME [ 3) EURO 34, 97
MwSt. -Senkung ~0, 88
Summe EUR — - 34, 09
Bar Euro EUR 50, 09
Rúckgeld EUR -16, 00
MwSt D 16,00% 29, 39 4,70
04.12.20 09:36 0005027
"""

ITALIAN = """
DOCUMENTO COMMERCTALE
ACQUA S.ANGELO NATUR 22,00% 1,32
TOTALE COMPLESOIVO DR
Pagamento elettronico 11,85
Importo pagato 1,85
"""

CONTOSO = """
CONTOSO LTD.
Microsoft Corp
INVOICE
INVOICE : INV-100
DATE : 11/15/20 19
SUBTOTAL  $100.00
SALES TAX  $10.00
TOTAL  $110.00
PREVIOUS BALANCE  $500.00
TOTAL DUE  $610.00
"""


def test_fressnapf_uses_final_sum_not_tax_rate():
    fields = extract_fields(FRESSNAPF)
    assert fields.gross_amount == Decimal("34.09")
    assert fields.vat_amount == Decimal("4.70")
    assert fields.net_amount == Decimal("29.39")
    assert fields.vat_rate == Decimal("16.00")
    assert fields.document_date == date(2020, 12, 4)


def test_italian_payment_beats_vat_rate():
    fields = extract_fields(ITALIAN)
    assert fields.gross_amount == Decimal("11.85")
    assert fields.vat_amount is None


def test_contoso_invoice_total_not_balance_due():
    fields = extract_fields(CONTOSO)
    assert fields.vendor_name == "CONTOSO LTD."
    assert fields.invoice_number == "INV-100"
    assert fields.document_date == date(2019, 11, 15)
    assert fields.gross_amount == Decimal("110.00")
    assert fields.vat_amount == Decimal("10.00")


def test_unlabeled_noise_does_not_invent_a_total():
    fields = extract_fields("in | ht\n3 Heinen Pint\nTerie no 40. 18\n")
    assert fields.gross_amount is None


def test_receipt_with_two_vat_rates_sums_both():
    fields = extract_fields(
        "Pingo Doce\nNIF 503504564\n01/10/2026\n"
        "IVA 6% 10,00 0,60\nIVA 23% 20,00 4,60\nTOTAL 35,20"
    )
    assert fields.vat_amount == Decimal("5.20")
    assert fields.net_amount == Decimal("30.00")
    assert fields.vat_rate is None
    assert [entry["rate"] for entry in fields.vat_breakdown] == ["6.00", "23.00"]


@pytest.mark.parametrize(
    "raw, expected",
    [("1.234,56", "1234.56"), ("1.234", "1234.00"), ("1,234.56", "1234.56"), ("12,5", "12.50")],
)
def test_amounts_with_thousands_separators(raw, expected):
    assert parse_pt_amount(raw) == Decimal(expected)


def test_nif_must_pass_check_digit():
    assert extract_portuguese_nif("NIF 123456780") is None
    assert extract_portuguese_nif("NIF 503504564") == "503504564"


def test_vendor_nif_preferred_over_customer_nif():
    text = "Cliente NIF 123456789 / Fornecedor NIF 503504564"
    assert extract_portuguese_nif(text) == "503504564"


@pytest.mark.parametrize("vat, net, expected", [
    ("2,20", "10,00", "22.00"),  # Madeira standard
    ("1,20", "10,00", "12.00"),  # Madeira intermediate
    ("0,50", "10,00", "5.00"),   # Madeira reduced
    ("1,60", "10,00", "16.00"),  # Azores standard
    ("0,90", "10,00", "9.00"),   # Azores intermediate
    ("0,40", "10,00", "4.00"),   # Azores reduced
    ("2,30", "10,00", "23.00"),  # Mainland still wins
])
def test_regional_vat_rates_are_recognised(vat, net, expected):
    gross = parse_pt_amount(vat) + parse_pt_amount(net)
    fields = extract_fields(
        f"Loja Funchal\nNIF 503504564\n15/09/2026\nIVA {vat}\nBase {net}\nTOTAL {str(gross).replace('.', ',')}"
    )
    assert fields.vat_rate == Decimal(expected)

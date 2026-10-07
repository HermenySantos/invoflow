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

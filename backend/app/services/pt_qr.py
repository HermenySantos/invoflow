"""
Portuguese invoice QR code (Portaria 195/2020, required on faturas since 2022).

The code holds the issuer NIF, date, document number and the VAT split as
`key:value` pairs joined by `*`, e.g.

    A:503504564*B:999999990*C:PT*D:FT*E:N*F:20260915*G:FT A/12*H:ATCUD*
    I1:PT*I3:10.00*I4:0.60*I7:20.00*I8:4.60*N:5.20*O:35.20*Q:hash*R:cert

When it decodes, its numbers are the ones the issuer reported to the AT, so
they beat anything OCR reads from the printed text.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Optional

from PIL import Image

logger = logging.getLogger(__name__)

# Per fiscal region: (region key, exempt base, then (base, VAT) for the
# reduced, intermediate and standard rates).
_REGIONS = {
    "I": ("I1", "I2", (("I3", "I4"), ("I5", "I6"), ("I7", "I8"))),
    "J": ("J1", "J2", (("J3", "J4"), ("J5", "J6"), ("J7", "J8"))),
    "K": ("K1", "K2", (("K3", "K4"), ("K5", "K6"), ("K7", "K8"))),
}
# (reduced, intermediate, standard) rate for each region code in I1/J1/K1.
_RATES = {
    "PT": ("6.00", "13.00", "23.00"),
    "PT-MA": ("5.00", "12.00", "22.00"),
    "PT-AC": ("4.00", "9.00", "16.00"),
}


@dataclass
class InvoiceQR:
    vendor_nif: Optional[str]
    document_date: Optional[date]
    invoice_number: Optional[str]
    atcud: Optional[str]
    net_amount: Optional[Decimal]
    vat_amount: Optional[Decimal]
    gross_amount: Optional[Decimal]
    vat_rate: Optional[Decimal]  # None when the invoice mixes rates
    breakdown: list[dict] = field(default_factory=list)
    payload: str = ""


def _amount(value: Optional[str]) -> Optional[Decimal]:
    if value is None:
        return None
    try:
        return Decimal(value).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def parse_invoice_qr(payload: str) -> Optional[InvoiceQR]:
    """Parse an AT invoice QR payload, or None if it isn't one."""
    pairs = {}
    for part in payload.split("*"):
        key, sep, value = part.partition(":")
        if sep:
            pairs[key.strip()] = value.strip()
    # A (issuer NIF) and O (total) are mandatory in every AT code.
    if not pairs.get("A") or "O" not in pairs:
        return None

    breakdown: list[dict] = []
    net = Decimal("0")
    for region_key, exempt_key, rate_keys in _REGIONS.values():
        region = pairs.get(region_key)
        if region is None:
            continue
        rates = _RATES.get(region, _RATES["PT"])
        exempt = _amount(pairs.get(exempt_key))
        if exempt:
            net += exempt
            breakdown.append({"rate": "0.00", "net": str(exempt), "vat": "0.00"})
        for (base_key, vat_key), rate in zip(rate_keys, rates):
            base = _amount(pairs.get(base_key))
            vat = _amount(pairs.get(vat_key))
            if base is None and vat is None:
                continue
            net += base or Decimal("0")
            breakdown.append({"rate": rate, "net": str(base or 0), "vat": str(vat or 0)})

    issued = None
    if pairs.get("F"):
        try:
            issued = datetime.strptime(pairs["F"], "%Y%m%d").date()
        except ValueError:
            issued = None

    rates_used = {entry["rate"] for entry in breakdown}
    return InvoiceQR(
        vendor_nif=pairs["A"],
        document_date=issued,
        invoice_number=pairs.get("G") or None,
        atcud=pairs.get("H") or None,
        net_amount=net.quantize(Decimal("0.01")) if breakdown else None,
        vat_amount=_amount(pairs.get("N")),
        gross_amount=_amount(pairs.get("O")),
        vat_rate=Decimal(rates_used.pop()) if len(rates_used) == 1 else None,
        breakdown=breakdown,
        payload=payload,
    )


def read_invoice_qr(image: Image.Image) -> Optional[InvoiceQR]:
    """Find and parse an AT invoice QR in an image; None if there isn't a readable one."""
    try:
        import zxingcpp
    except ImportError:
        logger.warning("zxing-cpp not installed; skipping invoice QR")
        return None
    try:
        barcodes = zxingcpp.read_barcodes(image.convert("L"), formats=zxingcpp.BarcodeFormat.QRCode)
    except Exception as exc:
        logger.warning(f"QR read failed: {exc}")
        return None
    for barcode in barcodes:
        parsed = parse_invoice_qr(barcode.text)
        if parsed:
            return parsed
    return None


def read_invoice_qr_from_file(file_content: bytes, mime_type: str, pdf_page_image) -> Optional[InvoiceQR]:
    """QR from an uploaded image or the first page of a PDF."""
    try:
        if (mime_type or "").lower() == "application/pdf" or file_content[:4] == b"%PDF":
            image = pdf_page_image(file_content)
        else:
            image = Image.open(BytesIO(file_content))
    except Exception:
        return None
    return read_invoice_qr(image) if image is not None else None

"""Quarter-to-date IVA projection.

No database. No Article 21 table. The confirmed deductible total is already
the confirmed half for receipts dated on or before as_of. vat_on_sales is
None when the quarter has no sales entry. Decimal('0') is a real entry.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal, Optional

PROJECTION_LABEL = "IVA previsto (estimativa)"

# Portuguese, matching the summary warnings. Does not say accountant-ready.
PROJECTION_DISCLAIMER = (
    "Estimativa linear do IVA do trimestre, obtida a partir do IVA dedutível "
    "confirmado até à data. Não é uma declaração fiscal."
)

_CENT = Decimal("0.01")


@dataclass(frozen=True)
class QuarterProjectionInput:
    """confirmed_deductible is to-date, not a full-quarter total, and not the
    category-breakdown sum. vat_on_sales None means the quarter row is missing.
    Do not pass a monthly sum."""

    year: int
    quarter: int
    as_of: date
    confirmed_deductible: Decimal
    vat_on_sales: Optional[Decimal]


@dataclass(frozen=True)
class QuarterProjection:
    label: str
    disclaimer: str
    year: int
    quarter: int
    as_of: date
    days_elapsed: int
    days_in_quarter: int
    confirmed_deductible_to_date: Decimal
    projected_deductible: Decimal
    vat_on_sales: Optional[Decimal]
    projected_iva_payable: Optional[Decimal]
    sales_basis: Literal["entered_period_lump", "missing"]


def _quarter_bounds(year: int, quarter: int) -> tuple[date, date]:
    if quarter not in (1, 2, 3, 4):
        raise ValueError("quarter must be 1..4")
    start_month = (quarter - 1) * 3 + 1
    start = date(year, start_month, 1)
    if quarter == 4:
        end = date(year, 12, 31)
    else:
        end = date(year, start_month + 3, 1) - timedelta(days=1)
    return start, end


def _cents(amount: Decimal) -> Decimal:
    return amount.quantize(_CENT, rounding=ROUND_HALF_UP)


def project_quarter_to_date(inputs: QuarterProjectionInput) -> QuarterProjection:
    """Linear run-rate of confirmed deductible VAT across the calendar quarter,
    subtracted from the entered quarter sales lump.

    Sales are not scaled. projected_iva_payable is None exactly when
    vat_on_sales is None. An entered 0 still produces a payable.
    """
    start, end = _quarter_bounds(inputs.year, inputs.quarter)
    days_in_quarter = (end - start).days + 1
    if inputs.as_of < start:
        days_elapsed = 0
    elif inputs.as_of > end:
        days_elapsed = days_in_quarter
    else:
        days_elapsed = (inputs.as_of - start).days + 1

    confirmed = _cents(inputs.confirmed_deductible)
    if days_elapsed == 0:
        projected = Decimal("0.00")
    else:
        projected = _cents(confirmed * Decimal(days_in_quarter) / Decimal(days_elapsed))

    if inputs.vat_on_sales is None:
        payable = None
        basis: Literal["entered_period_lump", "missing"] = "missing"
        sales = None
    else:
        sales = _cents(inputs.vat_on_sales)
        payable = _cents(sales - projected)
        basis = "entered_period_lump"

    return QuarterProjection(
        label=PROJECTION_LABEL,
        disclaimer=PROJECTION_DISCLAIMER,
        year=inputs.year,
        quarter=inputs.quarter,
        as_of=inputs.as_of,
        days_elapsed=days_elapsed,
        days_in_quarter=days_in_quarter,
        confirmed_deductible_to_date=confirmed,
        projected_deductible=projected,
        vat_on_sales=sales,
        projected_iva_payable=payable,
        sales_basis=basis,
    )

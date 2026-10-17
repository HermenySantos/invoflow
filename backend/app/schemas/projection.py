"""Response for the quarter-to-date IVA projection. Not part of the summary."""

from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel


class ProjectionResponse(BaseModel):
    period: str
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
    sales_basis: str
    warnings: list[str] = []

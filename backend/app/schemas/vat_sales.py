"""Pydantic schemas for the VAT-on-sales CRUD endpoints."""

from pydantic import BaseModel, Field, model_validator
from typing import Optional
from decimal import Decimal
from datetime import datetime


class VatSalesCreate(BaseModel):
    """Body for creating or upserting a VAT-on-sales entry."""
    period_type: str = Field(..., pattern=r"^(month|quarter)$")
    year: int = Field(..., ge=2020, le=2099)
    period_value: int = Field(..., ge=1, le=12)
    vat_amount: Decimal = Field(..., ge=0)
    notes: Optional[str] = Field(None, max_length=500)

    @model_validator(mode="after")
    def quarter_is_one_to_four(self) -> "VatSalesCreate":
        if self.period_type == "quarter" and self.period_value > 4:
            raise ValueError("period_value must be 1-4 for a quarter")
        return self


class VatSalesResponse(BaseModel):
    """Single VAT-on-sales entry returned to the client."""
    id: str
    period_type: str
    year: int
    period_value: int
    vat_amount: Decimal
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class VatSalesListResponse(BaseModel):
    """List of VAT-on-sales entries for the user."""
    entries: list[VatSalesResponse]
    total: int

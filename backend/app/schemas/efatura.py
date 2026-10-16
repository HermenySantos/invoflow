"""Request and response models for the e-Fatura pull."""

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class EfaturaPullRequest(BaseModel):
    taxpayer_nif: str = Field(..., pattern=r"^\d{9}$")
    period_start: date
    period_end: date


class EfaturaSkipped(BaseModel):
    source_key: str
    outcome: str
    warning: Optional[str] = None


class EfaturaPullResponse(BaseModel):
    created: list[str]
    linked_existing: list[str]
    unchanged: list[str]
    skipped: list[EfaturaSkipped]
    warnings: list[str]

"""Pydantic schemas for the IVA summary endpoint."""

from pydantic import BaseModel
from decimal import Decimal
from typing import Optional


class CategoryBreakdown(BaseModel):
    """Expense totals for a single category."""
    category: str
    label: str
    count: int
    total: Decimal
    # VAT-specific (only populated for expense categories, not IRS sectors)
    vat_total: Optional[Decimal] = None
    deductible_vat: Optional[Decimal] = None
    deductible_pct: Optional[int] = None   # 0-100


class SummaryResponse(BaseModel):
    """IVA summary for a period."""
    
    # Period info
    period: str            # e.g., "2026-Q1" or "2026-01"
    period_type: str       # "month" or "quarter"
    year: int
    period_value: int      # month 1-12 or quarter 1-4
    
    # Counts
    total_documents: int
    ready_count: int
    needs_review_count: int
    processing_count: int
    failed_count: int
    
    # Amounts (in EUR)
    total_gross: Decimal
    total_net: Decimal
    total_vat: Decimal
    
    # IVA calculation
    deductible_vat: Decimal        # VAT that can be reclaimed (after deductible %)
    vat_on_sales: Decimal          # Manually entered by user
    estimated_iva_payable: Decimal  # vat_on_sales - deductible_vat (negative = refund)
    
    # Category breakdowns
    expense_breakdown: list[CategoryBreakdown] = []
    irs_breakdown: list[CategoryBreakdown] = []
    
    # Confidence (% of documents fully processed)
    confidence_percent: int
    
    # Warnings (human-readable strings)
    warnings: list[str] = []

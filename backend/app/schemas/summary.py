"""Pydantic schemas for the IVA summary endpoint."""

from pydantic import BaseModel
from decimal import Decimal
from typing import Optional

from app.services.iva_adjust import ACCEPTED_MISMATCH_HEADING


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


class AcceptedSeriesMismatch(BaseModel):
    """A counted row whose type and number were accepted as a printed pair."""
    id: str
    vendor_name: Optional[str] = None
    invoice_number: Optional[str] = None
    document_type: Optional[str] = None
    status: str


class ExcludedDocument(BaseModel):
    """A receipt left out of both IVA totals."""
    id: str
    vendor_name: Optional[str] = None
    invoice_number: Optional[str] = None
    document_type: Optional[str] = None
    status: str
    reason: str


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
    excluded_count: int = 0
    excluded_documents: list[ExcludedDocument] = []
    series_mismatch_heading: str = ACCEPTED_MISMATCH_HEADING
    series_mismatch_documents: list[AcceptedSeriesMismatch] = []
    needs_review_count: int
    processing_count: int
    failed_count: int
    
    # Amounts (in EUR)
    total_gross: Decimal
    total_net: Decimal
    total_vat: Decimal
    
    # IVA calculation
    deductible_vat: Decimal        # Reclaimable VAT on checked receipts (ready / accountant_review)
    deductible_vat_pending: Decimal = Decimal("0.00")  # Same, on receipts still in needs_review; not in the estimate
    vat_on_sales: Optional[Decimal]           # Entered by the user; None until they do
    estimated_iva_payable: Optional[Decimal]  # vat_on_sales - deductible_vat (negative = refund); None without vat_on_sales
    
    # Category breakdowns
    expense_breakdown: list[CategoryBreakdown] = []
    irs_breakdown: list[CategoryBreakdown] = []
    
    # Confidence (% of documents fully processed)
    confidence_percent: int
    
    # Warnings (human-readable strings)
    warnings: list[str] = []

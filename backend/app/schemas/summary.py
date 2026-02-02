from pydantic import BaseModel
from decimal import Decimal
from typing import Optional


class SummaryResponse(BaseModel):
    """IVA summary for a period."""
    
    # Period info
    period: str  # e.g., "2026-Q1" or "2026-01"
    period_type: str  # "month" or "quarter"
    
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
    
    # IVA calculation (V0: assume 100% deductible)
    deductible_vat: Decimal
    vat_on_sales: Decimal = Decimal("0.00")  # Manual input for V0
    estimated_iva_payable: Decimal  # VAT on sales - deductible VAT
    
    # Confidence
    confidence_percent: int  # % of documents fully processed
    
    # Warnings
    warnings: list[str] = []

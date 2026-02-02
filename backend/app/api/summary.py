"""
Summary API endpoints.
Provides IVA estimation and document statistics.
"""

from decimal import Decimal
from typing import Optional
from datetime import date
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, extract

from app.core.database import get_db
from app.core.security import get_current_user, CurrentUser
from app.models.user import User
from app.models.document import Document
from app.schemas.summary import SummaryResponse
from app.api.documents import get_or_create_user

router = APIRouter()


@router.get("", response_model=SummaryResponse)
async def get_summary(
    period_type: str = Query("quarter", pattern="^(month|quarter)$"),
    year: Optional[int] = None,
    month: Optional[int] = Query(None, ge=1, le=12),
    quarter: Optional[int] = Query(None, ge=1, le=4),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Get IVA summary for a specified period.
    
    - period_type: "month" or "quarter"
    - year: Year (defaults to current year)
    - month: Month number (1-12) for monthly view
    - quarter: Quarter number (1-4) for quarterly view
    """
    user = get_or_create_user(db, current_user)
    
    # Default to current period
    today = date.today()
    if year is None:
        year = today.year
    
    if period_type == "quarter":
        if quarter is None:
            quarter = (today.month - 1) // 3 + 1
        period = f"{year}-Q{quarter}"
        # Get months in quarter
        start_month = (quarter - 1) * 3 + 1
        end_month = quarter * 3
    else:
        if month is None:
            month = today.month
        period = f"{year}-{month:02d}"
        start_month = month
        end_month = month
    
    # Query documents for the period
    query = (
        db.query(Document)
        .filter(Document.user_id == user.id)
        .filter(
            # Filter by document_date or created_at
            (
                (extract('year', Document.document_date) == year) &
                (extract('month', Document.document_date) >= start_month) &
                (extract('month', Document.document_date) <= end_month)
            ) |
            (
                (Document.document_date.is_(None)) &
                (extract('year', Document.created_at) == year) &
                (extract('month', Document.created_at) >= start_month) &
                (extract('month', Document.created_at) <= end_month)
            )
        )
    )
    
    documents = query.all()
    
    # Calculate counts
    total_documents = len(documents)
    ready_count = sum(1 for d in documents if d.status == "ready")
    needs_review_count = sum(1 for d in documents if d.status == "needs_review")
    processing_count = sum(1 for d in documents if d.status == "processing")
    failed_count = sum(1 for d in documents if d.status == "failed")
    
    # Calculate totals (only from ready and needs_review documents)
    valid_docs = [d for d in documents if d.status in ("ready", "needs_review")]
    
    total_gross = sum(d.gross_amount or Decimal(0) for d in valid_docs)
    total_net = sum(d.net_amount or Decimal(0) for d in valid_docs)
    total_vat = sum(d.vat_amount or Decimal(0) for d in valid_docs)
    
    # V0: Assume 100% deductible
    deductible_vat = total_vat
    vat_on_sales = Decimal("0.00")  # Manual input not implemented in V0
    estimated_iva_payable = vat_on_sales - deductible_vat
    
    # Calculate confidence (% of documents that are ready)
    confidence_percent = 0
    if total_documents > 0:
        confidence_percent = int((ready_count / total_documents) * 100)
    
    # Generate warnings
    warnings = []
    if needs_review_count > 0:
        warnings.append(f"{needs_review_count} document(s) need review")
    if failed_count > 0:
        warnings.append(f"{failed_count} document(s) failed processing")
    if processing_count > 0:
        warnings.append(f"{processing_count} document(s) still processing")
    
    # Check for documents without VAT
    no_vat_count = sum(1 for d in valid_docs if d.vat_amount is None or d.vat_amount == 0)
    if no_vat_count > 0:
        warnings.append(f"{no_vat_count} document(s) have no VAT amount")
    
    return SummaryResponse(
        period=period,
        period_type=period_type,
        total_documents=total_documents,
        ready_count=ready_count,
        needs_review_count=needs_review_count,
        processing_count=processing_count,
        failed_count=failed_count,
        total_gross=total_gross,
        total_net=total_net,
        total_vat=total_vat,
        deductible_vat=deductible_vat,
        vat_on_sales=vat_on_sales,
        estimated_iva_payable=estimated_iva_payable,
        confidence_percent=confidence_percent,
        warnings=warnings,
    )

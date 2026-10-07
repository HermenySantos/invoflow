"""
Summary API endpoints.
Provides IVA estimation and document statistics.

IVA payable = VAT on sales − deductible VAT on expenses
Deductible VAT = Σ (document.vat_amount × category.deductible_pct / 100)
"""

from collections import defaultdict
from decimal import Decimal
from typing import Optional
from datetime import date
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import extract

from app.core.database import get_db
from app.core.security import get_current_user, CurrentUser
from app.models.user import User
from app.models.document import Document
from app.models.vat_sales import VatSalesEntry
from app.schemas.summary import SummaryResponse, CategoryBreakdown
from app.api.documents import get_or_create_user
from app.services.categorization import (
    get_expense_category_label,
    get_irs_sector_label,
    get_deductible_pct,
    deductible_vat_split,
    effective_deductible_pct,
)
from app.services.validation import validate_period_documents

router = APIRouter()


def _format_eur(amount: Decimal) -> str:
    """1234.5 -> "1.234,50 €" (pt-PT)."""
    whole, cents = f"{amount:,.2f}".split(".")
    return f"{whole.replace(',', '.')},{cents} €"


def _get_vat_on_sales(
    db: Session,
    user_id: str,
    period_type: str,
    year: int,
    period_value: int,
) -> Optional[Decimal]:
    """The user's VAT on sales for this period, or None if they haven't entered it."""
    entry = (
        db.query(VatSalesEntry)
        .filter(
            VatSalesEntry.user_id == user_id,
            VatSalesEntry.period_type == period_type,
            VatSalesEntry.year == year,
            VatSalesEntry.period_value == period_value,
        )
        .first()
    )
    return entry.vat_amount if entry else None


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
        start_month = (quarter - 1) * 3 + 1
        end_month = quarter * 3
        period_value = quarter
    else:
        if month is None:
            month = today.month
        period = f"{year}-{month:02d}"
        start_month = month
        end_month = month
        period_value = month
    
    # ── Query documents for the period ──
    query = (
        db.query(Document)
        .filter(Document.deleted_at.is_(None))
        .filter(Document.user_id == user.id)
        .filter(
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
    
    # ── Counts ──
    total_documents = len(documents)
    ready_count = sum(1 for d in documents if d.status == "ready")
    needs_review_count = sum(1 for d in documents if d.status == "needs_review")
    processing_count = sum(1 for d in documents if d.status == "processing")
    failed_count = sum(1 for d in documents if d.status == "failed")
    
    # ── Totals (only ready + needs_review) ──
    valid_docs = [d for d in documents if d.status in ("ready", "needs_review", "accountant_review")]
    
    total_gross = sum(d.gross_amount or Decimal(0) for d in valid_docs)
    total_net = sum(d.net_amount or Decimal(0) for d in valid_docs)
    total_vat = sum(d.vat_amount or Decimal(0) for d in valid_docs)
    
    # ── Deductible VAT (per-category percentage) ──
    # Only checked receipts count toward the estimate; unreviewed OCR values
    # are reported separately.
    deductible_vat, deductible_vat_pending = deductible_vat_split(valid_docs)
    
    # ── VAT on sales (manual input) ──
    vat_on_sales = _get_vat_on_sales(db, user.id, period_type, year, period_value)
    
    # ── Estimated IVA payable ──
    # Without VAT on sales the difference is just -deductible_vat, which reads
    # as a refund; leave it empty until the user has entered their sales.
    estimated_iva_payable = (
        vat_on_sales - deductible_vat if vat_on_sales is not None else None
    )
    
    # ── Confidence ──
    confidence_percent = 0
    if total_documents > 0:
        confidence_percent = int((ready_count / total_documents) * 100)
    
    # ── Warnings (from validation service) ──
    warning_objects = validate_period_documents(db, user.id, documents)
    # Also add a warning if VAT on sales is not set
    if vat_on_sales is None:
        warning_objects.append({
            "code": "no_vat_on_sales",
            "message": "Introduza o IVA das vendas para calcular o IVA a pagar",
            "severity": "info",
        })
    if deductible_vat_pending > 0:
        warning_objects.append({
            "code": "pending_deductible_vat",
            "message": (
                f"{_format_eur(deductible_vat_pending)} de IVA dedutível em {needs_review_count} "
                "recibo(s) por rever — fora da estimativa até serem revistos"
            ),
            "severity": "warning",
        })
    # Flatten to string list for the response (keep simple for V1)
    warnings = [w["message"] for w in warning_objects]
    
    # ── Category breakdowns ──
    expense_totals: dict[str, dict] = defaultdict(lambda: {"count": 0, "total": Decimal(0), "vat": Decimal(0), "deductible": Decimal(0)})
    irs_totals: dict[str, dict] = defaultdict(lambda: {"count": 0, "total": Decimal(0)})
    
    for d in valid_docs:
        cat = d.expense_category or "other"
        sect = d.irs_sector or "geral"
        amount = d.gross_amount or Decimal(0)
        vat = d.vat_amount or Decimal(0)
        pct = effective_deductible_pct(d)
        
        expense_totals[cat]["count"] += 1
        expense_totals[cat]["total"] += amount
        expense_totals[cat]["vat"] += vat
        expense_totals[cat]["deductible"] += (vat * pct / 100)
        
        irs_totals[sect]["count"] += 1
        irs_totals[sect]["total"] += amount
    
    expense_breakdown = sorted(
        [
            CategoryBreakdown(
                category=cat,
                label=get_expense_category_label(cat),
                count=data["count"],
                total=data["total"],
                vat_total=data["vat"],
                deductible_vat=data["deductible"].quantize(Decimal("0.01")),
                deductible_pct=get_deductible_pct(cat),
            )
            for cat, data in expense_totals.items()
        ],
        key=lambda x: x.total,
        reverse=True,
    )
    
    irs_breakdown = sorted(
        [
            CategoryBreakdown(
                category=sect,
                label=get_irs_sector_label(sect),
                count=data["count"],
                total=data["total"],
            )
            for sect, data in irs_totals.items()
        ],
        key=lambda x: x.total,
        reverse=True,
    )
    
    return SummaryResponse(
        period=period,
        period_type=period_type,
        year=year,
        period_value=period_value,
        total_documents=total_documents,
        ready_count=ready_count,
        needs_review_count=needs_review_count,
        processing_count=processing_count,
        failed_count=failed_count,
        total_gross=total_gross,
        total_net=total_net,
        total_vat=total_vat,
        deductible_vat=deductible_vat,
        deductible_vat_pending=deductible_vat_pending,
        vat_on_sales=vat_on_sales,
        estimated_iva_payable=estimated_iva_payable,
        expense_breakdown=expense_breakdown,
        irs_breakdown=irs_breakdown,
        confidence_percent=confidence_percent,
        warnings=warnings,
    )

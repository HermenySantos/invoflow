"""GET /api/summary/projection. A run-rate beside the existing estimate."""

from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import extract
from sqlalchemy.orm import Session

from app.api.documents import get_or_create_user
from app.core.database import get_db
from app.core.security import CurrentUser, get_current_user
from app.models.document import Document
from app.models.vat_sales import VatSalesEntry
from app.schemas.projection import ProjectionResponse
from app.services.categorization import deductible_vat_split
from app.schemas.summary import ExcludedDocument
from app.services.iva_adjust import (
    EXCLUDED_HEADING,
    credit_note_warnings,
    duplicate_warnings,
    exclusion_reason,
    left_out,
)
from app.services.iva_projection import QuarterProjectionInput, project_quarter_to_date

router = APIRouter()


def _effective_date(document: Document) -> date:
    if document.document_date:
        return document.document_date
    return document.created_at.date()


@router.get("/projection", response_model=ProjectionResponse)
async def get_projection(
    year: Optional[int] = None,
    quarter: Optional[int] = Query(None, ge=1, le=4),
    as_of: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Quarter window matches the summary, then rows after as_of are dropped."""
    user = get_or_create_user(db, current_user)
    today = date.today()
    if year is None:
        year = today.year
    if quarter is None:
        quarter = (today.month - 1) // 3 + 1
    if as_of is None:
        as_of = today

    start_month = (quarter - 1) * 3 + 1
    end_month = quarter * 3
    documents = (
        db.query(Document)
        .filter(Document.deleted_at.is_(None))
        .filter(Document.user_id == user.id)
        .filter(
            (
                (extract("year", Document.document_date) == year)
                & (extract("month", Document.document_date) >= start_month)
                & (extract("month", Document.document_date) <= end_month)
            )
            | (
                (Document.document_date.is_(None))
                & (extract("year", Document.created_at) == year)
                & (extract("month", Document.created_at) >= start_month)
                & (extract("month", Document.created_at) <= end_month)
            )
        )
        .all()
    )
    clipped = [document for document in documents if _effective_date(document) <= as_of]
    library = (
        db.query(Document)
        .filter(Document.deleted_at.is_(None))
        .filter(Document.user_id == user.id)
        .filter(Document.status.in_(("ready", "needs_review", "accountant_review")))
        .all()
    )
    confirmed, _pending = deductible_vat_split(clipped, library)
    credit_warnings = credit_note_warnings(clipped, library) + duplicate_warnings(clipped, library)

    entry = (
        db.query(VatSalesEntry)
        .filter(
            VatSalesEntry.user_id == user.id,
            VatSalesEntry.period_type == "quarter",
            VatSalesEntry.year == year,
            VatSalesEntry.period_value == quarter,
        )
        .first()
    )
    vat_on_sales = entry.vat_amount if entry else None
    if isinstance(vat_on_sales, Decimal):
        vat_on_sales = Decimal(vat_on_sales)

    projection = project_quarter_to_date(
        QuarterProjectionInput(
            year=year,
            quarter=quarter,
            as_of=as_of,
            confirmed_deductible=confirmed,
            vat_on_sales=vat_on_sales,
        )
    )
    return ProjectionResponse(
        period=f"{projection.year}-Q{projection.quarter}",
        label=projection.label,
        disclaimer=projection.disclaimer,
        year=projection.year,
        quarter=projection.quarter,
        as_of=projection.as_of,
        days_elapsed=projection.days_elapsed,
        days_in_quarter=projection.days_in_quarter,
        confirmed_deductible_to_date=projection.confirmed_deductible_to_date,
        projected_deductible=projection.projected_deductible,
        vat_on_sales=projection.vat_on_sales,
        projected_iva_payable=projection.projected_iva_payable,
        sales_basis=projection.sales_basis,
        warnings=credit_warnings,
        excluded_heading=EXCLUDED_HEADING,
        excluded_documents=[
            ExcludedDocument(
                id=str(document.id),
                vendor_name=document.vendor_name,
                invoice_number=document.invoice_number,
                document_type=document.document_type or "unclassified",
                status=document.status,
                reason=exclusion_reason(document) or "por rever",
            )
            for document in left_out(clipped, library)
        ],
    )

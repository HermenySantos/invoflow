"""
Export API endpoints.
Generates accountant-ready ZIP packages.
"""

from typing import Optional
from datetime import date, datetime
from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy import extract

from app.core.database import get_db
from app.core.security import get_current_user, CurrentUser
from app.models.document import Document
from app.schemas.export import ExportResponse
from app.services.export import get_export_service
from app.api.documents import get_or_create_user

router = APIRouter()


@router.get("")
async def generate_export(
    period_type: str = Query("quarter", pattern="^(month|quarter)$"),
    year: Optional[int] = None,
    month: Optional[int] = Query(None, ge=1, le=12),
    quarter: Optional[int] = Query(None, ge=1, le=4),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Generate and download an export package for the specified period.
    Returns a ZIP file with original documents and summary.
    """
    user = get_or_create_user(db, current_user)
    export_service = get_export_service()
    
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
        .filter(Document.status.in_(["ready", "needs_review"]))
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
        .order_by(Document.document_date, Document.created_at)
    )
    
    documents = query.all()
    
    # Generate export
    zip_bytes, filename = export_service.generate_export(
        db=db,
        user_id=str(user.id),
        documents=documents,
        period=period,
    )
    
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(zip_bytes)),
        },
    )

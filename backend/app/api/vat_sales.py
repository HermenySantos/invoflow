"""
VAT-on-sales CRUD endpoints.
Users enter the total VAT charged on their sales for a given period.
The summary endpoint uses this to compute estimated IVA payable.
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user, CurrentUser
from app.models.vat_sales import VatSalesEntry
from app.schemas.vat_sales import (
    VatSalesCreate,
    VatSalesResponse,
    VatSalesListResponse,
)
from app.api.documents import get_or_create_user

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("", response_model=VatSalesResponse, status_code=status.HTTP_201_CREATED)
async def upsert_vat_sales(
    body: VatSalesCreate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Create or update VAT-on-sales for a period (upsert).
    If an entry already exists for the same user + period, it is updated.
    """
    user = get_or_create_user(db, current_user)

    # Check for existing entry
    existing = (
        db.query(VatSalesEntry)
        .filter(
            VatSalesEntry.user_id == user.id,
            VatSalesEntry.period_type == body.period_type,
            VatSalesEntry.year == body.year,
            VatSalesEntry.period_value == body.period_value,
        )
        .first()
    )

    if existing:
        existing.vat_amount = body.vat_amount
        if body.notes is not None:
            existing.notes = body.notes
        db.commit()
        db.refresh(existing)
        return existing

    entry = VatSalesEntry(
        user_id=user.id,
        period_type=body.period_type,
        year=body.year,
        period_value=body.period_value,
        vat_amount=body.vat_amount,
        notes=body.notes,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.get("", response_model=VatSalesListResponse)
async def list_vat_sales(
    year: Optional[int] = Query(None, ge=2020, le=2099),
    period_type: Optional[str] = Query(None, pattern="^(month|quarter)$"),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """List VAT-on-sales entries for the current user, optionally filtered."""
    user = get_or_create_user(db, current_user)

    query = db.query(VatSalesEntry).filter(VatSalesEntry.user_id == user.id)
    if year:
        query = query.filter(VatSalesEntry.year == year)
    if period_type:
        query = query.filter(VatSalesEntry.period_type == period_type)

    entries = query.order_by(VatSalesEntry.year.desc(), VatSalesEntry.period_value.desc()).all()
    return VatSalesListResponse(entries=entries, total=len(entries))


@router.get("/{entry_id}", response_model=VatSalesResponse)
async def get_vat_sales(
    entry_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get a single VAT-on-sales entry."""
    user = get_or_create_user(db, current_user)
    entry = (
        db.query(VatSalesEntry)
        .filter(VatSalesEntry.id == entry_id, VatSalesEntry.user_id == user.id)
        .first()
    )
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")
    return entry


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_vat_sales(
    entry_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Delete a VAT-on-sales entry."""
    user = get_or_create_user(db, current_user)
    entry = (
        db.query(VatSalesEntry)
        .filter(VatSalesEntry.id == entry_id, VatSalesEntry.user_id == user.id)
        .first()
    )
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")
    db.delete(entry)
    db.commit()

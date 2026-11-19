"""
Account endpoints: the whole-account data export.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.documents import get_or_create_user
from app.core.config import get_settings
from app.core.database import get_db
from app.core.rate_limit import RATE_LIMITS, limiter
from app.core.security import CurrentUser, get_current_user
from app.services.account_export import get_account_export_service

router = APIRouter()


@router.get("/export")
@limiter.limit(RATE_LIMITS["account_export"])
def export_account_data(
    request: Request,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """ZIP with every document, VAT-on-sales entry and receipt file of the current user."""
    if not get_settings().account_export_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    user = get_or_create_user(db, current_user)
    zip_bytes, filename = get_account_export_service().build(db, user)
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(zip_bytes)),
            "Cache-Control": "no-store",
        },
    )

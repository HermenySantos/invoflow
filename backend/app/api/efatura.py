"""POST /api/efatura/pull. Off unless EFATURA_PULL_ENABLED is true."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.documents import get_or_create_user
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import CurrentUser, get_current_user
from app.schemas.efatura import EfaturaPullRequest, EfaturaPullResponse, EfaturaSkipped
from app.services.efatura import (
    EFaturaConfigError,
    EFaturaDisabled,
    EFaturaSubjectMismatch,
    InvoiceQuery,
    build_efatura_client,
    import_purchases,
)

router = APIRouter()


@router.post("/pull", response_model=EfaturaPullResponse)
async def pull_efatura(
    body: EfaturaPullRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        client = build_efatura_client(get_settings())
    except EFaturaDisabled as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except EFaturaConfigError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    try:
        invoices = client.fetch(
            InvoiceQuery(
                taxpayer_nif=body.taxpayer_nif,
                period_start=body.period_start,
                period_end=body.period_end,
            )
        )
    except NotImplementedError as exc:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(exc)) from exc

    user = get_or_create_user(db, current_user)
    try:
        result = import_purchases(
            db,
            user_id=user.id,
            taxpayer_nif=body.taxpayer_nif,
            invoices=invoices,
        )
    except EFaturaSubjectMismatch as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    db.commit()
    return EfaturaPullResponse(
        created=list(result.created),
        linked_existing=list(result.linked_existing),
        unchanged=list(result.unchanged),
        skipped=[
            EfaturaSkipped(source_key=item.source_key, outcome=item.outcome, warning=item.warning)
            for item in result.skipped
        ],
        warnings=list(result.warnings),
    )

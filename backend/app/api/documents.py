"""
Document API endpoints.
Handles upload, listing, and management of receipts/invoices.
"""

import json
from datetime import date, datetime
from decimal import Decimal
import logging
import random
from typing import Optional, Dict, Any
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import desc, or_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.database import get_db, session_factory
from app.core.security import get_current_user, CurrentUser
from app.core.rate_limit import limiter, RATE_LIMITS
from app.models.user import User
from app.models.document import Document
from app.models.efatura import EfaturaLink
from app.schemas.document import (
    DocumentCreate,
    DocumentUpdate,
    DocumentResponse,
    DocumentListResponse,
    UploadUrlRequest,
    UploadUrlResponse,
    FieldConfidence,
    AMOUNT_MISMATCH_DETAIL,
    CONCRETE_DOCUMENT_TYPES,
    NULL_TYPE_DETAIL,
    SERIES_MISMATCH_DETAIL,
    SERIES_OVERRIDE_WARNING,
    TYPE_REQUIRED_DETAIL,
    amounts_are_consistent,
    crosses_credit_boundary,
    keeps_at_issued_pair,
    series_disagrees,
    series_fields_changed,
    series_override_allowed,
)
from app.services.pt_qr import parse_invoice_qr
from app.services.storage import get_storage_service, MAX_FILE_SIZE
from app.services.efatura import detach_deleted_scan
from app.services.processing import read_receipt
from app.services.categorization import effective_deductible_pct
from app.services.audit import (
    log_document_create,
    log_document_update,
    log_document_delete,
    log_series_mismatch_accepted,
)
from app.services.validation import validate_document, detect_duplicates
from app.services.iva_adjust import reading_is_fictional
from app.services.uploads import UNSUPPORTED_TYPE_DETAIL, prepare_upload

logger = logging.getLogger(__name__)
router = APIRouter()


def parse_field_confidence(ocr_raw_response: Optional[str], overall_confidence: Optional[float] = None) -> Optional[FieldConfidence]:
    """
    Parse per-field confidence from OCR raw response.
    For Azure Document Intelligence, extracts confidence from each field.
    For mock mode, generates realistic mock confidence values.
    """
    if not ocr_raw_response:
        return None
    
    try:
        data = json.loads(ocr_raw_response)
        
        # Check if this is mock data
        if data.get("mock"):
            # Generate mock field confidence based on overall confidence
            base_conf = overall_confidence if overall_confidence else 85.0
            # Seeded by the response so a document shows the same values on every load.
            rng = random.Random(ocr_raw_response)
            return FieldConfidence(
                vendor_name=min(100, base_conf + rng.uniform(-5, 10)),
                vendor_nif=min(100, base_conf + rng.uniform(-15, 5)) if rng.random() > 0.2 else None,
                invoice_number=min(100, base_conf + rng.uniform(-10, 10)),
                document_date=min(100, base_conf + rng.uniform(-5, 15)),
                net_amount=min(100, base_conf + rng.uniform(-10, 5)),
                vat_amount=min(100, base_conf + rng.uniform(-10, 5)),
                gross_amount=min(100, base_conf + rng.uniform(-3, 10)),
                vat_rate=min(100, base_conf + rng.uniform(-20, 10)) if rng.random() > 0.3 else None,
            )
        
        # Parse Azure Document Intelligence response
        analyze_result = data.get("analyzeResult", {})
        documents = analyze_result.get("documents", [])
        
        if not documents:
            return None
        
        fields = documents[0].get("fields", {})
        
        # Map Azure field names to our field names
        field_mapping = {
            "MerchantName": "vendor_name",
            "TransactionId": "invoice_number",
            "TransactionDate": "document_date",
            "Total": "gross_amount",
            "TotalTax": "vat_amount",
        }
        
        confidence_data = {}
        for azure_field, our_field in field_mapping.items():
            field_data = fields.get(azure_field, {})
            if "confidence" in field_data:
                confidence_data[our_field] = field_data["confidence"] * 100
        
        # NIF confidence (extracted separately, use a default if found)
        if "vendor_nif" not in confidence_data:
            confidence_data["vendor_nif"] = None
        
        # Calculate net_amount confidence as average of gross and vat
        if "gross_amount" in confidence_data and "vat_amount" in confidence_data:
            gross_conf = confidence_data.get("gross_amount", 0)
            vat_conf = confidence_data.get("vat_amount", 0)
            if gross_conf and vat_conf:
                confidence_data["net_amount"] = (gross_conf + vat_conf) / 2
        
        return FieldConfidence(**confidence_data) if confidence_data else None
        
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.warning(f"Failed to parse field confidence: {e}")
        return None


def _json_object(raw: Optional[str]) -> Optional[dict]:
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _efatura_issued(document: Document, db: Optional[Session]) -> Optional[tuple]:
    """Type and number from the e-Fatura snapshot linked to this row."""
    if db is None:
        return None
    link = (
        db.query(EfaturaLink)
        .filter(EfaturaLink.document_id == document.id)
        .order_by(desc(EfaturaLink.created_at), desc(EfaturaLink.id))
        .first()
    )
    if link is None or not link.payload_json:
        return None
    payload = _json_object(link.payload_json)
    if not payload:
        return None
    at_type = str(payload.get("document_type") or "").strip().upper() or None
    at_number = str(payload.get("invoice_number") or "").strip() or None
    if not at_type and not at_number:
        return None
    return at_type, at_number


def _column_at_type(document: Document) -> Optional[str]:
    """Stored AT code, including a legacy row whose QR payload is gone."""
    raw = getattr(document, "at_document_type", None)
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


def _at_issued(document: Document, db: Optional[Session]) -> Optional[tuple]:
    """(type, number) AT supplied, from a QR payload or an e-Fatura link.

    A scanned row linked to an e-Fatura record has a pair even though the
    file itself is not an e-Fatura upload. A legacy column with no payload
    and no link is not a pair; the column still blocks the printed-pair flag.
    """
    raw = _json_object(document.ocr_raw_response)
    qr = raw.get("qr") if raw else None
    if isinstance(qr, dict) and qr.get("payload"):
        try:
            parsed = parse_invoice_qr(str(qr["payload"]))
        except (TypeError, ValueError):
            parsed = None
        if parsed is not None and (parsed.document_type or parsed.invoice_number):
            at_type = (parsed.document_type or "").strip().upper() or None
            at_number = (parsed.invoice_number or "").strip() or None
            return at_type, at_number
    return _efatura_issued(document, db)


def build_document_response(
    document: Document,
    file_url: Optional[str] = None,
    db: Optional[Session] = None,
) -> DocumentResponse:
    """Build a DocumentResponse with computed fields, parsed confidence, and validation warnings."""
    field_confidence = parse_field_confidence(
        document.ocr_raw_response, 
        float(document.ocr_confidence) if document.ocr_confidence else None
    )
    issued = _at_issued(document, db)
    at_typed = _column_at_type(document) is not None
    issued_type = issued[0] if issued else None
    issued_number = issued[1] if issued else None

    # Run validation
    warnings = validate_document(document)
    if db is not None:
        warnings += detect_duplicates(db, document.user_id, document)
    # A stored pair that is not the one AT issued stays visible as a warning.
    # The confirmation wording is only for a mismatch the flag can still accept.
    if series_disagrees(document.document_type, document.invoice_number) and not keeps_at_issued_pair(
        document.document_type, document.invoice_number, issued
    ):
        overridable = series_override_allowed(
            document.document_type, document.invoice_number, issued, at_typed=at_typed
        )
        warnings.append(
            {
                "code": "series_mismatch",
                "message": SERIES_OVERRIDE_WARNING if overridable else SERIES_MISMATCH_DETAIL,
                "severity": "warning",
                "field": "invoice_number",
            }
        )

    return DocumentResponse(
        id=document.id,
        user_id=document.user_id,
        status=document.status,
        storage_key=document.storage_key,
        original_filename=document.original_filename,
        mime_type=document.mime_type,
        file_size=document.file_size,
        vendor_name=document.vendor_name,
        vendor_nif=document.vendor_nif,
        invoice_number=document.invoice_number,
        document_type=document.document_type or "unclassified",
        suggested_type=getattr(document, "suggested_type", None),
        suggested_invoice_number=getattr(document, "suggested_invoice_number", None),
        at_document_type=issued_type or getattr(document, "at_document_type", None),
        at_invoice_number=issued_number,
        document_date=document.document_date,
        net_amount=document.net_amount,
        vat_amount=document.vat_amount,
        gross_amount=document.gross_amount,
        vat_rate=document.vat_rate,
        ocr_confidence=document.ocr_confidence,
        field_confidence=field_confidence,
        review_notes=getattr(document, 'review_notes', None),
        expense_category=getattr(document, 'expense_category', None),
        irs_sector=getattr(document, 'irs_sector', None),
        deductible_pct=effective_deductible_pct(document),
        deductible_pct_override=document.deductible_pct_override,
        series_mismatch_accepted=bool(getattr(document, "series_mismatch_accepted", False)),
        validation_warnings=warnings,
        fictional=reading_is_fictional(document.ocr_raw_response),
        period_tag=document.period_tag,
        quarter_tag=document.quarter_tag,
        file_url=file_url,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


def get_or_create_user(db: Session, current_user: CurrentUser) -> User:
    """Get existing user or create new one from auth data."""
    user = db.query(User).filter(User.clerk_id == current_user.user_id).first()
    if not user:
        try:
            user = User(
                clerk_id=current_user.user_id,
                email=current_user.email,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"Failed to create user: {e}")
            # Try to fetch again in case of race condition
            user = db.query(User).filter(User.clerk_id == current_user.user_id).first()
            if not user:
                raise
    return user


@router.post("/upload-url", response_model=UploadUrlResponse)
@limiter.limit(RATE_LIMITS["upload"])
async def get_upload_url(
    request: Request,
    upload_request: UploadUrlRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Get a presigned URL for uploading a document.
    Client should PUT the file to this URL, then call POST /documents.
    """
    storage = get_storage_service()
    storage_key = storage.generate_storage_key(current_user.user_id, upload_request.filename)
    upload_url = storage.get_upload_url(storage_key, upload_request.content_type)
    
    return UploadUrlResponse(
        upload_url=upload_url,
        storage_key=storage_key,
        expires_in=900,
    )


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(RATE_LIMITS["upload"])
async def create_document(
    request: Request,
    doc_create: DocumentCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Create a document record and trigger OCR processing.
    Call this after successfully uploading the file.
    """
    # Validate file size
    if doc_create.file_size and doc_create.file_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File size exceeds maximum allowed size of {MAX_FILE_SIZE // (1024 * 1024)}MB",
        )

    # A key that walks out of the user's folder is rejected before the prefix
    # check, because "user/../other" still starts with "user/".
    storage_key = doc_create.storage_key
    if (
        not storage_key
        or "\x00" in storage_key
        or "\\" in storage_key
        or storage_key.startswith("/")
        or any(part == ".." for part in storage_key.split("/"))
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid storage key",
        )

    # Upload keys are issued under the user's own folder; anything else is another user's file.
    if not storage_key.startswith(f"{current_user.user_id}/"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Storage key does not belong to the current user",
        )

    user = get_or_create_user(db, current_user)
    storage = get_storage_service()
    stored = storage.get_file(storage_key)
    if stored is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Uploaded file was not found",
        )
    prepared = prepare_upload(stored)
    if prepared is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=UNSUPPORTED_TYPE_DETAIL,
        )
    if prepared != stored:
        storage.replace_file(storage_key, prepared)

    try:
        document = Document(
            user_id=user.id,
            storage_key=doc_create.storage_key,
            original_filename=doc_create.original_filename,
            mime_type=doc_create.mime_type,
            file_size=doc_create.file_size,
            status="processing",
        )
        db.add(document)
        db.flush()
        log_document_create(db, document_id=document.id, user_id=user.id)
        db.commit()
        db.refresh(document)
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error creating document: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create document",
        )

    # OCR runs after the response; the receipt shows "A processar" until then.
    background_tasks.add_task(read_receipt, session_factory(request), document.id)

    file_url = storage.get_download_url(document.storage_key)
    return build_document_response(document, file_url, db)


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: Optional[str] = Query(None, alias="status"),
    expense_category: Optional[str] = Query(None),
    irs_sector: Optional[str] = Query(None),
    q: Optional[str] = Query(None, max_length=100, description="Vendor, NIF, invoice number or filename"),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    min_amount: Optional[Decimal] = Query(None, ge=0),
    max_amount: Optional[Decimal] = Query(None, ge=0),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    List all documents for the current user.
    Supports pagination, status/category filters, text search and date/amount ranges.
    """
    user = get_or_create_user(db, current_user)
    storage = get_storage_service()
    
    # Build query
    query = db.query(Document).filter(Document.user_id == user.id, Document.deleted_at.is_(None))
    
    if status_filter:
        query = query.filter(Document.status == status_filter)
    if expense_category:
        query = query.filter(Document.expense_category == expense_category)
    if irs_sector:
        query = query.filter(Document.irs_sector == irs_sector)
    if q and q.strip():
        escaped = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        query = query.filter(or_(
            Document.vendor_name.ilike(pattern, escape="\\"),
            Document.vendor_nif.ilike(pattern, escape="\\"),
            Document.invoice_number.ilike(pattern, escape="\\"),
            Document.original_filename.ilike(pattern, escape="\\"),
        ))
    if date_from:
        query = query.filter(Document.document_date >= date_from)
    if date_to:
        query = query.filter(Document.document_date <= date_to)
    if min_amount is not None:
        query = query.filter(Document.gross_amount >= min_amount)
    if max_amount is not None:
        query = query.filter(Document.gross_amount <= max_amount)
    
    # Get total count
    total = query.count()
    
    # Apply pagination
    documents = (
        query
        .order_by(desc(Document.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    
    # Generate URLs and response
    doc_responses = []
    for doc in documents:
        file_url = storage.get_download_url(doc.storage_key)
        doc_responses.append(build_document_response(doc, file_url))
    
    return DocumentListResponse(
        documents=doc_responses,
        total=total,
        page=page,
        page_size=page_size,
        has_more=(page * page_size) < total,
    )


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get a single document by ID."""
    user = get_or_create_user(db, current_user)
    storage = get_storage_service()
    
    document = (
        db.query(Document)
        .filter(
            Document.id == document_id,
            Document.user_id == user.id,
            Document.deleted_at.is_(None),
        )
        .first()
    )
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    
    file_url = storage.get_download_url(document.storage_key)
    return build_document_response(document, file_url, db)


@router.patch("/{document_id}", response_model=DocumentResponse)
async def update_document(
    document_id: str,
    doc_update: DocumentUpdate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update document fields (for manual corrections)."""
    user = get_or_create_user(db, current_user)
    storage = get_storage_service()
    
    document = (
        db.query(Document)
        .filter(
            Document.id == document_id,
            Document.user_id == user.id,
            Document.deleted_at.is_(None),
        )
        .first()
    )
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    
    try:
        # Capture before-state for audit
        update_data = doc_update.model_dump(exclude_unset=True)
        if "document_type" in update_data and update_data["document_type"] is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=NULL_TYPE_DETAIL,
            )
        confirmed = {"ready", "accountant_review"}
        amount_fields = ("net_amount", "vat_amount", "gross_amount")
        was_confirmed = document.status in confirmed
        type_changed = (
            "document_type" in update_data
            and update_data["document_type"] != document.document_type
        )
        merged_net = update_data.get("net_amount", document.net_amount)
        merged_vat = update_data.get("vat_amount", document.vat_amount)
        merged_gross = update_data.get("gross_amount", document.gross_amount)
        merged_type = update_data.get("document_type", document.document_type)
        # A ready row is re-checked on every amount or type edit, not only
        # when the status itself moves. A draft may stay inconsistent.
        if was_confirmed and any(field in update_data for field in (*amount_fields, "document_type")):
            if not amounts_are_consistent(merged_net, merged_vat, merged_gross):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=AMOUNT_MISMATCH_DETAIL,
                )
        if update_data.get("status") in confirmed and not amounts_are_consistent(
            merged_net, merged_vat, merged_gross
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=AMOUNT_MISMATCH_DETAIL,
            )
        # Retyping a checked row sends it back to review.
        if type_changed and was_confirmed:
            update_data["status"] = "needs_review"
        if (
            update_data.get("status") in confirmed
            and merged_type not in CONCRETE_DOCUMENT_TYPES
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=TYPE_REQUIRED_DETAIL,
            )
        merged_number = (
            update_data["invoice_number"]
            if "invoice_number" in update_data
            else document.invoice_number
        )
        # Not a column. A category, deductible or notes edit does not send it.
        accept_series_mismatch = bool(update_data.pop("accept_series_mismatch", False))
        confirming = update_data.get("status") in confirmed
        # A status-only confirm is checked too. An unchanged AT pair is exempt.
        # The flag is honoured only when the row has no QR pair, no e-Fatura
        # pair and no stored AT type, and only inside {FT, FS, FR}.
        override_applied = False
        before_type = document.document_type
        before_number = document.invoice_number
        before_accepted = bool(document.series_mismatch_accepted)
        if series_fields_changed(document.document_type, document.invoice_number, update_data) or confirming:
            issued = _at_issued(document, db)
            at_typed = _column_at_type(document) is not None
            known_at = (issued[0] if issued and issued[0] else None) or _column_at_type(document)
            # An AT pair, including a scanned row linked to e-Fatura, cannot
            # be retyped across the credit/invoice boundary. An unprefixed
            # number does not make that retype legal.
            if known_at and crosses_credit_boundary(known_at, merged_type):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=SERIES_MISMATCH_DETAIL,
                )
            still_at = keeps_at_issued_pair(merged_type, merged_number, issued)
            disagrees = series_disagrees(merged_type, merged_number) and not still_at
            if disagrees:
                allowed = accept_series_mismatch and series_override_allowed(
                    merged_type, merged_number, issued, at_typed=at_typed
                )
                if not allowed:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail=SERIES_MISMATCH_DETAIL,
                    )
                update_data["series_mismatch_accepted"] = True
                override_applied = True
            elif before_accepted:
                update_data["series_mismatch_accepted"] = False
        before_state = {field: getattr(document, field, None) for field in update_data}

        # Update fields
        for field, value in update_data.items():
            setattr(document, field, value)
        
        # Audit log
        after_state = {field: getattr(document, field, None) for field in update_data}
        log_document_update(
            db,
            document_id=document.id,
            user_id=user.id,
            before=before_state,
            after=after_state,
        )
        if override_applied:
            log_series_mismatch_accepted(
                db,
                document_id=document.id,
                user_id=user.id,
                document_type=document.document_type,
                invoice_number=document.invoice_number,
                previous_accepted=before_accepted,
                previous_type=before_type,
                previous_number=before_number,
            )

        db.commit()
        db.refresh(document)
    except HTTPException:
        db.rollback()
        raise
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error updating document: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update document",
        )
    
    file_url = storage.get_download_url(document.storage_key)
    return build_document_response(document, file_url, db)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Hide a document. The row and the original file are kept (invoice retention)."""
    user = get_or_create_user(db, current_user)
    
    # Lock the scan so a second DELETE waits, then sees it already hidden.
    document = (
        db.query(Document)
        .filter(
            Document.id == document_id,
            Document.user_id == user.id,
            Document.deleted_at.is_(None),
        )
        .with_for_update()
        .first()
    )
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    
    try:
        log_document_delete(db, document_id=document.id, user_id=user.id)
        document.deleted_at = datetime.utcnow()
        # The scan leaves the totals. An e-Fatura invoice that was only
        # represented by this row is stored again as its own AT document.
        detach_deleted_scan(db, document)
        db.commit()
    except IntegrityError:
        db.rollback()
        logger.warning("AT invoice restore collided for document %s", document_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error deleting document: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete document",
        )

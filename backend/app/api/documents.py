"""
Document API endpoints.
Handles upload, listing, and management of receipts/invoices.
"""

import json
import logging
import random
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import desc
from sqlalchemy.exc import SQLAlchemyError

from app.core.database import get_db
from app.core.security import get_current_user, CurrentUser
from app.core.rate_limit import limiter, RATE_LIMITS
from app.models.user import User
from app.models.document import Document
from app.schemas.document import (
    DocumentCreate,
    DocumentUpdate,
    DocumentResponse,
    DocumentListResponse,
    UploadUrlRequest,
    UploadUrlResponse,
    FieldConfidence,
)
from app.services.storage import get_storage_service, MAX_FILE_SIZE
from app.services.ocr import get_ocr_service
from app.services.categorization import categorize_document
from app.services.audit import (
    log_document_create,
    log_ocr_extraction,
    log_auto_categorize,
    log_document_update,
    log_document_delete,
)
from app.services.validation import validate_document, detect_duplicates

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
            return FieldConfidence(
                vendor_name=min(100, base_conf + random.uniform(-5, 10)),
                vendor_nif=min(100, base_conf + random.uniform(-15, 5)) if random.random() > 0.2 else None,
                invoice_number=min(100, base_conf + random.uniform(-10, 10)),
                document_date=min(100, base_conf + random.uniform(-5, 15)),
                net_amount=min(100, base_conf + random.uniform(-10, 5)),
                vat_amount=min(100, base_conf + random.uniform(-10, 5)),
                gross_amount=min(100, base_conf + random.uniform(-3, 10)),
                vat_rate=min(100, base_conf + random.uniform(-20, 10)) if random.random() > 0.3 else None,
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

    # Run validation
    warnings = validate_document(document)
    if db is not None:
        warnings += detect_duplicates(db, document.user_id, document)

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
        validation_warnings=warnings,
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

    # Upload keys are issued under the user's own folder; anything else is another user's file.
    if not doc_create.storage_key.startswith(f"{current_user.user_id}/"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Storage key does not belong to the current user",
        )

    user = get_or_create_user(db, current_user)
    storage = get_storage_service()
    ocr = get_ocr_service()
    
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

        file_content = storage.get_file(doc_create.storage_key)

        if file_content or ocr.backend == "mock":
            try:
                ocr_result = await ocr.process_document(
                    file_content or b"mock_content",
                    doc_create.mime_type,
                )
                
                # Update document with OCR results
                document.vendor_name = ocr_result.vendor_name
                document.vendor_nif = ocr_result.vendor_nif
                document.invoice_number = ocr_result.invoice_number
                document.document_date = ocr_result.document_date
                document.net_amount = ocr_result.net_amount
                document.vat_amount = ocr_result.vat_amount
                document.gross_amount = ocr_result.gross_amount
                document.vat_rate = ocr_result.vat_rate
                document.ocr_confidence = ocr_result.confidence
                document.ocr_raw_response = ocr_result.raw_response
                
                # Auto-categorize based on vendor
                expense_cat, irs_sect = categorize_document(
                    ocr_result.vendor_name, ocr_result.vendor_nif
                )
                document.expense_category = expense_cat
                document.irs_sector = irs_sect
                
                if ocr_result.error:
                    document.status = "failed"
                elif ocr_result.needs_review:
                    document.status = "needs_review"
                else:
                    document.status = "ready"
                    
            except Exception as e:
                logger.error(f"OCR processing failed: {e}")
                document.status = "failed"
                document.ocr_raw_response = str(e)
        else:
            document.status = "failed"
            document.ocr_raw_response = "File content not available for OCR processing"
        
        # ── Audit logging ──
        log_document_create(db, document_id=document.id, user_id=user.id)

        if document.status in ("ready", "needs_review"):
            # Log OCR extraction
            log_ocr_extraction(
                db,
                document_id=document.id,
                user_id=user.id,
                extracted_fields={
                    "vendor_name": document.vendor_name,
                    "vendor_nif": document.vendor_nif,
                    "invoice_number": document.invoice_number,
                    "document_date": document.document_date,
                    "net_amount": document.net_amount,
                    "vat_amount": document.vat_amount,
                    "gross_amount": document.gross_amount,
                    "vat_rate": document.vat_rate,
                },
            )
            # Log auto-categorization
            if document.expense_category:
                log_auto_categorize(
                    db,
                    document_id=document.id,
                    user_id=user.id,
                    expense_category=document.expense_category,
                    irs_sector=document.irs_sector or "geral",
                )

        db.commit()
        db.refresh(document)
        
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error creating document: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create document",
        )
    
    file_url = storage.get_download_url(document.storage_key)
    return build_document_response(document, file_url, db)


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: Optional[str] = Query(None, alias="status"),
    expense_category: Optional[str] = Query(None),
    irs_sector: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    List all documents for the current user.
    Supports pagination, status, and category filtering.
    """
    user = get_or_create_user(db, current_user)
    storage = get_storage_service()
    
    # Build query
    query = db.query(Document).filter(Document.user_id == user.id)
    
    if status_filter:
        query = query.filter(Document.status == status_filter)
    if expense_category:
        query = query.filter(Document.expense_category == expense_category)
    if irs_sector:
        query = query.filter(Document.irs_sector == irs_sector)
    
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
        .filter(Document.id == document_id, Document.user_id == user.id)
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
        .filter(Document.id == document_id, Document.user_id == user.id)
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

        db.commit()
        db.refresh(document)
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
    """Delete a document."""
    user = get_or_create_user(db, current_user)
    storage = get_storage_service()
    
    document = (
        db.query(Document)
        .filter(Document.id == document_id, Document.user_id == user.id)
        .first()
    )
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    
    storage_key = document.storage_key  # Save before deletion
    
    try:
        # Audit log (before deletion)
        log_document_delete(db, document_id=document.id, user_id=user.id)

        # Delete from database first (can be rolled back)
        db.delete(document)
        db.commit()
        
        # Then delete from storage (cannot be rolled back, but document is already gone)
        storage.delete_file(storage_key)
        
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error deleting document: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete document",
        )

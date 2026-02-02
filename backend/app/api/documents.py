"""
Document API endpoints.
Handles upload, listing, and management of receipts/invoices.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.core.database import get_db
from app.core.security import get_current_user, CurrentUser
from app.models.user import User
from app.models.document import Document
from app.schemas.document import (
    DocumentCreate,
    DocumentUpdate,
    DocumentResponse,
    DocumentListResponse,
    UploadUrlRequest,
    UploadUrlResponse,
)
from app.services.storage import get_storage_service
from app.services.ocr import get_ocr_service

router = APIRouter()


def get_or_create_user(db: Session, current_user: CurrentUser) -> User:
    """Get existing user or create new one from auth data."""
    user = db.query(User).filter(User.clerk_id == current_user.user_id).first()
    if not user:
        user = User(
            clerk_id=current_user.user_id,
            email=current_user.email,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


@router.post("/upload-url", response_model=UploadUrlResponse)
async def get_upload_url(
    request: UploadUrlRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Get a presigned URL for uploading a document.
    Client should PUT the file to this URL, then call POST /documents.
    """
    storage = get_storage_service()
    storage_key = storage.generate_storage_key(current_user.user_id, request.filename)
    upload_url = storage.get_upload_url(storage_key, request.content_type)
    
    return UploadUrlResponse(
        upload_url=upload_url,
        storage_key=storage_key,
        expires_in=900,
    )


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def create_document(
    doc_create: DocumentCreate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Create a document record and trigger OCR processing.
    Call this after successfully uploading the file.
    """
    user = get_or_create_user(db, current_user)
    storage = get_storage_service()
    ocr = get_ocr_service()
    
    # Create document record
    document = Document(
        user_id=user.id,
        storage_key=doc_create.storage_key,
        original_filename=doc_create.original_filename,
        mime_type=doc_create.mime_type,
        file_size=doc_create.file_size,
        status="processing",
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    
    # Get file content for OCR
    file_content = None
    if storage.mock_mode:
        file_content = storage.get_file_mock(doc_create.storage_key)
    
    # Process OCR (synchronous for V0)
    if file_content or storage.mock_mode:
        try:
            # In mock mode, we don't need actual file content
            ocr_result = await ocr.process_document(
                file_content or b"mock_content",
                doc_create.mime_type
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
            
            if ocr_result.error:
                document.status = "failed"
            elif ocr_result.needs_review:
                document.status = "needs_review"
            else:
                document.status = "ready"
                
        except Exception as e:
            document.status = "failed"
            document.ocr_raw_response = str(e)
    else:
        # No file content available, mark as pending
        document.status = "pending"
    
    db.commit()
    db.refresh(document)
    
    # Generate file URL
    file_url = storage.get_download_url(document.storage_key)
    
    return DocumentResponse(
        **document.__dict__,
        period_tag=document.period_tag,
        quarter_tag=document.quarter_tag,
        file_url=file_url,
    )


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: Optional[str] = Query(None, alias="status"),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    List all documents for the current user.
    Supports pagination and status filtering.
    """
    user = get_or_create_user(db, current_user)
    storage = get_storage_service()
    
    # Build query
    query = db.query(Document).filter(Document.user_id == user.id)
    
    if status_filter:
        query = query.filter(Document.status == status_filter)
    
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
        doc_responses.append(DocumentResponse(
            **doc.__dict__,
            period_tag=doc.period_tag,
            quarter_tag=doc.quarter_tag,
            file_url=file_url,
        ))
    
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
    
    return DocumentResponse(
        **document.__dict__,
        period_tag=document.period_tag,
        quarter_tag=document.quarter_tag,
        file_url=file_url,
    )


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
    
    # Update fields
    update_data = doc_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(document, field, value)
    
    db.commit()
    db.refresh(document)
    
    file_url = storage.get_download_url(document.storage_key)
    
    return DocumentResponse(
        **document.__dict__,
        period_tag=document.period_tag,
        quarter_tag=document.quarter_tag,
        file_url=file_url,
    )


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
    
    # Delete from storage
    storage.delete_file(document.storage_key)
    
    # Delete from database
    db.delete(document)
    db.commit()

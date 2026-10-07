"""
File serving endpoints for mock mode.
In production, files are served directly from R2 via presigned URLs.
"""

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse, Response
from app.core.rate_limit import RATE_LIMITS, limiter
from app.services.storage import MAX_FILE_SIZE, get_storage_service

router = APIRouter()


@router.get("/{storage_key:path}")
async def get_file(
    storage_key: str,
):
    """
    Serve files from mock storage.
    Only used in development mode.
    """
    storage = get_storage_service()
    
    if not storage.mock_mode:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File serving only available in mock mode",
        )
    
    file_path = storage.get_file_path_mock(storage_key)
    
    if not file_path or not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        )
    
    # Determine content type
    suffix = file_path.suffix.lower()
    content_types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".pdf": "application/pdf",
        ".heic": "image/heic",
    }
    content_type = content_types.get(suffix, "application/octet-stream")
    
    return FileResponse(
        path=file_path,
        media_type=content_type,
        filename=file_path.name,
    )


@router.put("/mock-upload/{storage_key:path}")
@limiter.limit(RATE_LIMITS["upload"])
async def mock_upload(
    request: Request,
    storage_key: str,
):
    """
    Handle mock file uploads.
    This endpoint simulates R2 presigned URL uploads for development.
    """
    storage = get_storage_service()
    
    if not storage.mock_mode:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mock upload only available in mock mode",
        )
    
    # Check Content-Length header first (quick reject for large files)
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_FILE_SIZE:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"File size exceeds maximum allowed size of {MAX_FILE_SIZE // (1024 * 1024)}MB",
                )
        except ValueError:
            pass  # Invalid content-length header, will check actual content size
    
    # Read file content from request body
    content = await request.body()
    
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No file content provided",
        )
    
    # Validate actual file size
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File size exceeds maximum allowed size of {MAX_FILE_SIZE // (1024 * 1024)}MB",
        )
    
    # Save to mock storage (storage key is validated inside this function)
    try:
        storage.save_file_mock(storage_key, content)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    return Response(status_code=status.HTTP_200_OK)

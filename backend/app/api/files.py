"""
File serving endpoints for mock mode.
In production, files are served directly from R2 via presigned URLs.
"""

from pathlib import Path
from fastapi import APIRouter, HTTPException, status, Request, Depends
from fastapi.responses import FileResponse, Response
from app.services.storage import get_storage_service
from app.core.security import get_current_user, CurrentUser

router = APIRouter()


@router.get("/{storage_key:path}")
async def get_file(
    storage_key: str,
    current_user: CurrentUser = Depends(get_current_user),
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
async def mock_upload(
    storage_key: str,
    request: Request,
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
    
    # Read file content from request body
    content = await request.body()
    
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No file content provided",
        )
    
    # Save to mock storage
    storage.save_file_mock(storage_key, content)
    
    return Response(status_code=status.HTTP_200_OK)

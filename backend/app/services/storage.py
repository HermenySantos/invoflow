"""
Storage service for Cloudflare R2.
Includes mock mode for development without R2 credentials.
"""

import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional
from app.core.config import get_settings

settings = get_settings()

# Local storage directory for mock mode
MOCK_STORAGE_DIR = Path(__file__).parent.parent.parent / "mock_storage"


class StorageService:
    """
    Handles file storage operations.
    Uses Cloudflare R2 in production, local filesystem in mock mode.
    """
    
    def __init__(self):
        self.mock_mode = settings.storage_mock_mode
        self.s3_client = None
        self.bucket_name = None
        
        if not self.mock_mode:
            # Initialize R2 client - requires boto3
            try:
                import boto3
                from botocore.config import Config
                self.s3_client = boto3.client(
                    "s3",
                    endpoint_url=f"https://{settings.r2_account_id}.r2.cloudflarestorage.com",
                    aws_access_key_id=settings.r2_access_key_id,
                    aws_secret_access_key=settings.r2_secret_access_key,
                    config=Config(signature_version="s3v4"),
                    region_name="auto",
                )
                self.bucket_name = settings.r2_bucket_name
            except ImportError:
                print("Warning: boto3 not installed. Falling back to mock mode.")
                self.mock_mode = True
        
        if self.mock_mode:
            # Mock mode - use local filesystem
            MOCK_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    
    def generate_storage_key(self, user_id: str, filename: str) -> str:
        """Generate a unique storage key for a file."""
        timestamp = datetime.utcnow().strftime("%Y/%m")
        unique_id = uuid.uuid4().hex[:8]
        safe_filename = "".join(c if c.isalnum() or c in ".-_" else "_" for c in filename)
        return f"{user_id}/{timestamp}/{unique_id}_{safe_filename}"
    
    def get_upload_url(self, storage_key: str, content_type: str, expires_in: int = 900) -> str:
        """
        Generate a presigned URL for uploading a file.
        In mock mode, returns a fake URL that the mock upload endpoint will handle.
        """
        if self.mock_mode:
            # Return a mock upload URL pointing to our API
            return f"http://localhost:8000/api/mock-upload/{storage_key}"
        
        # Generate presigned PUT URL for R2
        url = self.s3_client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": self.bucket_name,
                "Key": storage_key,
                "ContentType": content_type,
            },
            ExpiresIn=expires_in,
        )
        return url
    
    def get_download_url(self, storage_key: str, expires_in: int = 3600) -> str:
        """
        Generate a presigned URL for downloading a file.
        In mock mode, returns a URL to serve from local filesystem.
        """
        if self.mock_mode:
            return f"http://localhost:8000/api/files/{storage_key}"
        
        url = self.s3_client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": self.bucket_name,
                "Key": storage_key,
            },
            ExpiresIn=expires_in,
        )
        return url
    
    def save_file_mock(self, storage_key: str, content: bytes) -> str:
        """Save file to local filesystem in mock mode."""
        if not self.mock_mode:
            raise RuntimeError("save_file_mock called in non-mock mode")
        
        file_path = MOCK_STORAGE_DIR / storage_key
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(content)
        return str(file_path)
    
    def get_file_mock(self, storage_key: str) -> Optional[bytes]:
        """Get file from local filesystem in mock mode."""
        if not self.mock_mode:
            raise RuntimeError("get_file_mock called in non-mock mode")
        
        file_path = MOCK_STORAGE_DIR / storage_key
        if file_path.exists():
            return file_path.read_bytes()
        return None
    
    def get_file_path_mock(self, storage_key: str) -> Optional[Path]:
        """Get the local file path in mock mode."""
        if not self.mock_mode:
            return None
        
        file_path = MOCK_STORAGE_DIR / storage_key
        if file_path.exists():
            return file_path
        return None
    
    def delete_file(self, storage_key: str) -> bool:
        """Delete a file from storage."""
        if self.mock_mode:
            file_path = MOCK_STORAGE_DIR / storage_key
            if file_path.exists():
                file_path.unlink()
                return True
            return False
        
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=storage_key)
            return True
        except Exception:
            return False
    
    def file_exists(self, storage_key: str) -> bool:
        """Check if a file exists in storage."""
        if self.mock_mode:
            return (MOCK_STORAGE_DIR / storage_key).exists()
        
        try:
            self.s3_client.head_object(Bucket=self.bucket_name, Key=storage_key)
            return True
        except Exception:
            return False


# Singleton instance
_storage_service: Optional[StorageService] = None


def get_storage_service() -> StorageService:
    """Get the storage service singleton."""
    global _storage_service
    if _storage_service is None:
        _storage_service = StorageService()
    return _storage_service

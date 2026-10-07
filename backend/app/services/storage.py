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

MOCK_STORAGE_DIR = Path(__file__).parent.parent.parent / "mock_storage"

# Maximum file size (10MB)
MAX_FILE_SIZE = 10 * 1024 * 1024


def _validate_storage_key(storage_key: str, base_dir: Path) -> Path:
    """
    Validate storage key to prevent path traversal attacks.
    Returns the resolved file path if valid.
    Raises ValueError if the path would escape the base directory.
    """
    # Reject obviously malicious patterns
    if any(part.startswith("..") for part in Path(storage_key).parts) or storage_key.startswith("/"):
        raise ValueError("Invalid storage key: path traversal attempt detected")
    
    # Resolve the full path and ensure it's within base_dir
    file_path = (base_dir / storage_key).resolve()
    base_resolved = base_dir.resolve()
    
    # Check that resolved path starts with the base directory
    try:
        file_path.relative_to(base_resolved)
    except ValueError:
        raise ValueError("Invalid storage key: path traversal attempt detected")
    
    return file_path


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
            MOCK_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

    def generate_storage_key(self, user_id: str, filename: str) -> str:
        timestamp = datetime.utcnow().strftime("%Y/%m")
        unique_id = uuid.uuid4().hex[:8]
        safe_filename = "".join(c if c.isalnum() or c in ".-_" else "_" for c in filename)
        return f"{user_id}/{timestamp}/{unique_id}_{safe_filename}"

    def get_upload_url(self, storage_key: str, content_type: str, expires_in: int = 900) -> str:
        if self.mock_mode:
            # Relative URL so the Next.js rewrite (or same-origin API) can proxy it.
            return f"/api/files/mock-upload/{storage_key}"

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
        if self.mock_mode:
            return f"/api/files/{storage_key}"

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
        if not self.mock_mode:
            raise RuntimeError("save_file_mock called in non-mock mode")

        file_path = _validate_storage_key(storage_key, MOCK_STORAGE_DIR)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(content)
        return str(file_path)

    def get_file(self, storage_key: str) -> Optional[bytes]:
        if self.mock_mode:
            return self.get_file_mock(storage_key)
        if not self.s3_client:
            return None
        try:
            obj = self.s3_client.get_object(Bucket=self.bucket_name, Key=storage_key)
            return obj["Body"].read()
        except Exception:
            return None

    def get_file_mock(self, storage_key: str) -> Optional[bytes]:
        """Get file from local filesystem in mock mode."""
        if not self.mock_mode:
            raise RuntimeError("get_file_mock called in non-mock mode")

        try:
            file_path = _validate_storage_key(storage_key, MOCK_STORAGE_DIR)
            if file_path.exists():
                return file_path.read_bytes()
        except ValueError:
            return None
        return None

    def get_file_path_mock(self, storage_key: str) -> Optional[Path]:
        if not self.mock_mode:
            return None

        try:
            file_path = _validate_storage_key(storage_key, MOCK_STORAGE_DIR)
            if file_path.exists():
                return file_path
        except ValueError:
            return None
        return None

    def delete_file(self, storage_key: str) -> bool:
        if self.mock_mode:
            try:
                file_path = _validate_storage_key(storage_key, MOCK_STORAGE_DIR)
                if file_path.exists():
                    file_path.unlink()
                    return True
            except ValueError:
                return False
            return False

        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=storage_key)
            return True
        except Exception:
            return False

    def file_exists(self, storage_key: str) -> bool:
        if self.mock_mode:
            try:
                file_path = _validate_storage_key(storage_key, MOCK_STORAGE_DIR)
                return file_path.exists()
            except ValueError:
                return False

        try:
            self.s3_client.head_object(Bucket=self.bucket_name, Key=storage_key)
            return True
        except Exception:
            return False


_storage_service: Optional[StorageService] = None


def get_storage_service() -> StorageService:
    global _storage_service
    if _storage_service is None:
        _storage_service = StorageService()
    return _storage_service

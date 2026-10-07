"""
Tests for security features including path traversal protection.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from app.services.storage import get_storage_service, _validate_storage_key, MOCK_STORAGE_DIR


class TestPathTraversalProtection:
    """Tests for path traversal attack prevention."""

    def test_valid_storage_key(self):
        """Test that valid storage keys are accepted."""
        valid_keys = [
            "user123/2024/01/abc123_file.jpg",
            "user-456/2024/02/test.pdf",
            "simple_file.png",
        ]
        for key in valid_keys:
            # Should not raise
            result = _validate_storage_key(key, MOCK_STORAGE_DIR)
            assert result is not None

    def test_path_traversal_with_double_dots(self):
        """Test that path traversal with .. is blocked."""
        malicious_keys = [
            "../../../etc/passwd",
            "user123/../../../etc/passwd",
            "user123/2024/../../../secret",
            "..%2f..%2f..%2fetc/passwd",  # URL encoded
        ]
        for key in malicious_keys:
            with pytest.raises(ValueError) as exc_info:
                _validate_storage_key(key, MOCK_STORAGE_DIR)
            assert "path traversal" in str(exc_info.value).lower()

    def test_absolute_path_blocked(self):
        """Test that absolute paths are blocked."""
        with pytest.raises(ValueError) as exc_info:
            _validate_storage_key("/etc/passwd", MOCK_STORAGE_DIR)
        assert "path traversal" in str(exc_info.value).lower()


class TestSecurityHeaders:
    """Tests for security headers middleware."""

    def test_security_headers_present(self, client: TestClient):
        """Test that security headers are added to responses."""
        response = client.get("/health")
        assert response.status_code == 200
        
        # Check security headers
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "DENY"
        assert response.headers.get("X-XSS-Protection") == "1; mode=block"
        assert "strict-origin" in response.headers.get("Referrer-Policy", "").lower()


class TestAuthentication:
    """Tests for authentication handling."""

    def test_unauthenticated_request(self, client: TestClient):
        """Test that requests without auth headers use mock user in mock mode."""
        # In mock mode, requests without auth headers should still work
        response = client.get("/api/documents")
        assert response.status_code == 200

    def test_custom_mock_user(self, client: TestClient):
        """Test that custom mock user headers are respected."""
        headers = {
            "X-Mock-User-Id": "custom-user-123",
            "X-Mock-User-Email": "custom@example.com",
        }
        
        # Create a document with custom user
        upload_response = client.post(
            "/api/documents/upload-url",
            headers=headers,
            json={"filename": "test.jpg", "content_type": "image/jpeg"},
        )
        assert upload_response.status_code == 200
        storage_key = upload_response.json()["storage_key"]
        
        # Verify the user ID is in the storage key
        assert "custom-user-123" in storage_key


class TestFileSizeValidation:
    """Tests for file size validation."""

    def test_mock_upload_file_too_large_header(self, client: TestClient):
        """Test that Content-Length header is checked for large files."""
        response = client.put(
            get_storage_service().get_upload_url("test/key", "image/jpeg"),
            content=b"small content",
            headers={"Content-Length": str(100 * 1024 * 1024)},  # 100MB
        )
        assert response.status_code == 413

    def test_mock_upload_file_within_limit(self, client: TestClient):
        """Test that files within size limit are accepted."""
        response = client.put(
            get_storage_service().get_upload_url(f"test/{uuid.uuid4().hex}.jpg", "image/jpeg"),
            content=b"x" * 1024,  # 1KB
        )
        assert response.status_code == 200


def test_double_dot_inside_filename_is_allowed():
    """A filename like recibo..jpg is not traversal."""
    path = _validate_storage_key("user123/2026/10/ab12cd34_recibo..jpg", MOCK_STORAGE_DIR)
    assert path.name == "ab12cd34_recibo..jpg"

"""
Tests for field confidence parsing and review functionality.
"""

import json
import uuid
import pytest
from fastapi.testclient import TestClient

from app.services.storage import get_storage_service


def unique_user_headers():
    """Generate unique user headers to avoid rate limiting."""
    user_id = f"test-user-{uuid.uuid4().hex[:8]}"
    return {
        "X-Mock-User-Id": user_id,
        "X-Mock-User-Email": f"{user_id}@example.com",
    }


class TestFieldConfidenceParsing:
    """Tests for parsing field confidence from OCR responses."""

    def test_mock_ocr_generates_field_confidence(self, client: TestClient):
        """Mock OCR should generate field confidence values."""
        headers = unique_user_headers()
        user_id = headers["X-Mock-User-Id"]
        
        # First upload a mock file
        client.put(
            get_storage_service().get_upload_url(f"{user_id}/test-confidence.jpg", "image/jpeg"),
            content=b"fake image content",
            headers={"Content-Type": "image/jpeg"},
        )
        
        # Create document (triggers mock OCR)
        response = client.post(
            "/api/documents",
            json={
                "storage_key": f"{user_id}/test-confidence.jpg",
                "original_filename": "test-confidence.jpg",
                "mime_type": "image/jpeg",
                "file_size": 1024,
            },
            headers=headers,
        )
        
        assert response.status_code == 201
        data = client.get(f"/api/documents/{response.json()['id']}", headers=headers).json()
        
        # Should have field_confidence
        assert "field_confidence" in data
        fc = data["field_confidence"]
        
        # Should have some confidence values (mock generates random values)
        assert fc is not None or data["status"] == "failed"

    def test_field_confidence_returned_in_get_document(self, client: TestClient):
        """Field confidence should be included when getting a document."""
        headers = unique_user_headers()
        user_id = headers["X-Mock-User-Id"]
        
        # Create a document first
        client.put(
            get_storage_service().get_upload_url(f"{user_id}/test-fc-get.jpg", "image/jpeg"),
            content=b"fake image content",
            headers={"Content-Type": "image/jpeg"},
        )
        
        create_response = client.post(
            "/api/documents",
            json={
                "storage_key": f"{user_id}/test-fc-get.jpg",
                "original_filename": "test-fc-get.jpg",
                "mime_type": "image/jpeg",
            },
            headers=headers,
        )
        
        doc_id = create_response.json()["id"]
        
        # Get the document
        get_response = client.get(f"/api/documents/{doc_id}", headers=headers)
        
        assert get_response.status_code == 200
        assert "field_confidence" in get_response.json()


class TestReviewNotes:
    """Tests for review notes functionality."""

    def test_can_add_review_notes(self, client: TestClient):
        """Should be able to add review notes to a document."""
        headers = unique_user_headers()
        user_id = headers["X-Mock-User-Id"]
        
        # Create a document
        client.put(
            get_storage_service().get_upload_url(f"{user_id}/test-notes.jpg", "image/jpeg"),
            content=b"fake image content",
            headers={"Content-Type": "image/jpeg"},
        )
        
        create_response = client.post(
            "/api/documents",
            json={
                "storage_key": f"{user_id}/test-notes.jpg",
                "original_filename": "test-notes.jpg",
                "mime_type": "image/jpeg",
            },
            headers=headers,
        )
        
        doc_id = create_response.json()["id"]
        
        # Update with review notes
        update_response = client.patch(
            f"/api/documents/{doc_id}",
            json={
                "review_notes": "Please verify the VAT calculation",
            },
            headers=headers,
        )
        
        assert update_response.status_code == 200
        assert update_response.json()["review_notes"] == "Please verify the VAT calculation"

    def test_review_notes_persists(self, client: TestClient):
        """Review notes should persist when retrieving document."""
        headers = unique_user_headers()
        user_id = headers["X-Mock-User-Id"]
        
        # Create a document
        client.put(
            get_storage_service().get_upload_url(f"{user_id}/test-notes-persist.jpg", "image/jpeg"),
            content=b"fake image content",
            headers={"Content-Type": "image/jpeg"},
        )
        
        create_response = client.post(
            "/api/documents",
            json={
                "storage_key": f"{user_id}/test-notes-persist.jpg",
                "original_filename": "test-notes-persist.jpg",
                "mime_type": "image/jpeg",
            },
            headers=headers,
        )
        
        doc_id = create_response.json()["id"]
        
        # Add notes
        client.patch(
            f"/api/documents/{doc_id}",
            json={"review_notes": "Test note"},
            headers=headers,
        )
        
        # Retrieve and verify
        get_response = client.get(f"/api/documents/{doc_id}", headers=headers)
        assert get_response.json()["review_notes"] == "Test note"


class TestAccountantReviewStatus:
    """Tests for accountant_review status."""

    def test_can_set_accountant_review_status(self, client: TestClient):
        """Should be able to set status to accountant_review."""
        headers = unique_user_headers()
        user_id = headers["X-Mock-User-Id"]
        
        # Create a document
        client.put(
            get_storage_service().get_upload_url(f"{user_id}/test-accountant.jpg", "image/jpeg"),
            content=b"fake image content",
            headers={"Content-Type": "image/jpeg"},
        )
        
        create_response = client.post(
            "/api/documents",
            json={
                "storage_key": f"{user_id}/test-accountant.jpg",
                "original_filename": "test-accountant.jpg",
                "mime_type": "image/jpeg",
            },
            headers=headers,
        )
        
        doc_id = create_response.json()["id"]
        
        # Set to accountant_review
        update_response = client.patch(
            f"/api/documents/{doc_id}",
            json={
                "status": "accountant_review",
                "review_notes": "Need accountant to verify",
            },
            headers=headers,
        )
        
        assert update_response.status_code == 200
        assert update_response.json()["status"] == "accountant_review"

    def test_invalid_status_rejected(self, client: TestClient):
        """Invalid status values should be rejected."""
        headers = unique_user_headers()
        user_id = headers["X-Mock-User-Id"]
        
        # Create a document
        client.put(
            get_storage_service().get_upload_url(f"{user_id}/test-invalid-status.jpg", "image/jpeg"),
            content=b"fake image content",
            headers={"Content-Type": "image/jpeg"},
        )
        
        create_response = client.post(
            "/api/documents",
            json={
                "storage_key": f"{user_id}/test-invalid-status.jpg",
                "original_filename": "test-invalid-status.jpg",
                "mime_type": "image/jpeg",
            },
            headers=headers,
        )
        
        doc_id = create_response.json()["id"]
        
        # Try to set invalid status
        update_response = client.patch(
            f"/api/documents/{doc_id}",
            json={"status": "invalid_status"},
            headers=headers,
        )
        
        assert update_response.status_code == 422  # Validation error

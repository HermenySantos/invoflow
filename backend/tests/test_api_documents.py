"""
Tests for document API endpoints.
"""

import pytest
from fastapi.testclient import TestClient


class TestDocumentAPI:
    """Tests for document CRUD operations."""

    def test_list_documents_empty(self, client: TestClient, mock_user_headers: dict):
        """Test listing documents when none exist."""
        response = client.get("/api/documents", headers=mock_user_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["documents"] == []
        assert data["total"] == 0
        assert data["page"] == 1
        assert data["has_more"] is False

    def test_get_upload_url(self, client: TestClient, mock_user_headers: dict):
        """Test getting a presigned upload URL."""
        response = client.post(
            "/api/documents/upload-url",
            headers=mock_user_headers,
            json={
                "filename": "test-receipt.jpg",
                "content_type": "image/jpeg",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "upload_url" in data
        assert "storage_key" in data
        assert data["expires_in"] == 900
        assert "test-user-001" in data["storage_key"]

    def test_create_document(self, client: TestClient, mock_user_headers: dict):
        """Test creating a document record."""
        # First get upload URL
        upload_response = client.post(
            "/api/documents/upload-url",
            headers=mock_user_headers,
            json={
                "filename": "test-receipt.jpg",
                "content_type": "image/jpeg",
            },
        )
        storage_key = upload_response.json()["storage_key"]

        # Create document
        response = client.post(
            "/api/documents",
            headers=mock_user_headers,
            json={
                "storage_key": storage_key,
                "original_filename": "test-receipt.jpg",
                "mime_type": "image/jpeg",
                "file_size": 1024,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["original_filename"] == "test-receipt.jpg"
        assert data["mime_type"] == "image/jpeg"
        assert data["file_size"] == 1024
        # The upload returns before OCR; reading happens in the background.
        assert data["status"] == "processing"
        read = client.get(f"/api/documents/{data['id']}", headers=mock_user_headers).json()
        assert read["status"] in ["ready", "needs_review", "failed"]

    def test_get_document(self, client: TestClient, mock_user_headers: dict):
        """Test getting a single document."""
        # Create a document first
        upload_response = client.post(
            "/api/documents/upload-url",
            headers=mock_user_headers,
            json={"filename": "test.jpg", "content_type": "image/jpeg"},
        )
        storage_key = upload_response.json()["storage_key"]

        create_response = client.post(
            "/api/documents",
            headers=mock_user_headers,
            json={
                "storage_key": storage_key,
                "original_filename": "test.jpg",
                "mime_type": "image/jpeg",
                "file_size": 1024,
            },
        )
        doc_id = create_response.json()["id"]

        # Get the document
        response = client.get(f"/api/documents/{doc_id}", headers=mock_user_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == doc_id
        assert data["original_filename"] == "test.jpg"

    def test_get_document_not_found(self, client: TestClient, mock_user_headers: dict):
        """Test getting a non-existent document."""
        response = client.get(
            "/api/documents/nonexistent-id",
            headers=mock_user_headers,
        )
        assert response.status_code == 404

    def test_update_document(self, client: TestClient, mock_user_headers: dict):
        """Test updating a document."""
        # Create a document
        upload_response = client.post(
            "/api/documents/upload-url",
            headers=mock_user_headers,
            json={"filename": "test.jpg", "content_type": "image/jpeg"},
        )
        storage_key = upload_response.json()["storage_key"]

        create_response = client.post(
            "/api/documents",
            headers=mock_user_headers,
            json={
                "storage_key": storage_key,
                "original_filename": "test.jpg",
                "mime_type": "image/jpeg",
                "file_size": 1024,
            },
        )
        doc_id = create_response.json()["id"]

        # Update the document
        response = client.patch(
            f"/api/documents/{doc_id}",
            headers=mock_user_headers,
            json={
                "vendor_name": "Updated Vendor",
                "gross_amount": "100.50",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["vendor_name"] == "Updated Vendor"
        assert float(data["gross_amount"]) == 100.50

    def test_delete_document(self, client: TestClient, mock_user_headers: dict):
        """Test deleting a document."""
        # Create a document
        upload_response = client.post(
            "/api/documents/upload-url",
            headers=mock_user_headers,
            json={"filename": "test.jpg", "content_type": "image/jpeg"},
        )
        storage_key = upload_response.json()["storage_key"]

        create_response = client.post(
            "/api/documents",
            headers=mock_user_headers,
            json={
                "storage_key": storage_key,
                "original_filename": "test.jpg",
                "mime_type": "image/jpeg",
                "file_size": 1024,
            },
        )
        doc_id = create_response.json()["id"]

        # Delete the document
        response = client.delete(f"/api/documents/{doc_id}", headers=mock_user_headers)
        assert response.status_code == 204

        # Verify it's deleted
        get_response = client.get(
            f"/api/documents/{doc_id}",
            headers=mock_user_headers,
        )
        assert get_response.status_code == 404

    def test_file_size_limit(self, client: TestClient, mock_user_headers: dict):
        """Test file size validation."""
        response = client.post(
            "/api/documents",
            headers=mock_user_headers,
            json={
                "storage_key": "test/key",
                "original_filename": "huge-file.jpg",
                "mime_type": "image/jpeg",
                "file_size": 100 * 1024 * 1024,  # 100MB - exceeds limit
            },
        )
        assert response.status_code == 413

    def test_list_documents_pagination(self, client: TestClient, mock_user_headers: dict):
        """Test document listing with pagination."""
        # Create multiple documents
        for i in range(3):
            upload_response = client.post(
                "/api/documents/upload-url",
                headers=mock_user_headers,
                json={"filename": f"test{i}.jpg", "content_type": "image/jpeg"},
            )
            storage_key = upload_response.json()["storage_key"]
            client.post(
                "/api/documents",
                headers=mock_user_headers,
                json={
                    "storage_key": storage_key,
                    "original_filename": f"test{i}.jpg",
                    "mime_type": "image/jpeg",
                    "file_size": 1024,
                },
            )

        # Test pagination
        response = client.get(
            "/api/documents?page=1&page_size=2",
            headers=mock_user_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["documents"]) == 2
        assert data["total"] == 3
        assert data["has_more"] is True

        # Get second page
        response2 = client.get(
            "/api/documents?page=2&page_size=2",
            headers=mock_user_headers,
        )
        assert response2.status_code == 200
        data2 = response2.json()
        assert len(data2["documents"]) == 1
        assert data2["has_more"] is False

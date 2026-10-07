"""
Tests that one user cannot reach another user's documents or files.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core import startup
from app.core.config import get_settings
from app.services.storage import get_storage_service, sign_mock_url


def user_headers():
    return {"X-Mock-User-Id": f"test-user-{uuid.uuid4().hex[:8]}"}


def upload_document(client: TestClient, headers: dict) -> dict:
    key = f"{headers['X-Mock-User-Id']}/2026/10/ab12cd34_recibo.jpg"
    client.put(get_storage_service().get_upload_url(key, "image/jpeg"), content=b"fake image")
    response = client.post(
        "/api/documents",
        json={"storage_key": key, "original_filename": "recibo.jpg", "file_size": 10, "mime_type": "image/jpeg"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_audit_trail_is_only_visible_to_the_owner(client: TestClient):
    owner, other = user_headers(), user_headers()
    document = upload_document(client, owner)

    assert client.get(f"/api/audit/documents/{document['id']}", headers=owner).status_code == 200
    assert client.get(f"/api/audit/documents/{document['id']}", headers=other).status_code == 404


def test_cannot_register_another_users_storage_key(client: TestClient):
    owner, other = user_headers(), user_headers()
    stolen_key = f"{owner['X-Mock-User-Id']}/2026/10/ab12cd34_recibo.jpg"

    response = client.post(
        "/api/documents",
        json={"storage_key": stolen_key, "original_filename": "recibo.jpg", "file_size": 10, "mime_type": "image/jpeg"},
        headers=other,
    )
    assert response.status_code == 403


@pytest.mark.parametrize("path", ["/api/files/u1/2026/10/a_r.jpg", "/api/files/mock-upload/u1/2026/10/a_r.jpg"])
def test_mock_file_routes_reject_unsigned_links(client: TestClient, path: str):
    response = client.put(path, content=b"x") if "mock-upload" in path else client.get(path)
    assert response.status_code == 403


def test_mock_file_routes_reject_expired_links(client: TestClient):
    expired = sign_mock_url("/api/files/", "u1/2026/10/a_r.jpg", expires_in=-10)
    assert client.get(expired).status_code == 403


def test_signed_download_link_serves_the_file(client: TestClient):
    storage = get_storage_service()
    key = "u1/2026/10/ab12cd34_signed.jpg"
    client.put(storage.get_upload_url(key, "image/jpeg"), content=b"fake image")
    assert client.get(storage.get_download_url(key)).status_code == 200


@pytest.mark.parametrize("flag", ["auth_mock_mode", "storage_mock_mode"])
def test_mock_modes_refused_outside_development(monkeypatch, flag):
    settings = get_settings()
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "auth_mock_mode", flag == "auth_mock_mode")
    monkeypatch.setattr(settings, "storage_mock_mode", flag == "storage_mock_mode")
    monkeypatch.setattr(settings, "clerk_secret_key", "sk_test_placeholder")
    monkeypatch.setattr(settings, "r2_account_id", "a")
    monkeypatch.setattr(settings, "r2_access_key_id", "b")
    monkeypatch.setattr(settings, "r2_secret_access_key", "c")

    with pytest.raises(startup.ConfigurationError, match=flag.upper()):
        startup.validate_configuration()

"""Guards from the QA gate: mock OCR, tesseract, the e-Fatura flag, uploads."""

import uuid

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.startup import ConfigurationError, validate_configuration
from app.services.ocr import OCRService
from app.services.uploads import allowed_upload


def test_mock_ocr_is_never_confirmed():
    result = OCRService()._generate_mock_result("application/pdf")
    assert result.needs_review is True
    assert result.backend == "mock"
    assert '"mock": true' in (result.raw_response or "")


def test_tesseract_without_a_binary_refuses_startup(monkeypatch):
    monkeypatch.setattr(get_settings(), "ocr_backend", "tesseract")
    monkeypatch.setattr("app.services.ocr.tesseract_available", lambda: False)
    with __import__("pytest").raises(ConfigurationError, match="tesseract binary"):
        validate_configuration()


def test_health_is_degraded_when_tesseract_is_missing(client: TestClient, monkeypatch):
    monkeypatch.setattr(get_settings(), "ocr_backend", "tesseract")
    monkeypatch.setattr("app.services.ocr.tesseract_available", lambda: False)
    health_response = client.get("/health")
    assert health_response.status_code == 503
    health = health_response.json()
    assert health["status"] == "degraded"
    assert health["ocr_backend"] == "tesseract"
    assert health["tesseract"] is False


def test_empty_efatura_flag_is_off(monkeypatch):
    monkeypatch.setenv("EFATURA_PULL_ENABLED", "")
    get_settings.cache_clear()
    try:
        assert get_settings().efatura_pull_enabled is False
    finally:
        get_settings.cache_clear()


def test_app_debug_defaults_to_false(monkeypatch):
    monkeypatch.delenv("APP_DEBUG", raising=False)
    get_settings.cache_clear()
    try:
        assert get_settings().app_debug is False
    finally:
        get_settings.cache_clear()


def test_efatura_is_hidden_when_the_flag_is_off(client: TestClient, monkeypatch):
    monkeypatch.delenv("EFATURA_PULL_ENABLED", raising=False)
    get_settings.cache_clear()
    assert client.get("/api/efatura/pull").status_code == 404
    assert client.post("/api/efatura/pull", json={}).status_code == 404
    assert client.post("/api/efatura/pull/").status_code == 404
    paths = client.get("/openapi.json").json()["paths"]
    assert not any("efatura" in path for path in paths)


def test_exe_disguised_as_pdf_is_rejected(client: TestClient):
    headers = {"X-Mock-User-Id": f"type-{uuid.uuid4().hex[:8]}"}
    from app.services.storage import get_storage_service

    key = f"{headers['X-Mock-User-Id']}/2026/01/{uuid.uuid4().hex[:8]}_evil.pdf"
    payload = b"MZ\x90\x00" + b"\x00" * 32
    assert allowed_upload(payload) is False
    client.put(get_storage_service().get_upload_url(key, "application/pdf"), content=payload)
    response = client.post(
        "/api/documents",
        json={
            "storage_key": key,
            "original_filename": "evil.pdf",
            "mime_type": "application/pdf",
            "file_size": len(payload),
        },
        headers=headers,
    )
    assert response.status_code == 415


def test_polyglot_uploads_are_rejected():
    assert allowed_upload(b"BM" + b"MZ" + b"\x00" * 64) is False
    assert allowed_upload(b"%PDF-1.1\n" + b"MZ\x90\x00" + b"\x00" * 32) is False
    assert allowed_upload(b"GIF89a" + b"<svg xmlns='http://www.w3.org/2000/svg'></svg>") is False
    assert allowed_upload(b"\xff\xd8\xff\xd9") is True


def test_missing_or_forged_storage_key_creates_nothing(client: TestClient):
    headers = {"X-Mock-User-Id": f"key-{uuid.uuid4().hex[:8]}"}
    missing = client.post(
        "/api/documents",
        json={
            "storage_key": f"{headers['X-Mock-User-Id']}/2026/01/never-uploaded.png",
            "original_filename": "never.png",
            "mime_type": "image/png",
            "file_size": 4,
        },
        headers=headers,
    )
    assert missing.status_code in {400, 404}
    dotted = client.post(
        "/api/documents",
        json={
            "storage_key": f"{headers['X-Mock-User-Id']}/../secrets.png",
            "original_filename": "secrets.png",
            "mime_type": "image/png",
            "file_size": 4,
        },
        headers=headers,
    )
    assert dotted.status_code in {400, 404}
    assert client.get("/api/documents", headers=headers).json()["documents"] == []


def test_mock_user_id_with_a_path_separator_is_rejected(client: TestClient):
    response = client.get("/api/documents", headers={"X-Mock-User-Id": "attacker/../../etc"})
    assert response.status_code == 400

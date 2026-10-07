"""
Deleting a receipt hides it but keeps the row and the original file.
"""

import uuid

from fastapi.testclient import TestClient

from app.models.document import Document
from app.services.storage import get_storage_service


def test_delete_hides_the_receipt_but_keeps_the_original(client: TestClient, db):
    headers = {"X-Mock-User-Id": f"test-user-{uuid.uuid4().hex[:8]}"}
    storage = get_storage_service()
    key = f"{headers['X-Mock-User-Id']}/2026/09/{uuid.uuid4().hex[:8]}_recibo.jpg"
    client.put(storage.get_upload_url(key, "image/jpeg"), content=b"original")
    created = client.post(
        "/api/documents",
        json={"storage_key": key, "original_filename": "recibo.jpg", "file_size": 8, "mime_type": "image/jpeg"},
        headers=headers,
    ).json()

    assert client.delete(f"/api/documents/{created['id']}", headers=headers).status_code == 204

    assert client.get(f"/api/documents/{created['id']}", headers=headers).status_code == 404
    assert created["id"] not in [d["id"] for d in client.get("/api/documents", headers=headers).json()["documents"]]
    assert db.get(Document, created["id"]).deleted_at is not None
    assert storage.get_file(key) == b"original"


def test_an_original_cannot_be_overwritten(client: TestClient):
    upload_url = get_storage_service().get_upload_url(f"u1/2026/09/{uuid.uuid4().hex}.jpg", "image/jpeg")
    assert client.put(upload_url, content=b"first").status_code == 200
    assert client.put(upload_url, content=b"second").status_code == 409


def test_local_database_gets_new_nullable_columns(tmp_path):
    from sqlalchemy import create_engine, inspect, text

    from app.core.database import add_missing_nullable_columns

    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE documents (id VARCHAR(36) PRIMARY KEY)"))

    added = add_missing_nullable_columns(engine)

    assert "documents.deleted_at" in added
    assert "deleted_at" in {c["name"] for c in inspect(engine).get_columns("documents")}

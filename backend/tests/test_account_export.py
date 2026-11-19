"""GET /api/account/export: the whole account, and only the caller's account."""

import csv
import io
import json
import re
import uuid
import zipfile

import pytest
from PIL import Image
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.document import Document
from app.models.user import User
from app.services.storage import get_storage_service

BASE_ENTRIES = {
    "LEIA-ME.txt",
    "conta.json",
    "documentos.json",
    "documentos.csv",
    "iva_vendas.json",
    "iva_vendas.csv",
}


def _headers(name: str) -> dict:
    return {"X-Mock-User-Id": f"exp-{name}-{uuid.uuid4().hex[:8]}", "X-Mock-User-Email": f"{name}@example.com"}


def _image(color: tuple[int, int, int]) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (8, 8), color).save(out, format="JPEG")
    return out.getvalue()


def _receipt(client: TestClient, headers: dict, color: tuple[int, int, int], vendor: str) -> dict:
    content = _image(color)
    filename = f"recibo-{uuid.uuid4().hex[:6]}.jpg"
    issued = client.post(
        "/api/documents/upload-url", json={"filename": filename, "content_type": "image/jpeg"}, headers=headers
    )
    assert issued.status_code == 200, issued.text
    key = issued.json()["storage_key"]
    assert client.put(issued.json()["upload_url"], content=content, headers=headers).status_code == 200
    created = client.post(
        "/api/documents",
        json={"storage_key": key, "original_filename": filename, "file_size": len(content), "mime_type": "image/jpeg"},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    doc_id = created.json()["id"]
    edited = client.patch(f"/api/documents/{doc_id}", json={"vendor_name": vendor}, headers=headers)
    assert edited.status_code == 200, edited.text
    return {"id": doc_id, "key": key, "filename": filename, "content": get_storage_service().get_file(key)}


def _vat(client: TestClient, headers: dict, quarter: int, amount: str, notes: str) -> str:
    r = client.post(
        "/api/vat-sales",
        json={"period_type": "quarter", "year": 2026, "period_value": quarter, "vat_amount": amount, "notes": notes},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _export(client: TestClient, headers: dict, **params) -> zipfile.ZipFile:
    r = client.get("/api/account/export", headers=headers, params=params)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/zip"
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["content-disposition"].startswith('attachment; filename="Invoflow_meus_dados_')
    return zipfile.ZipFile(io.BytesIO(r.content))


def _csv_rows(zf: zipfile.ZipFile, name: str) -> list[list[str]]:
    text = zf.read(name).decode("utf-8")
    assert text.startswith("\ufeff")
    return list(csv.reader(io.StringIO(text[1:]), delimiter=";"))


def _all_text(zf: zipfile.ZipFile) -> str:
    return "\n".join([*zf.namelist(), *(zf.read(n).decode("latin-1") for n in zf.namelist())])


def test_owner_gets_every_document_vat_entry_and_receipt_file(client: TestClient):
    a = _headers("a")
    kept = _receipt(client, a, (200, 10, 10), "Papelaria Lisboa")
    gone = _receipt(client, a, (10, 200, 10), "Cafe Porto")
    assert client.delete(f"/api/documents/{gone['id']}", headers=a).status_code in (200, 204)
    vat_ids = {_vat(client, a, 1, "120.50", "primeiro"), _vat(client, a, 2, "80.00", "=SUM(A1)")}

    zf = _export(client, a)

    docs = {d["id"]: d for d in json.loads(zf.read("documentos.json"))}
    assert set(docs) == {kept["id"], gone["id"]}
    assert docs[kept["id"]]["vendor_name"] == "Papelaria Lisboa"
    assert docs[kept["id"]]["original_filename"] == kept["filename"]
    assert docs[kept["id"]]["deleted_at"] is None
    assert docs[gone["id"]]["deleted_at"] is not None
    assert all("user_id" not in d and "storage_key" not in d for d in docs.values())
    for receipt in (kept, gone):
        path = docs[receipt["id"]]["ficheiro"]
        assert path == f"ficheiros/{receipt['id']}.jpg"
        assert zf.read(path) == receipt["content"]
    assert {n for n in zf.namelist() if n.startswith("ficheiros/")} == {f"ficheiros/{kept['id']}.jpg", f"ficheiros/{gone['id']}.jpg"}

    vat = json.loads(zf.read("iva_vendas.json"))
    assert {v["id"] for v in vat} == vat_ids
    assert {v["vat_amount"] for v in vat} == {"120.50", "80.00"}

    rows = _csv_rows(zf, "documentos.csv")
    assert rows[0][:3] == ["ID", "Data", "Fornecedor"]
    assert {r[0] for r in rows[1:]} == {kept["id"], gone["id"]}
    vat_rows = _csv_rows(zf, "iva_vendas.csv")
    assert sorted(r[4] for r in vat_rows[1:]) == ["120,50", "80,00"]
    assert "'=SUM(A1)" in [r[5] for r in vat_rows[1:]]

    account = json.loads(zf.read("conta.json"))
    assert account["email"] == "a@example.com"
    assert (account["documentos"], account["ficheiros"], account["registos_iva_vendas"]) == (2, 2, 2)


def test_empty_account_gets_a_valid_zip_with_empty_files(client: TestClient):
    zf = _export(client, _headers("vazio"))

    assert set(zf.namelist()) == BASE_ENTRIES
    assert zf.testzip() is None
    assert json.loads(zf.read("documentos.json")) == []
    assert json.loads(zf.read("iva_vendas.json")) == []
    assert len(_csv_rows(zf, "documentos.csv")) == 1
    assert len(_csv_rows(zf, "iva_vendas.csv")) == 1
    account = json.loads(zf.read("conta.json"))
    assert (account["documentos"], account["ficheiros"], account["registos_iva_vendas"]) == (0, 0, 0)


def test_b_cannot_export_a(client: TestClient, db: Session):
    a, b = _headers("a"), _headers("b")
    a_doc = _receipt(client, a, (10, 10, 200), "Fornecedor Secreto A")
    a_vat = _vat(client, a, 1, "999.99", "nota-privada-de-a")
    b_doc = _receipt(client, b, (200, 200, 10), "Fornecedor B")
    b_vat = _vat(client, b, 1, "1.00", "nota-de-b")
    a_user_id = db.query(User.id).filter(User.clerk_id == a["X-Mock-User-Id"]).scalar()

    # Query parameters that name A are ignored: scope comes from the session only.
    zf = _export(client, b, user_id=a_user_id, user=a["X-Mock-User-Id"])
    assert [d["id"] for d in json.loads(zf.read("documentos.json"))] == [b_doc["id"]]
    assert [v["id"] for v in json.loads(zf.read("iva_vendas.json"))] == [b_vat]
    assert zf.read(f"ficheiros/{b_doc['id']}.jpg") == b_doc["content"]
    assert not [n for n in zf.namelist() if zf.read(n) == a_doc["content"]]
    text = _all_text(zf)
    secrets = (a_doc["id"], a_doc["key"], a_doc["filename"], a_vat, a_user_id, a["X-Mock-User-Id"],
               "Fornecedor Secreto A", "nota-privada-de-a", "a@example.com")
    assert [s for s in secrets if s in text] == []

    assert [d["id"] for d in json.loads(_export(client, a).read("documentos.json"))] == [a_doc["id"]]


def test_a_row_pointing_at_another_users_file_does_not_ship_that_file(client: TestClient, db: Session):
    a, b = _headers("a"), _headers("b")
    a_doc = _receipt(client, a, (10, 200, 200), "Fornecedor A")
    _export(client, b)
    b_user_id = db.query(User.id).filter(User.clerk_id == b["X-Mock-User-Id"]).scalar()
    forged = Document(
        user_id=b_user_id,
        storage_key=a_doc["key"],
        original_filename="forjado.jpg",
        mime_type="image/jpeg",
        status="ready",
    )
    db.add(forged)
    db.commit()

    zf = _export(client, b)

    docs = json.loads(zf.read("documentos.json"))
    assert [(d["id"], d["ficheiro"]) for d in docs] == [(forged.id, None)]
    assert not [n for n in zf.namelist() if n.startswith("ficheiros/")]
    assert not [n for n in zf.namelist() if zf.read(n) == a_doc["content"]]


def test_rate_limited_more_strictly_than_the_period_export(client: TestClient):
    a = _headers("limite")
    codes = [client.get("/api/account/export", headers=a).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
    assert client.get("/api/account/export", headers=_headers("outro")).status_code == 200


def test_flag_off_answers_404(client: TestClient, monkeypatch):
    monkeypatch.setenv("ACCOUNT_EXPORT_ENABLED", "false")
    get_settings.cache_clear()
    try:
        assert client.get("/api/account/export", headers=_headers("off")).status_code == 404
    finally:
        get_settings.cache_clear()


@pytest.mark.parametrize("word", ["RGPD", "GDPR", "dedutível", "dedução", "fiscal", "legal", "lei", "garant"])
def test_readme_is_pt_pt_and_makes_no_tax_or_legal_claims(client: TestClient, word: str):
    readme = _export(client, _headers("leia")).read("LEIA-ME.txt").decode("utf-8")
    assert "exportação dos seus dados" in readme
    assert not re.search(rf"\b{word}", readme, re.IGNORECASE)

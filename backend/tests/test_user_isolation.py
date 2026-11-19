"""
User B tries every /api route against user A's data.

Item routes must answer 403/404. Collection routes (list, summary, export,
pull) answer B with B's own, empty scope. Every response is scanned for A's
identifiers, and A's rows and stored file must be identical afterwards.
test_every_api_route_is_covered fails when a route is added without an attack.
"""

import io
import uuid
import zipfile
from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, Iterator
from urllib.parse import urlsplit

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.main import app
from app.models.audit_log import AuditLog
from app.models.document import Document
from app.models.efatura import EfaturaLink, EfaturaSubject
from app.models.user import User
from app.models.vat_sales import VatSalesEntry
from app.services.storage import get_storage_service

Route = tuple[str, str]  # (method, path template as registered)

VENDOR = "Fornecedor Confidencial A"
NOTE = "nota-privada-do-utilizador-a"
NIF = "555555555"
PERIOD = {"period_type": "quarter", "year": 2026, "quarter": 1}
DENIED = (403, 404)

PUBLIC_ROUTES: frozenset[Route] = frozenset(
    {
        ("GET", "/"),
        ("GET", "/health"),
        ("GET", "/health/detailed"),
        *((method, path) for path in ("/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc") for method in ("GET", "HEAD")),
    }
)


@dataclass(frozen=True)
class World:
    a: dict
    b: dict
    a_user_id: str
    scan_id: str
    at_ids: tuple[str, ...]
    storage_key: str
    filename: str
    vat_id: str

    @property
    def doc_ids(self) -> tuple[str, ...]:
        return (self.scan_id, *self.at_ids)

    @property
    def secrets(self) -> tuple[str, ...]:
        return (
            self.a["X-Mock-User-Id"],
            self.a_user_id,
            *self.doc_ids,
            self.storage_key,
            self.filename,
            self.vat_id,
            VENDOR,
            NOTE,
        )


Attack = Callable[[TestClient, World], list[httpx.Response]]
ATTACKS: dict[Route, Attack] = {}


def attack(method: str, path: str) -> Callable[[Attack], Attack]:
    def register(fn: Attack) -> Attack:
        assert (method, path) not in ATTACKS, (method, path)
        ATTACKS[(method, path)] = fn
        return fn

    return register


@pytest.fixture(autouse=True)
def _efatura_on(monkeypatch):
    monkeypatch.setenv("EFATURA_PULL_ENABLED", "true")
    monkeypatch.setenv("EFATURA_ENDPOINT", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _headers(name: str) -> dict:
    return {"X-Mock-User-Id": f"iso-{name}-{uuid.uuid4().hex[:8]}", "X-Mock-User-Email": f"{name}@example.com"}


@pytest.fixture
def world(client: TestClient, db: Session) -> World:
    a, b = _headers("a"), _headers("b")
    filename = f"recibo-segredo-{uuid.uuid4().hex[:6]}.jpg"
    issued = client.post("/api/documents/upload-url", json={"filename": filename, "content_type": "image/jpeg"}, headers=a)
    assert issued.status_code == 200, issued.text
    key = issued.json()["storage_key"]
    assert client.put(issued.json()["upload_url"], content=b"\xff\xd8\xff\xd9", headers=a).status_code == 200
    created = client.post(
        "/api/documents",
        json={"storage_key": key, "original_filename": filename, "file_size": 4, "mime_type": "image/jpeg"},
        headers=a,
    )
    assert created.status_code == 201, created.text
    scan_id = created.json()["id"]
    edited = client.patch(
        f"/api/documents/{scan_id}",
        json={
            "vendor_name": VENDOR,
            "document_type": "FT",
            "document_date": "2026-02-15",
            "net_amount": "100.00",
            "vat_amount": "23.00",
            "gross_amount": "123.00",
            "status": "ready",
            "review_notes": NOTE,
        },
        headers=a,
    )
    assert edited.status_code == 200, edited.text
    vat = client.post(
        "/api/vat-sales",
        json={"period_type": "quarter", "year": 2026, "period_value": 1, "vat_amount": "999.99", "notes": NOTE},
        headers=a,
    )
    assert vat.status_code == 201, vat.text
    pulled = client.post(
        "/api/efatura/pull",
        json={"taxpayer_nif": NIF, "period_start": "2026-01-01", "period_end": "2026-03-31"},
        headers=a,
    )
    assert pulled.status_code == 200, pulled.text

    a_user_id = db.query(User.id).filter(User.clerk_id == a["X-Mock-User-Id"]).scalar()
    at_ids = tuple(
        sorted(i for (i,) in db.query(Document.id).filter(Document.user_id == a_user_id, Document.id != scan_id))
    )
    assert at_ids, "the e-Fatura fixture gave A no documents"
    return World(a, b, a_user_id, scan_id, at_ids, key, filename, vat.json()["id"])


def _snapshot(db: Session, w: World) -> dict:
    db.expire_all()

    def rows(model, *criteria) -> list[tuple]:
        columns = model.__table__.columns
        return sorted(tuple(str(getattr(row, c.key)) for c in columns) for row in db.query(model).filter(*criteria))

    return {
        "documents": rows(Document, Document.user_id == w.a_user_id),
        "vat_sales": rows(VatSalesEntry, VatSalesEntry.user_id == w.a_user_id),
        "efatura_links": rows(EfaturaLink, EfaturaLink.user_id == w.a_user_id),
        "efatura_subject": rows(EfaturaSubject, EfaturaSubject.user_id == w.a_user_id),
        "audit": rows(AuditLog, (AuditLog.user_id == w.a_user_id) | AuditLog.entity_id.in_(w.doc_ids)),
        "file": get_storage_service().get_file(w.storage_key),
    }


def _visible_text(response: httpx.Response) -> str:
    parts = [f"{k}: {v}" for k, v in response.headers.items()]
    body = response.content
    if body[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(body)) as zf:
            for name in zf.namelist():
                parts += [name, zf.read(name).decode("latin-1")]
    else:
        parts.append(body.decode("latin-1"))
    return "\n".join(parts)


def _leaks(response: httpx.Response, w: World) -> list[str]:
    text = _visible_text(response)
    return [secret for secret in w.secrets if secret in text]


def _signed(url: str) -> str:
    return urlsplit(url).query


# ── documents ──


@attack("POST", "/api/documents/upload-url")
def _upload_url(client: TestClient, w: World) -> list[httpx.Response]:
    r = client.post("/api/documents/upload-url", json={"filename": "../../vitima.jpg", "content_type": "image/jpeg"}, headers=w.b)
    assert r.status_code == 200
    key = r.json()["storage_key"]
    assert key.startswith(f"{w.b['X-Mock-User-Id']}/")
    assert ".." not in key.split("/")
    return [r]


@attack("POST", "/api/documents")
def _create_document(client: TestClient, w: World) -> list[httpx.Response]:
    body = {"original_filename": "x.jpg", "file_size": 4, "mime_type": "image/jpeg"}
    stolen = client.post("/api/documents", json={**body, "storage_key": w.storage_key}, headers=w.b)
    walked = client.post(
        "/api/documents", json={**body, "storage_key": f"{w.b['X-Mock-User-Id']}/../{w.storage_key}"}, headers=w.b
    )
    assert stolen.status_code == 403
    assert walked.status_code in (400, 403)
    return [stolen, walked]


@attack("GET", "/api/documents")
def _list_documents(client: TestClient, w: World) -> list[httpx.Response]:
    responses = [
        client.get("/api/documents", params=params, headers=w.b)
        for params in ({}, {"q": w.filename}, {"q": VENDOR}, {"status": "ready"}, {"page_size": 100})
    ]
    for r in responses:
        assert r.status_code == 200
        assert r.json()["total"] == 0
    return responses


@attack("GET", "/api/documents/{document_id}")
def _read_document(client: TestClient, w: World) -> list[httpx.Response]:
    responses = [client.get(f"/api/documents/{i}", headers=w.b) for i in w.doc_ids]
    assert all(r.status_code in DENIED for r in responses)
    return responses


@attack("PATCH", "/api/documents/{document_id}")
def _edit_document(client: TestClient, w: World) -> list[httpx.Response]:
    edit = {"vendor_name": "Alterado por B", "status": "failed", "invoice_number": "B-1"}
    responses = [client.patch(f"/api/documents/{i}", json=edit, headers=w.b) for i in w.doc_ids]
    assert all(r.status_code in DENIED for r in responses)
    return responses


@attack("DELETE", "/api/documents/{document_id}")
def _delete_document(client: TestClient, w: World) -> list[httpx.Response]:
    responses = [client.delete(f"/api/documents/{i}", headers=w.b) for i in w.doc_ids]
    assert all(r.status_code in DENIED for r in responses)
    return responses


# ── IVA summary, projection, export ──


@attack("GET", "/api/summary")
def _summary(client: TestClient, w: World) -> list[httpx.Response]:
    responses = [
        client.get("/api/summary", params=PERIOD, headers=w.b),
        client.get("/api/summary", params={"period_type": "month", "year": 2026, "month": 2}, headers=w.b),
    ]
    for r in responses:
        assert r.status_code == 200
        body = r.json()
        assert body["total_documents"] == 0
        assert Decimal(str(body["total_vat"])) == 0
        assert Decimal(str(body["deductible_vat"])) == 0
        assert body["vat_on_sales"] is None
    return responses


@attack("GET", "/api/summary/projection")
def _projection(client: TestClient, w: World) -> list[httpx.Response]:
    r = client.get("/api/summary/projection", params={"year": 2026, "quarter": 1, "as_of": "2026-03-31"}, headers=w.b)
    assert r.status_code == 200
    assert Decimal(str(r.json()["confirmed_deductible_to_date"])) == 0
    assert r.json()["vat_on_sales"] is None
    return [r]


@attack("GET", "/api/export")
def _export(client: TestClient, w: World) -> list[httpx.Response]:
    r = client.get("/api/export", params=PERIOD, headers=w.b)
    assert r.status_code == 200
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        assert not [n for n in zf.namelist() if n.startswith("receipts/") or n.endswith(".jpg")]
    return [r]


# ── files ──


def _b_signature(client: TestClient, w: World) -> str:
    issued = client.post("/api/documents/upload-url", json={"filename": "b.jpg", "content_type": "image/jpeg"}, headers=w.b)
    return _signed(issued.json()["upload_url"])


@attack("GET", "/api/files/{storage_key:path}")
def _download(client: TestClient, w: World) -> list[httpx.Response]:
    responses = [
        client.get(f"/api/files/{w.storage_key}", headers=w.b),
        client.get(f"/api/files/{w.storage_key}?{_b_signature(client, w)}", headers=w.b),
    ]
    assert all(r.status_code == 403 for r in responses)
    return responses


@attack("PUT", "/api/files/mock-upload/{storage_key:path}")
def _upload(client: TestClient, w: World) -> list[httpx.Response]:
    responses = [
        client.put(f"/api/files/mock-upload/{w.storage_key}", content=b"B", headers=w.b),
        client.put(f"/api/files/mock-upload/{w.storage_key}?{_b_signature(client, w)}", content=b"B", headers=w.b),
    ]
    assert all(r.status_code == 403 for r in responses)
    return responses


# ── VAT on sales ──


@attack("POST", "/api/vat-sales")
def _upsert_vat(client: TestClient, w: World) -> list[httpx.Response]:
    r = client.post(
        "/api/vat-sales",
        json={"period_type": "quarter", "year": 2026, "period_value": 1, "vat_amount": "1.00", "notes": "B"},
        headers=w.b,
    )
    assert r.status_code == 201
    assert r.json()["id"] != w.vat_id
    return [r]


@attack("GET", "/api/vat-sales")
def _list_vat(client: TestClient, w: World) -> list[httpx.Response]:
    r = client.get("/api/vat-sales", headers=w.b)
    assert r.status_code == 200
    assert r.json()["total"] == 0
    return [r]


@attack("GET", "/api/vat-sales/{entry_id}")
def _read_vat(client: TestClient, w: World) -> list[httpx.Response]:
    r = client.get(f"/api/vat-sales/{w.vat_id}", headers=w.b)
    assert r.status_code in DENIED
    return [r]


@attack("DELETE", "/api/vat-sales/{entry_id}")
def _delete_vat(client: TestClient, w: World) -> list[httpx.Response]:
    r = client.delete(f"/api/vat-sales/{w.vat_id}", headers=w.b)
    assert r.status_code in DENIED
    return [r]


# ── audit, e-Fatura ──


@attack("GET", "/api/audit/documents/{document_id}")
def _audit(client: TestClient, w: World) -> list[httpx.Response]:
    responses = [client.get(f"/api/audit/documents/{i}", headers=w.b) for i in w.doc_ids]
    assert all(r.status_code in DENIED for r in responses)
    return responses


@attack("POST", "/api/efatura/pull")
def _efatura_pull(client: TestClient, w: World) -> list[httpx.Response]:
    pull = client.post(
        "/api/efatura/pull",
        json={"taxpayer_nif": NIF, "period_start": "2026-01-01", "period_end": "2026-03-31"},
        headers=w.b,
    )
    assert pull.status_code == 200
    assert pull.json()["created"], "B's pull should import B's own copies, not link A's"
    assert not pull.json()["linked_existing"]
    listed = client.get("/api/documents", params={"page_size": 100}, headers=w.b)
    assert listed.json()["total"] == len(w.at_ids)
    return [pull, listed]


# ── tests ──


@pytest.mark.parametrize("route", sorted(ATTACKS), ids=lambda route: " ".join(route))
def test_user_b_cannot_reach_user_a(route: Route, client: TestClient, db: Session, world: World):
    before = _snapshot(db, world)

    responses = ATTACKS[route](client, world)

    assert responses
    for response in responses:
        assert _leaks(response, world) == [], f"{response.request.method} {response.request.url}"
    assert _snapshot(db, world) == before
    assert client.get(f"/api/documents/{world.scan_id}", headers=world.a).json()["vendor_name"] == VENDOR
    assert client.get(f"/api/vat-sales/{world.vat_id}", headers=world.a).status_code == 200


def test_owner_sees_what_the_leak_scan_looks_for(client: TestClient, world: World):
    """Without this, an empty scan could just mean the secrets never reach a response."""
    a = world.a
    listed = client.get("/api/documents", params={"page_size": 100}, headers=a)
    assert {d["id"] for d in listed.json()["documents"]} == set(world.doc_ids)
    assert VENDOR in _visible_text(listed) and world.filename in _visible_text(listed)
    assert client.get("/api/summary", params=PERIOD, headers=a).json()["total_documents"] == len(world.doc_ids)
    assert world.vat_id in _visible_text(client.get("/api/vat-sales", headers=a))
    assert VENDOR in _visible_text(client.get("/api/export", params=PERIOD, headers=a))
    file_url = client.get(f"/api/documents/{world.scan_id}", headers=a).json()["file_url"]
    assert client.get(file_url).content == get_storage_service().get_file(world.storage_key)


def _registered_routes() -> Iterator[Route]:
    def walk(route) -> Iterator:
        if hasattr(route, "effective_route_contexts"):
            yield from route.effective_route_contexts()
        else:
            yield route

    for top in app.routes:
        for route in walk(top):
            methods = getattr(route, "methods", None)
            assert methods, f"route without methods (mount?): {route!r}"
            for method in methods:
                yield method, route.path


def test_every_api_route_is_covered():
    registered = set(_registered_routes())
    assert {p for _, p in registered if p.startswith("/api/")}, "route enumeration found no /api routes"
    assert not {r for r in PUBLIC_ROUTES if r[1].startswith("/api")}, "a public /api route needs a deliberate decision"
    assert sorted(registered - ATTACKS.keys() - PUBLIC_ROUTES) == [], "route(s) not covered by the isolation suite"
    assert sorted((ATTACKS.keys() | PUBLIC_ROUTES) - registered) == [], "stale entries; the route no longer exists"

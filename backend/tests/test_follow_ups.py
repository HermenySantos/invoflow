"""
Review follow-ups: JWKS refetch policy, stable mock confidence, error shape.
"""

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from app.api.documents import parse_field_confidence
from app.core import security


@pytest.fixture
def jwks_calls(monkeypatch):
    """Count JWKS fetches; Clerk rotates from key-1 to key-2 after the first fetch."""
    calls = []

    class Response:
        def __init__(self, keys):
            self._keys = keys

        def raise_for_status(self):
            pass

        def json(self):
            return {"keys": [{"kid": kid} for kid in self._keys]}

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, url):
            calls.append(url)
            return Response(["key-1"] if len(calls) == 1 else ["key-1", "key-2"])

    monkeypatch.setattr(security.httpx, "AsyncClient", Client)
    monkeypatch.setattr(security.settings, "clerk_jwks_url", "https://clerk.test/jwks")
    monkeypatch.setattr(security, "_jwks_cache", None)
    monkeypatch.setattr(security, "_jwks_fetched_at", None)
    return calls


def test_known_key_uses_the_cache(jwks_calls):
    asyncio.run(security._find_signing_key("key-1"))
    asyncio.run(security._find_signing_key("key-1"))
    assert len(jwks_calls) == 1


def test_rotated_key_is_found_after_one_refetch(jwks_calls, monkeypatch):
    asyncio.run(security._find_signing_key("key-1"))
    # Cache is older than the refresh interval (also right after boot, where
    # monotonic() is small: the bug CI caught).
    monkeypatch.setattr(security, "_jwks_fetched_at", security.time.monotonic() - security.JWKS_REFRESH_INTERVAL - 1)
    assert asyncio.run(security._find_signing_key("key-2"))["kid"] == "key-2"
    assert len(jwks_calls) == 2


def test_unknown_keys_do_not_refetch_every_time(jwks_calls):
    asyncio.run(security._find_signing_key("key-1"))
    for _ in range(5):
        with pytest.raises(security.HTTPException):
            asyncio.run(security._find_signing_key("junk"))
    assert len(jwks_calls) == 1


def test_mock_field_confidence_is_the_same_on_every_load():
    raw = json.dumps({"mock": True, "id": "abc"})
    assert parse_field_confidence(raw, 80) == parse_field_confidence(raw, 80)


def test_errors_carry_detail_for_the_frontend(client: TestClient):
    response = client.post("/api/vat-sales", json={"period_type": "quarter", "year": 2026, "period_value": 9, "vat_amount": "1"})
    assert response.status_code == 422
    assert response.json()["detail"] == "Invalid request data"


def test_first_refresh_works_right_after_boot(jwks_calls, monkeypatch):
    """monotonic() is small on a freshly booted server; that must not block the refetch."""
    monkeypatch.setattr(security.time, "monotonic", lambda: 10.0)
    monkeypatch.setattr(security, "_jwks_cache", {"keys": [{"kid": "old"}]})
    assert asyncio.run(security._find_signing_key("key-1"))["kid"] == "key-1"
    assert len(jwks_calls) == 1

"""
Mutating routes are limited per signed-in user, per route; signed-out requests per IP.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from starlette.requests import Request

from app.core import rate_limit
from app.core.config import Settings
from tests.test_jwt_validation import clerk, token  # noqa: F401  (clerk is a fixture)

LIMIT = 3


@pytest.fixture
def small_limits(monkeypatch):
    for name in ("rate_limit_write", "rate_limit_upload", "rate_limit_export", "rate_limit_efatura"):
        monkeypatch.setattr(rate_limit.settings, name, f"{LIMIT}/minute")


def user(name=None):
    return {"X-Mock-User-Id": name or f"rl-{uuid.uuid4().hex[:8]}"}


def vat_body(period_value=1):
    return {"period_type": "month", "year": 2026, "period_value": period_value, "vat_amount": "10"}


def post_vat(client, headers, period_value=1):
    return client.post("/api/vat-sales", json=vat_body(period_value), headers=headers)


def test_under_the_limit_every_request_goes_through(client: TestClient, small_limits):
    headers = user()
    for month in range(1, LIMIT + 1):
        assert post_vat(client, headers, month).status_code == 201


def test_over_the_limit_is_429_with_retry_after_and_no_internals(client: TestClient, small_limits):
    headers = user()
    for month in range(1, LIMIT + 1):
        post_vat(client, headers, month)

    response = post_vat(client, headers, 12)

    assert response.status_code == 429
    retry_after = int(response.headers["Retry-After"])
    assert 1 <= retry_after <= 60
    body = response.json()
    assert body["error"]["code"] == "RATE_LIMITED"
    assert body["detail"] == f"Demasiados pedidos. Aguarde {retry_after} s e tente novamente."
    assert "Traceback" not in response.text
    assert "minute" not in response.text


def test_users_do_not_share_buckets(client: TestClient, small_limits):
    alice, bob = user("rl-alice"), user("rl-bob")
    for month in range(1, LIMIT + 1):
        post_vat(client, alice, month)
    assert post_vat(client, alice, 12).status_code == 429

    assert post_vat(client, bob).status_code == 201


def test_one_route_is_one_bucket_whatever_the_id_in_the_url(client: TestClient, small_limits):
    headers = user()
    statuses = [
        client.delete(f"/api/vat-sales/{uuid.uuid4()}", headers=headers).status_code
        for _ in range(LIMIT + 1)
    ]
    assert statuses == [404] * LIMIT + [429]


def test_routes_have_separate_buckets(client: TestClient, small_limits):
    headers = user()
    for month in range(1, LIMIT + 1):
        post_vat(client, headers, month)
    assert post_vat(client, headers, 12).status_code == 429

    assert client.delete(f"/api/vat-sales/{uuid.uuid4()}", headers=headers).status_code == 404


@pytest.mark.parametrize(
    "method, path, body",
    [
        ("patch", "/api/documents/{id}", {"supplier_name": "X"}),
        ("delete", "/api/documents/{id}", None),
        ("post", "/api/vat-sales", vat_body()),
        ("delete", "/api/vat-sales/{id}", None),
        ("post", "/api/documents/upload-url", {"filename": "r.jpg", "content_type": "image/jpeg"}),
        ("get", "/api/export", None),
    ],
)
def test_every_mutating_route_is_limited(client: TestClient, small_limits, method, path, body):
    headers = user()
    kwargs = {"headers": headers}
    if body is not None:
        kwargs["json"] = body
    statuses = [
        getattr(client, method)(path.format(id=uuid.uuid4()), **kwargs).status_code
        for _ in range(LIMIT + 1)
    ]
    assert 429 not in statuses[:LIMIT]
    assert statuses[-1] == 429


def test_efatura_pull_is_limited(client: TestClient, small_limits, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "efatura_pull_enabled", True)
    headers = user()
    body = {"taxpayer_nif": "123456789", "period_start": "2026-01-01", "period_end": "2026-01-31"}
    statuses = [
        client.post("/api/efatura/pull", json=body, headers=headers).status_code
        for _ in range(LIMIT + 1)
    ]
    assert 429 not in statuses[:LIMIT]
    assert statuses[-1] == 429


def test_signed_out_requests_share_one_ip_bucket(client: TestClient, small_limits):
    # The mock upload takes a signed link, not a session; the header is not a login there.
    path = "/api/files/mock-upload/u1/2026/10/a_r.jpg"
    statuses = [
        client.put(path, content=b"x", headers=user()).status_code for _ in range(LIMIT + 1)
    ]
    assert statuses == [403] * LIMIT + [429]


def _request(client_ip: str) -> Request:
    return Request({"type": "http", "headers": [], "client": (client_ip, 1234)})


def test_key_is_the_user_when_signed_in_otherwise_the_ip():
    signed_out = _request("203.0.113.7")
    assert rate_limit.get_user_identifier(signed_out) == "ip:203.0.113.7"
    assert rate_limit.get_user_identifier(_request("198.51.100.1")) == "ip:198.51.100.1"

    signed_in = _request("203.0.113.7")
    rate_limit.remember_rate_limit_user(signed_in, "user_abc")
    assert rate_limit.get_user_identifier(signed_in) == "user:user_abc"


def test_clerk_users_are_keyed_by_token_subject_not_mock_header(
    client: TestClient, small_limits, clerk  # noqa: F811
):
    alice = {"Authorization": f"Bearer {token(sub='user_alice')}"}
    bob = {"Authorization": f"Bearer {token(sub='user_bob')}"}
    statuses = [
        post_vat(client, {**alice, **user()}, month).status_code for month in range(1, LIMIT + 2)
    ]
    assert statuses == [201] * LIMIT + [429]

    assert post_vat(client, bob).status_code == 201


def test_rejected_token_never_reaches_a_bucket(client: TestClient, small_limits, clerk):  # noqa: F811
    statuses = [
        post_vat(client, {"Authorization": "Bearer junk"}).status_code for _ in range(LIMIT + 1)
    ]
    assert statuses == [401] * (LIMIT + 1)


def test_disabled_limiter_lets_everything_through(client: TestClient, small_limits, monkeypatch):
    monkeypatch.setattr(rate_limit.limiter, "enabled", False)
    headers = user()
    assert all(post_vat(client, headers, m).status_code == 201 for m in range(1, LIMIT + 3))


@pytest.mark.parametrize("value", ["", "lots", "10 per fortnight"])
def test_bad_limit_setting_fails_startup(tmp_path, monkeypatch, value):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RATE_LIMIT_WRITE", value)
    with pytest.raises(ValidationError):
        Settings()


def test_limit_settings_come_from_the_environment(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RATE_LIMIT_WRITE", "10/second;300/hour")
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")
    settings = Settings()
    assert settings.rate_limit_write == "10/second;300/hour"
    assert settings.rate_limit_enabled is False

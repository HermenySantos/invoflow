"""
Real Clerk-style JWT validation with PyJWT: RS256 tokens checked against a JWKS,
then iss, azp, exp and nbf checked against settings on a fixed clock.
"""

import asyncio
import json
import logging
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.core import security, startup
from app.core.config import Settings


def new_key(kid: str):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key()))
    public_jwk.update(kid=kid, use="sig", alg="RS256")
    return private, public_jwk


SIGNING, SIGNING_JWK = new_key("clerk-1")
OTHER, _ = new_key("clerk-1")  # same kid, different key: a forged token

NOW = 1_800_000_000
ISSUER = "https://clerk.invoflow.test"
ORIGIN = "https://app.invoflow.test"
LEEWAY = security.CLOCK_LEEWAY_SECONDS


@pytest.fixture
def clerk(monkeypatch):
    monkeypatch.setattr(security.settings, "auth_mock_mode", False)
    monkeypatch.setattr(security.settings, "clerk_frontend_api", "clerk.invoflow.test")
    monkeypatch.setattr(security.settings, "clerk_authorized_parties", [ORIGIN])
    monkeypatch.setattr(security, "_jwks_cache", {"keys": [SIGNING_JWK]})
    monkeypatch.setattr(security, "_jwks_fetched_at", time.monotonic())
    monkeypatch.setattr(security, "_now", lambda: float(NOW))


def token(key=SIGNING, kid="clerk-1", drop=(), **claims) -> str:
    body = {"sub": "user_123", "iss": ISSUER, "azp": ORIGIN, "exp": NOW + 60, "iat": NOW, **claims}
    for name in drop:
        body.pop(name)
    return jwt.encode(body, key, algorithm="RS256", headers={"kid": kid})


def authenticate(raw: str):
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=raw)
    return asyncio.run(security.get_current_user(request=None, credentials=credentials))


def rejected(raw: str) -> HTTPException:
    with pytest.raises(HTTPException) as error:
        authenticate(raw)
    assert error.value.status_code == 401
    return error.value


def test_valid_token_gives_the_clerk_user(clerk):
    user = authenticate(token(nbf=NOW - 1))
    assert user.user_id == "user_123"
    assert user.is_mock is False


@pytest.mark.parametrize("claims", [
    {"iss": "https://clerk.attacker.test"},
    {"iss": "https://clerk.invoflow.test/"},
    {"drop": ("iss",)},
], ids=["other-instance", "trailing-slash", "missing"])
def test_wrong_issuer_is_rejected(clerk, claims):
    rejected(token(**claims))


@pytest.mark.parametrize("claims", [
    {"azp": "https://evil.test"},
    {"azp": "http://app.invoflow.test"},
    {"drop": ("azp",)},
], ids=["other-origin", "other-scheme", "missing"])
def test_wrong_authorized_party_is_rejected(clerk, claims):
    rejected(token(**claims))


def test_missing_exp_is_rejected(clerk):
    rejected(token(drop=("exp",)))


def test_expired_token_is_rejected(clerk):
    rejected(token(exp=NOW - 60))


def test_nbf_in_the_future_is_rejected(clerk):
    rejected(token(nbf=NOW + 60))


def test_leeway_boundary(clerk):
    assert authenticate(token(exp=NOW - LEEWAY + 1)).user_id == "user_123"
    rejected(token(exp=NOW - LEEWAY))
    assert authenticate(token(nbf=NOW + LEEWAY)).user_id == "user_123"
    rejected(token(nbf=NOW + LEEWAY + 1))


def test_empty_allowlist_rejects_every_token(clerk, monkeypatch):
    monkeypatch.setattr(security.settings, "clerk_authorized_parties", [])
    rejected(token())


@pytest.mark.parametrize("raw", [
    token(key=OTHER),          # signed by someone else
    token()[:-4] + "AAAA",     # tampered signature
    token(drop=("sub",)),
    "not-a-jwt",
])
def test_bad_tokens_are_rejected(clerk, raw):
    rejected(raw)


def test_missing_token_is_rejected(clerk):
    with pytest.raises(HTTPException) as error:
        asyncio.run(security.get_current_user(request=None, credentials=None))
    assert error.value.status_code == 401


def test_rejections_never_log_token_contents(clerk, caplog):
    raws = [
        token(iss="https://clerk.attacker.test"),
        token(azp="https://evil.test"),
        token(exp=NOW - 60),
        token(key=OTHER),
        token()[:-4] + "AAAA",
    ]
    with caplog.at_level(logging.DEBUG, logger=security.logger.name):
        for raw in raws:
            rejected(raw)
    logged = caplog.text
    assert "Clerk session token rejected" in logged
    for raw in raws:
        for part in raw.split("."):
            assert part[:16] not in logged
    for value in ("attacker", "evil", "user_123"):
        assert value not in logged


@pytest.mark.parametrize("missing", ["CLERK_FRONTEND_API", "CLERK_AUTHORIZED_PARTIES"])
def test_real_auth_refuses_to_start_without_issuer_or_allowlist(monkeypatch, missing):
    env = {
        "APP_ENV": "production",
        "CLERK_SECRET_KEY": "sk_test_placeholder",
        "CLERK_FRONTEND_API": "clerk.invoflow.test",
        "CLERK_AUTHORIZED_PARTIES": ORIGIN,
    }
    env.pop(missing)
    for name in ("MOCK_AUTH", "AUTH_MOCK_MODE", *env, missing):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    settings = Settings(_env_file=None)
    monkeypatch.setattr(startup, "get_settings", lambda: settings)

    with pytest.raises(startup.ConfigurationError, match=missing):
        startup.validate_configuration()


def test_authorized_parties_parse_from_the_environment(monkeypatch):
    monkeypatch.setenv("CLERK_AUTHORIZED_PARTIES", "https://app.invoflow.test/, https://invoflow.test")
    assert Settings(_env_file=None).clerk_authorized_parties == [
        "https://app.invoflow.test",
        "https://invoflow.test",
    ]

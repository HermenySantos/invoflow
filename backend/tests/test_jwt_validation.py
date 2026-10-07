"""
Real Clerk-style JWT validation with PyJWT: RS256 tokens checked against a JWKS.
"""

import asyncio
import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.core import security


def new_key(kid: str):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key()))
    public_jwk.update(kid=kid, use="sig", alg="RS256")
    return private, public_jwk


SIGNING, SIGNING_JWK = new_key("clerk-1")
OTHER, _ = new_key("clerk-1")  # same kid, different key: a forged token


@pytest.fixture
def clerk(monkeypatch):
    monkeypatch.setattr(security.settings, "auth_mock_mode", False)
    monkeypatch.setattr(security, "_jwks_cache", {"keys": [SIGNING_JWK]})
    monkeypatch.setattr(security, "_jwks_fetched_at", time.monotonic())


def token(key=SIGNING, kid="clerk-1", **claims) -> str:
    body = {"sub": "user_123", "exp": int(time.time()) + 60, **claims}
    return jwt.encode(body, key, algorithm="RS256", headers={"kid": kid})


def authenticate(raw: str):
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=raw)
    return asyncio.run(security.get_current_user(request=None, credentials=credentials))


def test_valid_token_gives_the_clerk_user(clerk):
    user = authenticate(token())
    assert user.user_id == "user_123"
    assert user.is_mock is False


@pytest.mark.parametrize("raw", [
    token(exp=int(time.time()) - 10),  # expired
    token(key=OTHER),                  # signed by someone else
    token()[:-4] + "AAAA",             # tampered signature
    "not-a-jwt",
])
def test_bad_tokens_are_rejected(clerk, raw):
    with pytest.raises(HTTPException) as error:
        authenticate(raw)
    assert error.value.status_code == 401


def test_missing_token_is_rejected(clerk):
    with pytest.raises(HTTPException) as error:
        asyncio.run(security.get_current_user(request=None, credentials=None))
    assert error.value.status_code == 401

"""
Authentication middleware and utilities.
Supports both Clerk JWT validation and mock mode for development.
"""

import logging
import re
import time
from dataclasses import dataclass
import httpx
import jwt
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
from app.core.config import Settings, get_settings

settings = get_settings()
security = HTTPBearer(auto_error=False)
logger = logging.getLogger(__name__)
# Mock ids become storage-key prefixes. A slash or ".." would escape that folder.
_MOCK_USER_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@+-]{0,80}$")


# JWKS cache
_jwks_cache: Optional[dict] = None
_jwks_fetched_at: Optional[float] = None  # time.monotonic() of the last fetch
# A token with an unknown key id triggers at most one refetch per this many
# seconds, so junk tokens can't make every request call Clerk.
JWKS_REFRESH_INTERVAL = 300


async def _get_jwks(force_refresh: bool = False) -> dict:
    """Fetch and cache Clerk's JWKS (JSON Web Key Set)."""
    global _jwks_cache, _jwks_fetched_at

    # monotonic() counts from boot, so "never fetched" can't be modelled as 0.
    recently_fetched = (
        _jwks_fetched_at is not None
        and time.monotonic() - _jwks_fetched_at < JWKS_REFRESH_INTERVAL
    )
    if _jwks_cache is not None and (not force_refresh or recently_fetched):
        return _jwks_cache
    
    jwks_url = settings.clerk_jwks_url
    if not jwks_url and settings.clerk_frontend_api:
        jwks_url = f"https://{settings.clerk_frontend_api}/.well-known/jwks.json"
    
    if not jwks_url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="JWKS URL not configured. Set CLERK_JWKS_URL or CLERK_FRONTEND_API.",
        )
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(jwks_url)
            response.raise_for_status()
            _jwks_cache = response.json()
            _jwks_fetched_at = time.monotonic()
            return _jwks_cache
    except Exception as e:
        logger.error(f"Failed to fetch JWKS from {jwks_url}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch authentication keys",
        )


def _match_key(jwks: dict, kid: str) -> Optional[dict]:
    return next((key for key in jwks.get("keys", []) if key.get("kid") == kid), None)


async def _find_signing_key(kid: str) -> dict:
    """The JWKS key for *kid*, refetching once in case Clerk rotated its keys."""
    key = _match_key(await _get_jwks(), kid) or _match_key(await _get_jwks(force_refresh=True), kid)
    if key:
        return key
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unable to find matching signing key",
    )


CLOCK_LEEWAY_SECONDS = 5


class InvalidSessionToken(Exception):
    """A claim check failed. The message names the check, never a claim value."""


@dataclass(frozen=True)
class ClerkTokenPolicy:
    issuer: str
    authorized_parties: frozenset[str]
    leeway_seconds: int = CLOCK_LEEWAY_SECONDS


def clerk_issuer(frontend_api: str) -> str:
    host = frontend_api.strip().removeprefix("https://").removeprefix("http://").rstrip("/")
    return f"https://{host}" if host else ""


def policy_from_settings(config: Settings) -> ClerkTokenPolicy:
    return ClerkTokenPolicy(
        issuer=clerk_issuer(config.clerk_frontend_api),
        authorized_parties=frozenset(config.clerk_authorized_parties),
    )


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def verify_session_claims(claims: dict, policy: ClerkTokenPolicy, now: float) -> str:
    """The user id (sub) of signature-verified *claims* that pass *policy* at *now*."""
    if not policy.issuer or claims.get("iss") != policy.issuer:
        raise InvalidSessionToken("issuer mismatch")
    if claims.get("azp") not in policy.authorized_parties:
        raise InvalidSessionToken("authorized party not allowed")
    exp = claims.get("exp")
    if not _is_number(exp):
        raise InvalidSessionToken("exp missing")
    if now >= exp + policy.leeway_seconds:
        raise InvalidSessionToken("expired")
    nbf = claims.get("nbf")
    if nbf is not None and (not _is_number(nbf) or now < nbf - policy.leeway_seconds):
        raise InvalidSessionToken("not yet valid")
    sub = claims.get("sub")
    if not isinstance(sub, str) or not sub:
        raise InvalidSessionToken("sub missing")
    return sub


def _now() -> float:
    return time.time()


class CurrentUser:
    """Represents the authenticated user."""
    
    def __init__(self, user_id: str, email: str = "", is_mock: bool = False):
        self.user_id = user_id
        self.email = email
        self.is_mock = is_mock


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> CurrentUser:
    """
    Validate the JWT token and return the current user.
    In mock mode, returns a test user for development.
    """
    
    # Mock mode for development
    if settings.auth_mock_mode:
        mock_user_id = request.headers.get("X-Mock-User-Id", "mock-user-001")
        mock_email = request.headers.get("X-Mock-User-Email", "dev@invoflow.test")
        if ".." in mock_user_id or _MOCK_USER_ID.fullmatch(mock_user_id) is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid mock user id",
            )
        return CurrentUser(user_id=mock_user_id, email=mock_email, is_mock=True)
    
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = credentials.credentials
    
    try:
        # Get the key ID from the token header
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")
        
        if not kid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token missing key ID",
            )
        
        # Fetch JWKS and find the matching key
        signing_key = await _find_signing_key(kid)
        
        # PyJWT checks only the signature; verify_session_claims checks every
        # claim against one injectable clock.
        payload = jwt.decode(
            token,
            jwt.PyJWK(signing_key).key,
            algorithms=["RS256"],
            options={
                "verify_aud": False,  # Clerk doesn't set audience by default
                "verify_exp": False,
                "verify_nbf": False,
                "verify_iat": False,
                "verify_iss": False,
            },
        )
        user_id = verify_session_claims(payload, policy_from_settings(settings), _now())
        return CurrentUser(user_id=user_id, email="", is_mock=False)

    except InvalidSessionToken as e:
        logger.warning("Clerk session token rejected: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.PyJWTError as e:
        # Badly signed tokens say nothing about key rotation, so the JWKS
        # cache is kept (unknown key ids refetch in _find_signing_key).
        # PyJWT messages can quote header or claim values; log the type only.
        logger.warning("Clerk session token rejected: %s", type(e).__name__)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", type(e).__name__)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
            headers={"WWW-Authenticate": "Bearer"},
        )


# Dependency alias for cleaner route definitions
require_auth = Depends(get_current_user)

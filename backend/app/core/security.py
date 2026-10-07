"""
Authentication middleware and utilities.
Supports both Clerk JWT validation and mock mode for development.
"""

import logging
import httpx
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
from app.core.config import get_settings

settings = get_settings()
security = HTTPBearer(auto_error=False)
logger = logging.getLogger(__name__)

# JWT validation imports (only load if not in mock mode)
jwt = None
JWTError = None
if not settings.auth_mock_mode:
    try:
        from jose import jwt as jose_jwt, JWTError as JoseJWTError
        jwt = jose_jwt
        JWTError = JoseJWTError
        logger.info("JWT validation enabled with python-jose")
    except ImportError:
        logger.warning(
            "python-jose not installed. JWT validation will fail. "
            "Install with: pip install python-jose[cryptography]"
        )

# JWKS cache
_jwks_cache: Optional[dict] = None


async def _get_jwks() -> dict:
    """Fetch and cache Clerk's JWKS (JSON Web Key Set)."""
    global _jwks_cache
    
    if _jwks_cache is not None:
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
            return _jwks_cache
    except Exception as e:
        logger.error(f"Failed to fetch JWKS from {jwks_url}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch authentication keys",
        )


def _find_signing_key(jwks: dict, kid: str) -> dict:
    """Find the signing key in JWKS that matches the token's key ID."""
    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            return key
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unable to find matching signing key",
    )


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
        return CurrentUser(user_id=mock_user_id, email=mock_email, is_mock=True)
    
    # Real JWT validation
    if jwt is None:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="JWT validation not available. Install python-jose[cryptography].",
        )
    
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
        jwks = await _get_jwks()
        signing_key = _find_signing_key(jwks, kid)
        
        # Verify and decode the token using the public key from JWKS
        payload = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            options={
                "verify_aud": False,  # Clerk doesn't set audience by default
            },
        )
        
        # Extract user info from Clerk token
        user_id = payload.get("sub")
        
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing user ID",
            )
        
        return CurrentUser(user_id=user_id, email="", is_mock=False)
        
    except JWTError as e:
        logger.warning(f"JWT validation failed: {e}")
        # Clear JWKS cache on failure (key rotation)
        global _jwks_cache
        _jwks_cache = None
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Authentication error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
            headers={"WWW-Authenticate": "Bearer"},
        )


# Dependency alias for cleaner route definitions
require_auth = Depends(get_current_user)

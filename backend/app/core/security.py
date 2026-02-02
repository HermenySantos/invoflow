"""
Authentication middleware and utilities.
Supports both Clerk JWT validation and mock mode for development.
"""

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
from app.core.config import get_settings

settings = get_settings()
security = HTTPBearer(auto_error=False)


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
    
    # Mock mode for development (always enabled for V0)
    if settings.auth_mock_mode:
        # Check for optional mock user header
        mock_user_id = request.headers.get("X-Mock-User-Id", "mock-user-001")
        mock_email = request.headers.get("X-Mock-User-Email", "dev@invoflow.test")
        return CurrentUser(user_id=mock_user_id, email=mock_email, is_mock=True)
    
    # Real Clerk validation requires python-jose package
    # Install with: pip install python-jose[cryptography]
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Real authentication not configured. Set AUTH_MOCK_MODE=true or install python-jose.",
    )


# Dependency alias for cleaner route definitions
require_auth = Depends(get_current_user)

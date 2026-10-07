"""
Rate limiting configuration using slowapi.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address
from fastapi import Request

from app.core.config import get_settings

settings = get_settings()


def get_user_identifier(request: Request) -> str:
    """
    Get a unique identifier for rate limiting.
    Uses the mock user header only in mock mode (it is client-controlled),
    otherwise falls back to IP.
    """
    if settings.auth_mock_mode:
        user_id = request.headers.get("X-Mock-User-Id")
        if user_id:
            return f"user:{user_id}"
    
    # Fall back to IP address
    return get_remote_address(request)


# Create limiter instance
limiter = Limiter(
    key_func=get_user_identifier,
    default_limits=["100/minute"],  # Default: 100 requests per minute
    storage_uri="memory://",  # In-memory storage (use Redis for production)
    strategy="fixed-window",
)


# Rate limit decorators for different endpoint types
RATE_LIMITS = {
    "default": "100/minute",
    "upload": "10/minute",      # Stricter limit for uploads
    "export": "5/minute",       # Export is expensive
    "auth": "20/minute",        # Auth endpoints
}

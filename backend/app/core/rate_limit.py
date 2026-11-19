"""
Rate limiting configuration using slowapi.
"""

import math
import time
from typing import Optional

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import get_settings

settings = get_settings()

RATE_LIMITED_MESSAGE = "Demasiados pedidos. Aguarde {seconds} s e tente novamente."


def remember_rate_limit_user(request: Optional[Request], user_id: str) -> None:
    if request is not None:
        request.state.rate_limit_user = user_id


def get_user_identifier(request: Request) -> str:
    """
    The signed-in user id when authentication has run, otherwise the client IP.
    Limits are checked inside the endpoint, after its auth dependency.
    """
    user_id = getattr(request.state, "rate_limit_user", None)
    if user_id:
        return f"user:{user_id}"
    return f"ip:{get_remote_address(request)}"


limiter = Limiter(
    key_func=get_user_identifier,
    storage_uri="memory://",  # One API process; a multi-process deploy needs shared storage.
    strategy="fixed-window",
    # Bucket by route, not by URL, so /documents/a and /documents/b share one limit.
    key_style="endpoint",
    enabled=settings.rate_limit_enabled,
)


# Read on every request so a changed setting applies without re-decorating routes.
RATE_LIMITS = {
    "write": lambda: settings.rate_limit_write,
    "upload": lambda: settings.rate_limit_upload,
    "export": lambda: settings.rate_limit_export,
    "efatura": lambda: settings.rate_limit_efatura,
    "account_export": lambda: settings.rate_limit_account_export,
}


def retry_after_seconds(request: Request) -> Optional[int]:
    current = getattr(request.state, "view_rate_limit", None)
    if not current:
        return None
    limit, keys = current
    try:
        reset_at, _remaining = limiter.limiter.get_window_stats(limit, *keys)
    except Exception:
        return None
    return max(1, math.ceil(reset_at - time.time()))

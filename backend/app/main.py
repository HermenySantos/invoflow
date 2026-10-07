"""
FaturaFlow API - Main FastAPI application.
"""

import logging
import traceback
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.middleware.base import BaseHTTPMiddleware

from app.api import router as api_router
from app.core.config import get_settings
from app.core.database import Base, engine
from app.core.rate_limit import limiter
from app.core.startup import get_environment_status, run_startup_checks
from app.services.ocr import resolve_ocr_backend, tesseract_available

settings = get_settings()

logging.basicConfig(
    level=logging.INFO if not settings.app_debug else logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def create_error_response(
    code: str,
    message: str,
    status_code: int,
    details: dict = None,
) -> JSONResponse:
    """Create a standardized error response."""
    content = {
        "success": False,
        "error": {
            "code": code,
            "message": message,
            "timestamp": datetime.utcnow().isoformat(),
        },
    }
    if details:
        content["error"]["details"] = details

    return JSONResponse(status_code=status_code, content=content)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"

        if not settings.app_debug:
            response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"

        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log all incoming requests and responses."""

    async def dispatch(self, request: Request, call_next):
        import time

        start_time = time.time()
        logger.info(
            f"Request: {request.method} {request.url.path} "
            f"- Client: {request.client.host if request.client else 'unknown'}"
        )

        response = await call_next(request)
        duration = time.time() - start_time
        logger.info(
            f"Response: {request.method} {request.url.path} "
            f"- Status: {response.status_code} - Duration: {duration:.3f}s"
        )
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    run_startup_checks()
    # Local convenience only; real databases are built with `alembic upgrade head`.
    if settings.app_env == "development":
        Base.metadata.create_all(bind=engine)
    backend = resolve_ocr_backend()
    logger.info("FaturaFlow API starting...")
    logger.info(
        f"Auth mock: {settings.auth_mock_mode}; "
        f"Storage mock: {settings.storage_mock_mode}; "
        f"OCR backend: {backend} (tesseract installed: {tesseract_available()})"
    )
    env_status = get_environment_status()
    logger.info(f"Database: {env_status['database_type']}")
    yield
    logger.info("FaturaFlow API shutting down...")


app = FastAPI(
    title=settings.app_name,
    description="Invoice/receipt API for Portuguese small businesses (FaturaFlow)",
    version="0.2.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning(f"Validation error: {exc.errors()}")
    return create_error_response(
        code="VALIDATION_ERROR",
        message="Invalid request data",
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        details={"errors": exc.errors()},
    )


@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError):
    logger.error(f"Database integrity error: {exc}")
    return create_error_response(
        code="DATABASE_INTEGRITY_ERROR",
        message="Database constraint violation",
        status_code=status.HTTP_409_CONFLICT,
    )


@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_error_handler(request: Request, exc: SQLAlchemyError):
    logger.error(f"Database error: {exc}")
    return create_error_response(
        code="DATABASE_ERROR",
        message="A database error occurred",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    logger.warning(f"Value error: {exc}")
    return create_error_response(
        code="INVALID_VALUE",
        message=str(exc),
        status_code=status.HTTP_400_BAD_REQUEST,
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}\n{traceback.format_exc()}")
    if settings.app_debug:
        return create_error_response(
            code="INTERNAL_ERROR",
            message=str(exc),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details={"traceback": traceback.format_exc()},
        )
    return create_error_response(
        code="INTERNAL_ERROR",
        message="An unexpected error occurred",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

allowed_methods = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
allowed_headers = [
    "Authorization",
    "Content-Type",
    "X-Mock-User-Id",
    "X-Mock-User-Email",
    "X-Requested-With",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=allowed_methods,
    allow_headers=allowed_headers,
)

app.include_router(api_router, prefix=settings.api_prefix)


@app.get("/")
async def root():
    backend = resolve_ocr_backend()
    return {
        "name": settings.app_name,
        "product": "FaturaFlow",
        "version": "0.2.0",
        "status": "healthy",
        "ocr_backend": backend,
        "mock_mode": {
            "auth": settings.auth_mock_mode,
            "storage": settings.storage_mock_mode,
            "ocr": backend == "mock",
        },
    }


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "ocr_backend": resolve_ocr_backend(),
        "tesseract": tesseract_available(),
    }


@app.get("/health/detailed")
async def detailed_health_check():
    """Detailed health check. Full environment status is only returned in debug mode."""
    if not settings.app_debug:
        return {"status": "healthy", "message": "Detailed health checks disabled in production"}

    return {
        "status": "healthy",
        "environment": get_environment_status(),
    }

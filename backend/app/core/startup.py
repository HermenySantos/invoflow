"""
Startup validation and checks.
Ensures required configuration is present before the application starts.
"""

import logging
from typing import List, Tuple
from app.core.config import get_settings

logger = logging.getLogger(__name__)


class ConfigurationError(Exception):
    """Raised when required configuration is missing."""
    pass


def validate_configuration() -> List[str]:
    """
    Validate that all required configuration is present.
    Returns a list of warning messages for non-critical issues.
    Raises ConfigurationError for critical missing configuration.
    """
    settings = get_settings()
    warnings: List[str] = []
    errors: List[str] = []
    
    # Authentication validation
    if not settings.auth_mock_mode:
        if not settings.clerk_secret_key:
            errors.append(
                "AUTH_MOCK_MODE is false but CLERK_SECRET_KEY is not set. "
                "Set CLERK_SECRET_KEY or enable AUTH_MOCK_MODE=true"
            )
        if not settings.clerk_frontend_api:
            warnings.append(
                "CLERK_FRONTEND_API is not set. JWT issuer validation may fail."
            )
    else:
        warnings.append(
            "AUTH_MOCK_MODE is enabled. Authentication is bypassed. "
            "Do not use in production!"
        )
    
    # Storage validation
    if not settings.storage_mock_mode:
        required_r2 = [
            ("R2_ACCOUNT_ID", settings.r2_account_id),
            ("R2_ACCESS_KEY_ID", settings.r2_access_key_id),
            ("R2_SECRET_ACCESS_KEY", settings.r2_secret_access_key),
            ("R2_BUCKET_NAME", settings.r2_bucket_name),
        ]
        missing_r2 = [name for name, value in required_r2 if not value]
        if missing_r2:
            errors.append(
                f"STORAGE_MOCK_MODE is false but missing R2 configuration: "
                f"{', '.join(missing_r2)}. Set these values or enable STORAGE_MOCK_MODE=true"
            )
    else:
        warnings.append(
            "STORAGE_MOCK_MODE is enabled. Files are stored locally. "
            "Configure R2 for production!"
        )
    
    # OCR: Tesseract is the default. Azure is required only when explicitly selected.
    if settings.ocr_backend == "azure":
        if not settings.azure_doc_endpoint or not settings.azure_doc_key:
            errors.append(
                "OCR_BACKEND is azure but AZURE_DOC_ENDPOINT or AZURE_DOC_KEY is not set."
            )
    elif settings.ocr_mock_mode or settings.ocr_backend == "mock":
        warnings.append(
            "OCR mock data is enabled. The default open-source backend is Tesseract."
        )
    
    # Database validation
    if "sqlite" in settings.database_url.lower():
        warnings.append(
            "Using SQLite database. Consider PostgreSQL for production."
        )
    
    # Debug mode warning
    if settings.app_debug:
        warnings.append(
            "APP_DEBUG is enabled. Detailed errors will be exposed. "
            "Disable for production!"
        )
    
    # Raise error if critical configuration is missing
    if errors:
        error_message = "\n".join([f"  - {e}" for e in errors])
        raise ConfigurationError(
            f"Missing required configuration:\n{error_message}"
        )
    
    return warnings


def run_startup_checks() -> None:
    """
    Run all startup checks and log results.
    Called during application startup.
    """
    logger.info("Running startup configuration checks...")
    
    try:
        warnings = validate_configuration()
        
        if warnings:
            logger.warning("Configuration warnings:")
            for warning in warnings:
                logger.warning(f"  - {warning}")
        
        logger.info("Startup checks completed successfully")
        
    except ConfigurationError as e:
        logger.error(f"Configuration error: {e}")
        raise


def get_environment_status() -> dict:
    """
    Get a summary of the current environment configuration.
    Useful for debugging and health checks.
    """
    from app.services.ocr import resolve_ocr_backend, tesseract_available

    settings = get_settings()
    backend = resolve_ocr_backend()

    return {
        "mock_modes": {
            "auth": settings.auth_mock_mode,
            "storage": settings.storage_mock_mode,
            "ocr": backend == "mock",
        },
        "ocr_backend": backend,
        "tesseract": tesseract_available(),
        "debug_mode": settings.app_debug,
        "database_type": "SQLite" if "sqlite" in settings.database_url.lower() else "PostgreSQL",
        "configured_services": {
            "clerk_auth": bool(settings.clerk_secret_key),
            "r2_storage": bool(settings.r2_account_id and settings.r2_access_key_id),
            "azure_ocr": bool(settings.azure_doc_endpoint and settings.azure_doc_key),
        },
    }

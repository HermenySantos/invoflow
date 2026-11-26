import json
from functools import lru_cache
from typing import Union

from limits import parse_many
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings

_MOCK_AUTH_ON = {"1", "true", "yes", "on"}
_MOCK_AUTH_ENVS = {"development", "test"}
_KNOWN_APP_ENVS = _MOCK_AUTH_ENVS | {"production"}


def app_env_name(app_env: str) -> str:
    return app_env.strip().lower()


def mock_auth_requested(mock_auth: str) -> bool:
    return mock_auth.strip().lower() in _MOCK_AUTH_ON


def mock_auth_env_allowed(app_env: str) -> bool:
    return app_env_name(app_env) in _MOCK_AUTH_ENVS


def known_app_env(app_env: str) -> bool:
    return app_env_name(app_env) in _KNOWN_APP_ENVS


def _string_list(value):
    """A JSON list or a comma-separated string from the environment, as a list."""
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("["):
            return json.loads(stripped)
        return [part.strip() for part in stripped.split(",") if part.strip()]
    return value


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    app_name: str = "Invoflow API"
    app_debug: bool = False
    app_env: str = "development"
    api_prefix: str = "/api"

    # SQLite by default so `uvicorn` works without Docker/Postgres.
    database_url: str = "sqlite:///./invoflow.db"

    clerk_secret_key: str = ""
    clerk_publishable_key: str = ""
    clerk_jwks_url: str = ""
    # e.g. "clerk.your-app.com". Session tokens must have iss == https://<this>.
    clerk_frontend_api: str = ""
    # Web origins allowed in a session token's azp claim. Empty rejects every token.
    clerk_authorized_parties: Union[list[str], str] = []
    auth_mock_mode: bool = False
    mock_auth: str = ""

    # Cloudflare R2 (mock mode if not set)
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket_name: str = "invoflow-documents"
    r2_endpoint_url: str = ""

    # Error reporting; empty disables Sentry.
    sentry_dsn: str = ""
    r2_public_url: str = ""
    storage_mock_mode: bool = True
    # Signs mock storage URLs. Random per process unless set.
    mock_url_secret: str = ""

    # OCR: auto (Tesseract if present, else mock). Azure is optional paid.
    ocr_backend: str = "auto"
    ocr_mock_mode: bool = False
    tesseract_lang: str = "por+eng"
    azure_doc_endpoint: str = ""
    azure_doc_key: str = ""
    ollama_base_url: str = ""
    ollama_model: str = "llama3.2"

    # e-Fatura consultation. Off by default. Secrets stay in the environment.
    # The documented test URL is not a default:
    # https://servicos.portaldasfinancas.gov.pt:725/fatshare/ws/fatshareFaturas
    efatura_pull_enabled: bool = False
    efatura_endpoint: str = ""
    efatura_username: str = ""
    efatura_password: str = ""
    efatura_at_public_key_pem: str = ""
    efatura_client_cert_pem: str = ""
    efatura_client_key_pem: str = ""

    # Whole-account data export (GET /api/account/export). Off answers 404.
    account_export_enabled: bool = True

    cors_origins: Union[list[str], str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    # Per signed-in user (per IP when signed out), per route, in-process memory.
    # Values use the `limits` syntax: "60/minute", "10/second;300/hour".
    rate_limit_enabled: bool = True
    rate_limit_write: str = "60/minute"
    rate_limit_upload: str = "30/minute"
    rate_limit_export: str = "5/minute"
    rate_limit_efatura: str = "5/minute"
    # Whole-account export reads every receipt file the user owns.
    rate_limit_account_export: str = "2/minute;10/hour"
    # Public readiness check; it runs a database query, so cap it per IP.
    rate_limit_health: str = "30/minute"

    @model_validator(mode="after")
    def enable_mock_auth_only_when_asked(self):
        requested = bool(self.auth_mock_mode) or mock_auth_requested(self.mock_auth)
        object.__setattr__(self, "_mock_auth_requested", requested)
        self.auth_mock_mode = requested and mock_auth_env_allowed(self.app_env)
        return self

    @field_validator("efatura_pull_enabled", mode="before")
    @classmethod
    def empty_efatura_flag_is_off(cls, value):
        if value is None or (isinstance(value, str) and value.strip() == ""):
            return False
        return value

    @field_validator(
        "rate_limit_write",
        "rate_limit_upload",
        "rate_limit_export",
        "rate_limit_efatura",
        "rate_limit_account_export",
        "rate_limit_health",
    )
    @classmethod
    def parse_rate_limit(cls, value: str):
        try:
            parse_many(value)
        except ValueError as exc:
            raise ValueError(f"not a rate limit such as 60/minute: {value!r}") from exc
        return value

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors(cls, value):
        return _string_list(value)

    @field_validator("clerk_authorized_parties", mode="before")
    @classmethod
    def parse_authorized_parties(cls, value):
        return [party.strip().rstrip("/") for party in _string_list(value) if party.strip()]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()

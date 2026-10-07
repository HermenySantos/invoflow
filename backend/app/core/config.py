from functools import lru_cache
from typing import Union

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    app_name: str = "FaturaFlow API"
    app_debug: bool = True
    # "development" allows the mock auth/storage modes; anything else refuses them.
    app_env: str = "development"
    api_prefix: str = "/api"

    # SQLite by default so `uvicorn` works without Docker/Postgres.
    database_url: str = "sqlite:///./invoflow.db"

    clerk_secret_key: str = ""
    clerk_publishable_key: str = ""
    clerk_jwks_url: str = ""
    clerk_frontend_api: str = ""  # e.g., "clerk.your-app.com"
    auth_mock_mode: bool = True

    # Cloudflare R2 (mock mode if not set)
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket_name: str = "invoflow-documents"
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

    cors_origins: Union[list[str], str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors(cls, value):
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("["):
                import json

                return json.loads(stripped)
            return [part.strip() for part in stripped.split(",") if part.strip()]
        return value

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()

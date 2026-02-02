from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # App
    app_name: str = "InvoFlow API"
    app_debug: bool = True  # Renamed to avoid conflict with system DEBUG var
    api_prefix: str = "/api"
    
    # Database (defaults to SQLite for easy local dev, use PostgreSQL in production)
    database_url: str = "sqlite:///./invoflow.db"
    
    # Clerk Auth (mock mode if not set)
    clerk_secret_key: str = ""
    clerk_publishable_key: str = ""
    clerk_jwks_url: str = ""
    auth_mock_mode: bool = True  # Set to False when Clerk is configured
    
    # Cloudflare R2 (mock mode if not set)
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket_name: str = "invoflow-documents"
    r2_public_url: str = ""
    storage_mock_mode: bool = True  # Set to False when R2 is configured
    
    # Mindee OCR (mock mode if not set)
    mindee_api_key: str = ""
    ocr_mock_mode: bool = True  # Set to False when Mindee is configured
    
    # CORS
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()

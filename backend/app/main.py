"""
InvoFlow API - Main FastAPI application.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.database import engine, Base
from app.api import router as api_router

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup: Create database tables
    Base.metadata.create_all(bind=engine)
    print(f"🚀 InvoFlow API starting...")
    print(f"   Mock mode - Auth: {settings.auth_mock_mode}")
    print(f"   Mock mode - Storage: {settings.storage_mock_mode}")
    print(f"   Mock mode - OCR: {settings.ocr_mock_mode}")
    yield
    # Shutdown
    print("👋 InvoFlow API shutting down...")


app = FastAPI(
    title=settings.app_name,
    description="Invoice/Receipt management API for Portuguese SMBs",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router, prefix=settings.api_prefix)


@app.get("/")
async def root():
    """Root endpoint - health check."""
    return {
        "name": settings.app_name,
        "version": "0.1.0",
        "status": "healthy",
        "mock_mode": {
            "auth": settings.auth_mock_mode,
            "storage": settings.storage_mock_mode,
            "ocr": settings.ocr_mock_mode,
        },
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}

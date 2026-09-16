"""
FaturaFlow API - Main FastAPI application.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import router as api_router
from app.core.config import get_settings
from app.core.database import Base, engine
from app.services.ocr import resolve_ocr_backend, tesseract_available

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    backend = resolve_ocr_backend()
    print("FaturaFlow API starting...")
    print(f"   Auth mock: {settings.auth_mock_mode}")
    print(f"   Storage mock: {settings.storage_mock_mode}")
    print(f"   OCR backend: {backend} (tesseract installed: {tesseract_available()})")
    yield
    print("FaturaFlow API shutting down...")


app = FastAPI(
    title=settings.app_name,
    description="Invoice/receipt API for Portuguese small businesses (FaturaFlow)",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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

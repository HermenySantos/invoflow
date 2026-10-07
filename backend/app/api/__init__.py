from fastapi import APIRouter
from app.api import documents, summary, exports, files, vat_sales, audit

router = APIRouter()

router.include_router(documents.router, prefix="/documents", tags=["documents"])
router.include_router(summary.router, prefix="/summary", tags=["summary"])
router.include_router(exports.router, prefix="/export", tags=["export"])
router.include_router(files.router, prefix="/files", tags=["files"])
router.include_router(vat_sales.router, prefix="/vat-sales", tags=["vat-sales"])
router.include_router(audit.router, prefix="/audit", tags=["audit"])

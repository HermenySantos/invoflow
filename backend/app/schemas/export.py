from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class ExportResponse(BaseModel):
    """Response for export generation."""
    
    filename: str
    download_url: str
    period: str
    document_count: int
    total_vat: str
    generated_at: datetime
    expires_at: Optional[datetime] = None

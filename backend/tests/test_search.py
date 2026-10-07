"""
Receipt search: text, date range and amount range.
"""

import uuid
from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.user import User


def seed(db: Session) -> dict:
    user = User(clerk_id=f"test-user-{uuid.uuid4().hex[:8]}", email="")
    db.add(user)
    db.commit()
    rows = [
        ("Pingo Doce", "503504564", "FT 2026/12", date(2026, 9, 3), "12.40"),
        ("Galp Energia", "504499777", "FT A/77", date(2026, 9, 20), "85.00"),
        ("100% Bio_Loja", None, None, date(2026, 10, 1), "40.00"),
    ]
    for vendor, nif, invoice, when, gross in rows:
        db.add(Document(
            user_id=user.id, status="ready", storage_key=f"{user.clerk_id}/{uuid.uuid4().hex}",
            original_filename="r.jpg", mime_type="image/jpeg", vendor_name=vendor, vendor_nif=nif,
            invoice_number=invoice, document_date=when, gross_amount=Decimal(gross),
        ))
    db.commit()
    return {"X-Mock-User-Id": user.clerk_id}


def vendors(client: TestClient, headers: dict, **params) -> list[str]:
    response = client.get("/api/documents", params=params, headers=headers)
    assert response.status_code == 200
    return sorted(d["vendor_name"] for d in response.json()["documents"])


def test_text_search_matches_vendor_nif_and_invoice(client: TestClient, db: Session):
    headers = seed(db)
    assert vendors(client, headers, q="pingo") == ["Pingo Doce"]
    assert vendors(client, headers, q="504499") == ["Galp Energia"]
    assert vendors(client, headers, q="a/77") == ["Galp Energia"]


def test_wildcards_in_search_are_literal(client: TestClient, db: Session):
    headers = seed(db)
    assert vendors(client, headers, q="100%") == ["100% Bio_Loja"]
    assert vendors(client, headers, q="_") == ["100% Bio_Loja"]


def test_date_and_amount_ranges(client: TestClient, db: Session):
    headers = seed(db)
    assert vendors(client, headers, date_from="2026-09-10", date_to="2026-09-30") == ["Galp Energia"]
    assert vendors(client, headers, min_amount="20", max_amount="50") == ["100% Bio_Loja"]

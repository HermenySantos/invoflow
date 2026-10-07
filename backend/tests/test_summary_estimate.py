"""
The IVA estimate only counts receipts a person has checked.
"""

import uuid
from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.user import User


def add_receipt(db: Session, user: User, status: str, vat: str) -> None:
    db.add(Document(
        user_id=user.id,
        status=status,
        storage_key=f"{user.clerk_id}/2026/09/{uuid.uuid4().hex[:8]}_r.jpg",
        original_filename="r.jpg",
        mime_type="image/jpeg",
        document_date=date(2026, 9, 15),
        vat_amount=Decimal(vat),
        gross_amount=Decimal(vat) * 5,
        expense_category="office",  # 100% deductible
    ))


def test_unreviewed_receipts_are_reported_but_not_estimated(client: TestClient, db: Session):
    clerk_id = f"test-user-{uuid.uuid4().hex[:8]}"
    user = User(clerk_id=clerk_id, email="")
    db.add(user)
    db.commit()
    add_receipt(db, user, "ready", "10.00")
    add_receipt(db, user, "accountant_review", "5.00")
    add_receipt(db, user, "needs_review", "7.00")
    db.commit()
    headers = {"X-Mock-User-Id": clerk_id}
    client.post(
        "/api/vat-sales",
        json={"period_type": "month", "year": 2026, "period_value": 9, "vat_amount": "100"},
        headers=headers,
    )

    summary = client.get(
        "/api/summary", params={"period_type": "month", "year": 2026, "month": 9}, headers=headers
    ).json()

    assert summary["deductible_vat"] == "15.00"
    assert summary["deductible_vat_pending"] == "7.00"
    assert summary["estimated_iva_payable"] == "85.00"
    assert any("7,00 € de IVA dedutível em 1 recibo(s) por rever" in w for w in summary["warnings"])


def test_export_builds_with_reviewed_and_pending_receipts(client: TestClient, db: Session):
    clerk_id = f"test-user-{uuid.uuid4().hex[:8]}"
    user = User(clerk_id=clerk_id, email="")
    db.add(user)
    db.commit()
    add_receipt(db, user, "ready", "10.00")
    add_receipt(db, user, "needs_review", "7.00")
    db.commit()

    response = client.get(
        "/api/export",
        params={"period_type": "month", "year": 2026, "month": 9},
        headers={"X-Mock-User-Id": clerk_id},
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"

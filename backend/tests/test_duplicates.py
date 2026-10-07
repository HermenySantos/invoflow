"""
Possible duplicate receipts are flagged on the document and in the summary.
"""

import uuid
from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.user import User
from app.services.validation import count_duplicates


def make_user(db: Session) -> User:
    user = User(clerk_id=f"test-user-{uuid.uuid4().hex[:8]}", email="")
    db.add(user)
    db.commit()
    return user


def receipt(user: User, **fields) -> Document:
    defaults = dict(
        user_id=user.id,
        status="ready",
        storage_key=f"{user.clerk_id}/2026/09/{uuid.uuid4().hex[:8]}_r.jpg",
        original_filename="r.jpg",
        mime_type="image/jpeg",
        vendor_name="Pingo Doce",
        document_date=date(2026, 9, 15),
        gross_amount=Decimal("35.20"),
        vat_amount=Decimal("5.20"),
    )
    defaults.update(fields)
    return Document(**defaults)


def test_same_invoice_number_from_same_vendor_is_a_duplicate():
    user = User(id="u", clerk_id="c", email="")
    first = receipt(user, vendor_nif="503504564", invoice_number="FT 2026/12")
    again = receipt(user, vendor_nif="503504564", invoice_number="ft 2026/12", gross_amount=Decimal("99"))
    other = receipt(user, vendor_nif="503504564", invoice_number="FT 2026/13")
    assert count_duplicates([first, again, other]) == 1


def test_same_vendor_date_and_amount_is_a_duplicate():
    user = User(id="u", clerk_id="c", email="")
    first = receipt(user)
    again = receipt(user, vendor_name="PINGO DOCE ", gross_amount=Decimal("35.40"))
    later = receipt(user, document_date=date(2026, 9, 16))
    assert count_duplicates([first, again, later]) == 1


def test_document_and_summary_show_duplicate_warning(client: TestClient, db: Session):
    user = make_user(db)
    first = receipt(user)
    again = receipt(user)
    db.add_all([first, again])
    db.commit()
    headers = {"X-Mock-User-Id": user.clerk_id}

    document = client.get(f"/api/documents/{again.id}", headers=headers).json()
    duplicate = [w for w in document["validation_warnings"] if w["code"] == "possible_duplicate"]
    assert duplicate and duplicate[0]["duplicate_id"] == first.id

    summary = client.get(
        "/api/summary", params={"period_type": "month", "year": 2026, "month": 9}, headers=headers
    ).json()
    assert any("1 possível(is) recibo(s) duplicado(s)" in w for w in summary["warnings"])

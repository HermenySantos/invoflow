"""
VAT deductibility per receipt (CIVA art. 21): fuel type and user overrides.
"""

import json
import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.user import User
from app.services.categorization import detect_fuel_type, effective_deductible_pct
from app.services.validation import validate_document


def fuel_receipt(text: str | None = None, **fields) -> Document:
    raw = json.dumps({"text": text}) if text is not None else None
    return Document(expense_category="fuel", ocr_raw_response=raw, deductible_pct_override=None, **fields)


@pytest.mark.parametrize("text, expected", [
    ("GALP\nGasolina 95 Simples 40,00L", "gasoline"),
    ("PRIO\nSem Chumbo 95", "gasoline"),
    ("REPSOL\nGasóleo Simples 30,00L", "diesel"),
    ("BP\nDiesel Ultimate", "diesel"),
    ("Autogás GPL 20L", "diesel"),
    ("Loja de conveniência\nCafé 1,20", None),
])
def test_fuel_type_detection(text, expected):
    assert detect_fuel_type(text) == expected


def test_gasoline_is_not_deductible_and_diesel_is_half():
    assert effective_deductible_pct(fuel_receipt("Gasolina 95")) == 0
    assert effective_deductible_pct(fuel_receipt("Gasóleo")) == 50
    assert effective_deductible_pct(fuel_receipt("Combustível")) == 50  # unknown keeps the category rule


def test_override_wins_over_the_category_rule():
    repair = Document(expense_category="services", deductible_pct_override=0)
    assert effective_deductible_pct(repair) == 0


def test_unknown_fuel_type_asks_the_user_to_confirm():
    codes = [w["code"] for w in validate_document(fuel_receipt("Combustível"))]
    assert "fuel_type_unknown" in codes
    assert "fuel_type_unknown" not in [w["code"] for w in validate_document(fuel_receipt("Gasóleo"))]


def test_override_through_the_api_changes_the_estimate(client: TestClient, db: Session):
    user = User(clerk_id=f"test-user-{uuid.uuid4().hex[:8]}", email="")
    db.add(user)
    db.commit()
    repair = Document(
        user_id=user.id, status="ready", storage_key=f"{user.clerk_id}/{uuid.uuid4().hex}",
        original_filename="r.jpg", mime_type="image/jpeg", vendor_name="Oficina Auto",
        document_date=date(2026, 9, 10), vat_amount=Decimal("46.00"), gross_amount=Decimal("246.00"),
        expense_category="services",
    )
    db.add(repair)
    db.commit()
    headers = {"X-Mock-User-Id": user.clerk_id}
    september = {"period_type": "month", "year": 2026, "month": 9}

    assert client.get("/api/summary", params=september, headers=headers).json()["deductible_vat"] == "46.00"

    updated = client.patch(f"/api/documents/{repair.id}", json={"deductible_pct_override": 0}, headers=headers)
    assert updated.status_code == 200
    assert updated.json()["deductible_pct"] == 0

    assert client.get("/api/summary", params=september, headers=headers).json()["deductible_vat"] == "0.00"

    audit = client.get(f"/api/audit/documents/{repair.id}", headers=headers).json()
    assert any("deductible_pct_override" in (e["changes_json"] or "") for e in audit["entries"])

"""
VAT on sales: entering it, reading it back through the summary, and the payable.
"""

import uuid

from fastapi.testclient import TestClient


def user_headers():
    return {"X-Mock-User-Id": f"test-user-{uuid.uuid4().hex[:8]}"}


SEPTEMBER = {"period_type": "month", "year": 2026, "month": 9}


def test_payable_is_empty_until_vat_on_sales_is_entered(client: TestClient):
    summary = client.get("/api/summary", params=SEPTEMBER, headers=user_headers()).json()

    assert summary["vat_on_sales"] is None
    assert summary["estimated_iva_payable"] is None
    assert "Introduza o IVA das vendas para calcular o IVA a pagar" in summary["warnings"]


def test_entered_vat_on_sales_is_read_back_including_zero(client: TestClient):
    headers = user_headers()
    response = client.post(
        "/api/vat-sales",
        json={"period_type": "month", "year": 2026, "period_value": 9, "vat_amount": "0"},
        headers=headers,
    )
    assert response.status_code == 201

    summary = client.get("/api/summary", params=SEPTEMBER, headers=headers).json()
    assert summary["vat_on_sales"] == "0.00"
    assert summary["estimated_iva_payable"] == "0.00"

    listed = client.get("/api/vat-sales", params={"year": 2026}, headers=headers).json()
    assert listed["total"] == 1
    assert listed["entries"][0]["period_value"] == 9


def test_quarter_above_four_is_rejected(client: TestClient):
    response = client.post(
        "/api/vat-sales",
        json={"period_type": "quarter", "year": 2026, "period_value": 7, "vat_amount": "10"},
        headers=user_headers(),
    )
    assert response.status_code == 422

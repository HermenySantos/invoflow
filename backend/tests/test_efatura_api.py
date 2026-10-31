"""Pull route and projection route. The pull is off unless the flag is set."""

import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.startup import validate_configuration
from app.models.document import Document
from app.models.efatura import EfaturaLink
from app.models.user import User
from app.services.efatura import EFaturaConfigError, EFaturaDisabled, SoapEFaturaClient, build_efatura_client


@pytest.fixture(autouse=True)
def _fresh_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _headers() -> dict:
    return {"X-Mock-User-Id": f"pull-{uuid.uuid4().hex[:8]}", "X-Mock-User-Email": "pull@example.com"}


def _enable(monkeypatch):
    monkeypatch.setenv("EFATURA_PULL_ENABLED", "true")
    monkeypatch.setenv("EFATURA_ENDPOINT", "")
    get_settings.cache_clear()


def test_pull_is_404_when_the_flag_is_off(client: TestClient, db: Session, monkeypatch):
    def boom():
        raise AssertionError("fixture opened")

    monkeypatch.setattr("app.services.efatura._load_fixture_rows", boom)
    response = client.post(
        "/api/efatura/pull",
        json={"taxpayer_nif": "555555555", "period_start": "2026-01-01", "period_end": "2026-03-31"},
        headers=_headers(),
    )
    assert response.status_code == 404
    assert db.query(EfaturaLink).count() == 0


def test_lifespan_does_not_pull():
    source = Path("app/main.py").read_text(encoding="utf-8")
    assert "import_purchases" not in source
    assert "build_efatura_client" not in source


def test_pull_imports_the_fixture_when_enabled(client: TestClient, db: Session, monkeypatch):
    _enable(monkeypatch)
    headers = _headers()
    response = client.post(
        "/api/efatura/pull",
        json={"taxpayer_nif": "555555555", "period_start": "2020-01-01", "period_end": "2099-12-31"},
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["created"]
    assert any(item["outcome"] == "issuer" for item in body["skipped"])

    again = client.post(
        "/api/efatura/pull",
        json={"taxpayer_nif": "123456789", "period_start": "2020-01-01", "period_end": "2099-12-31"},
        headers=headers,
    )
    assert again.status_code == 409
    assert db.query(EfaturaLink).count() > 0


def test_summary_keeps_a_later_receipt_that_the_projection_drops(
    client: TestClient, db: Session
):
    clerk_id = f"proj-{uuid.uuid4().hex[:8]}"
    user = User(clerk_id=clerk_id, email="")
    db.add(user)
    db.commit()
    for when, vat in ((date(2026, 1, 15), "46.00"), (date(2026, 3, 20), "10.00")):
        db.add(Document(
            user_id=user.id,
            status="ready",
            storage_key=f"{clerk_id}/{when.isoformat()}.jpg",
            original_filename="r.jpg",
            mime_type="image/jpeg",
            document_date=when,
            vat_amount=Decimal(vat),
            gross_amount=Decimal(vat),
            expense_category="office",
            document_type="FT",
        ))
    db.commit()
    headers = {"X-Mock-User-Id": clerk_id}
    client.post(
        "/api/vat-sales",
        json={"period_type": "quarter", "year": 2026, "period_value": 1, "vat_amount": "100.00"},
        headers=headers,
    )
    client.post(
        "/api/vat-sales",
        json={"period_type": "month", "year": 2026, "period_value": 1, "vat_amount": "999.00"},
        headers=headers,
    )

    summary = client.get(
        "/api/summary",
        params={"period_type": "quarter", "year": 2026, "quarter": 1},
        headers=headers,
    ).json()
    projection = client.get(
        "/api/summary/projection",
        params={"year": 2026, "quarter": 1, "as_of": "2026-02-15"},
        headers=headers,
    ).json()

    assert summary["deductible_vat"] == "56.00"
    assert summary["estimated_iva_payable"] == "44.00"
    assert projection["confirmed_deductible_to_date"] == "46.00"
    assert projection["projected_deductible"] == "90.00"
    assert projection["projected_iva_payable"] == "10.00"
    assert projection["sales_basis"] == "entered_period_lump"
    assert projection["label"] == "IVA previsto (estimativa)"
    assert projection["period"] == "2026-Q1"
    assert "Não é uma declaração fiscal." in projection["disclaimer"]


def test_projection_without_a_quarter_sales_row_stays_empty(client: TestClient, db: Session):
    clerk_id = f"proj-{uuid.uuid4().hex[:8]}"
    user = User(clerk_id=clerk_id, email="")
    db.add(user)
    db.commit()
    headers = {"X-Mock-User-Id": clerk_id}
    client.post(
        "/api/vat-sales",
        json={"period_type": "month", "year": 2026, "period_value": 2, "vat_amount": "40.00"},
        headers=headers,
    )
    projection = client.get(
        "/api/summary/projection",
        params={"year": 2026, "quarter": 1, "as_of": "2026-02-15"},
        headers=headers,
    ).json()
    assert projection["projected_iva_payable"] is None
    assert projection["sales_basis"] == "missing"


def test_disabled_client_does_not_construct_a_fixture(monkeypatch):
    monkeypatch.delenv("EFATURA_PULL_ENABLED", raising=False)
    get_settings.cache_clear()
    with pytest.raises(EFaturaDisabled):
        build_efatura_client(get_settings())


def test_incomplete_endpoint_config_does_not_connect(monkeypatch):
    monkeypatch.setenv("EFATURA_PULL_ENABLED", "true")
    monkeypatch.setenv("EFATURA_ENDPOINT", "https://servicos.portaldasfinancas.gov.pt:725/fatshare/ws/fatshareFaturas")
    monkeypatch.setenv("EFATURA_USERNAME", "")
    monkeypatch.setenv("EFATURA_PASSWORD", "")
    monkeypatch.setenv("EFATURA_AT_PUBLIC_KEY_PEM", "")
    get_settings.cache_clear()
    with pytest.raises(EFaturaConfigError):
        build_efatura_client(get_settings())


def test_soap_fetch_is_not_implemented():
    client = SoapEFaturaClient(
        endpoint="https://example.test/ws",
        username="555555555/1",
        password="not-a-real-secret",
        at_public_key_pem="-----BEGIN PUBLIC KEY-----\nMIIB\n-----END PUBLIC KEY-----",
    )
    with pytest.raises(NotImplementedError):
        client.fetch(None)


def test_default_boot_does_not_warn_about_efatura():
    get_settings.cache_clear()
    warnings = validate_configuration()
    assert not any("EFATURA" in warning for warning in warnings)


def test_incomplete_efatura_config_warns_and_does_not_raise(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "efatura_pull_enabled", True)
    monkeypatch.setattr(settings, "efatura_endpoint", "https://example.test/ws")
    monkeypatch.setattr(settings, "efatura_username", "")
    monkeypatch.setattr(settings, "efatura_password", "")
    monkeypatch.setattr(settings, "efatura_at_public_key_pem", "")
    warnings = validate_configuration()
    assert any("EFATURA_PASSWORD" in warning for warning in warnings)

"""/health/detailed is the readiness check: it answers 503 naming `database` when the DB is down."""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import get_db
from app.main import app

SECRET = "s3cret-do-not-print"
POSTGRES_URL = os.environ.get("HEALTH_POSTGRES_URL")


def _use_database(monkeypatch, url: str, **engine_kwargs) -> None:
    engine = create_engine(url, **engine_kwargs)
    factory = sessionmaker(bind=engine)

    def override():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    monkeypatch.setitem(app.dependency_overrides, get_db, override)


def _assert_down(response) -> None:
    assert response.status_code == 503, response.text
    body = response.json()
    assert body["status"] == "degraded"
    assert body["checks"] == {"database": "down"}
    assert SECRET not in response.text


def test_liveness_does_not_touch_the_database(client: TestClient, monkeypatch):
    _use_database(monkeypatch, f"sqlite:////nonexistent-{SECRET}/invoflow.db")
    assert client.get("/health").status_code == 200


def test_readiness_ok_with_sqlite(client: TestClient):
    response = client.get("/health/detailed")
    assert response.status_code == 200, response.text
    assert response.json()["checks"] == {"database": "ok"}


def test_readiness_503_when_sqlite_unreachable(client: TestClient, monkeypatch):
    _use_database(monkeypatch, f"sqlite:////nonexistent-{SECRET}/invoflow.db")
    _assert_down(client.get("/health/detailed"))


def test_readiness_503_in_production_mode_without_environment(client: TestClient, monkeypatch):
    from app.main import settings

    monkeypatch.setattr(settings, "app_debug", False)
    _use_database(monkeypatch, f"sqlite:////nonexistent-{SECRET}/invoflow.db")
    response = client.get("/health/detailed")
    _assert_down(response)
    assert "environment" not in response.json()


@pytest.mark.skipif(not POSTGRES_URL, reason="HEALTH_POSTGRES_URL not set")
def test_readiness_ok_with_postgres(client: TestClient, monkeypatch):
    _use_database(monkeypatch, POSTGRES_URL)
    response = client.get("/health/detailed")
    assert response.status_code == 200, response.text
    assert response.json()["checks"] == {"database": "ok"}


@pytest.mark.skipif(not POSTGRES_URL, reason="HEALTH_POSTGRES_URL not set")
def test_readiness_503_when_postgres_unreachable(client: TestClient, monkeypatch):
    # Nothing listens on port 1, so the connection is refused at once.
    _use_database(
        monkeypatch,
        f"postgresql://invoflow:{SECRET}@127.0.0.1:1/invoflow",
        connect_args={"connect_timeout": 2},
    )
    _assert_down(client.get("/health/detailed"))


def test_readiness_is_rate_limited_and_liveness_is_not(client: TestClient, monkeypatch):
    from app.core import rate_limit

    monkeypatch.setattr(rate_limit.settings, "rate_limit_health", "2/minute")
    statuses = [client.get("/health/detailed").status_code for _ in range(3)]
    assert statuses == [200, 200, 429]
    assert client.get("/health").status_code == 200

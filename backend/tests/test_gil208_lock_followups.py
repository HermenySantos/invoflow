"""GIL-208. Follow-ups from the QA gate on PR #39 (GATE-7d59623).

The shared lock budget (N-1), writers that do not wait for a pull (N-2), the
waiter cap (N-3) and the 4-worker hammer (N-4) need Postgres and real
workers: scripts/check_lock_storm.py. The idle-limit pull (N-5) end to end is
in scripts/check_hung_pull.py. Here: what the API answers for each failure.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.db_errors import DB_BUSY_DETAIL, DB_INTERRUPTED_DETAIL
from app.models.document import Document
from tests.test_gil160_linked_delete import _purchase, _user
from tests.test_gil205_series_case import _pull

PERIOD = {"taxpayer_nif": "555555555", "period_start": "2020-01-01", "period_end": "2099-12-31"}


class _PgError(Exception):
    def __init__(self, pgcode):
        super().__init__(pgcode)
        self.pgcode = pgcode


def _db_error(pgcode=None, *, dropped=False) -> OperationalError:
    return OperationalError("SELECT 1", {}, _PgError(pgcode), connection_invalidated=dropped)


def _raise(exc):
    def raiser(*args, **kwargs):
        raise exc

    return raiser


def _enable_pull(monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "efatura_pull_enabled", True)


@pytest.mark.parametrize("pgcode", ["40P01", "40001", "55P03"])
def test_n4_a_matched_save_that_loses_a_lock_clash_is_a_pt_pt_503(
    client: TestClient, db: Session, monkeypatch, pgcode
):
    user, headers = _user(db)
    document_id = _pull(db, user, _purchase("FT A/1")).created[0]
    monkeypatch.setattr("app.api.documents.lock_account", _raise(_db_error(pgcode)))

    response = client.patch(f"/api/documents/{document_id}", headers=headers, json={"vendor_nif": "500000000"})

    assert response.status_code == 503, response.text
    assert response.json()["detail"] == DB_BUSY_DETAIL
    assert response.headers["retry-after"] == "5"
    db.expire_all()
    assert db.get(Document, document_id).vendor_nif != "500000000"


def test_n4_a_delete_that_deadlocks_twice_is_a_pt_pt_503_and_keeps_the_row(
    client: TestClient, db: Session, monkeypatch
):
    user, headers = _user(db)
    document_id = _pull(db, user, _purchase("FT A/1")).created[0]
    monkeypatch.setattr("app.api.documents.detach_deleted_scan", _raise(_db_error("40P01")))

    response = client.delete(f"/api/documents/{document_id}", headers=headers)

    assert response.status_code == 503, response.text
    assert response.json()["detail"] == DB_BUSY_DETAIL
    db.expire_all()
    assert db.get(Document, document_id).deleted_at is None


def test_n4_a_lock_clash_in_any_handler_is_a_coded_pt_pt_503(client: TestClient, monkeypatch):
    monkeypatch.setattr("app.api.vat_sales.get_or_create_user", _raise(_db_error("55P03")))

    response = client.post(
        "/api/vat-sales",
        headers={"X-Mock-User-Id": "gil208-vat"},
        json={"period_type": "month", "year": 2026, "period_value": 3, "vat_amount": "12.30"},
    )

    assert response.status_code == 503, response.text
    body = response.json()
    assert body["detail"] == DB_BUSY_DETAIL
    assert body["error"]["code"] == "DATABASE_BUSY"
    assert response.headers["retry-after"] == "5"


def test_n4_a_dropped_connection_in_any_handler_is_a_pt_pt_503(client: TestClient, monkeypatch):
    monkeypatch.setattr("app.api.vat_sales.get_or_create_user", _raise(_db_error(dropped=True)))

    response = client.get("/api/vat-sales", headers={"X-Mock-User-Id": "gil208-vat"})

    assert response.status_code == 503, response.text
    assert response.json()["detail"] == DB_INTERRUPTED_DETAIL
    assert response.json()["error"]["code"] == "DATABASE_INTERRUPTED"


def test_n4_other_database_errors_are_still_a_500(client: TestClient, monkeypatch):
    monkeypatch.setattr("app.api.vat_sales.get_or_create_user", _raise(_db_error("08006")))

    response = client.get("/api/vat-sales", headers={"X-Mock-User-Id": "gil208-vat"})

    assert response.status_code == 500, response.text
    assert response.json()["error"]["code"] == "DATABASE_ERROR"


@pytest.mark.parametrize(
    "error",
    [_db_error(dropped=True), _db_error("25P03"), _db_error("57014")],
    ids=["idle-limit-closed-connection", "idle-limit-code", "statement-limit"],
)
def test_n5_a_pull_the_server_ended_shows_the_pull_timeout_copy(
    client: TestClient, db: Session, monkeypatch, error
):
    from app.api.efatura import PULL_TIMEOUT_DETAIL

    _enable_pull(monkeypatch)
    monkeypatch.setattr("app.api.efatura.import_purchases", _raise(error))

    response = client.post("/api/efatura/pull", json=PERIOD, headers={"X-Mock-User-Id": "gil208-pull"})

    assert response.status_code == 503, response.text
    assert response.json()["detail"] == PULL_TIMEOUT_DETAIL
    assert response.headers["retry-after"] == "10"


def test_n4_a_pull_that_deadlocks_on_the_account_is_a_pt_pt_503(client: TestClient, monkeypatch):
    _enable_pull(monkeypatch)
    monkeypatch.setattr("app.api.efatura.import_purchases", _raise(_db_error("40P01")))

    response = client.post("/api/efatura/pull", json=PERIOD, headers={"X-Mock-User-Id": "gil208-pull"})

    assert response.status_code == 503, response.text
    assert response.json()["detail"] == DB_BUSY_DETAIL

"""A hung e-Fatura pull holds the account lock for a bounded time, on Postgres 16 (GIL-207 B-2).

Postgres only. A pull stops after its first invoice and stays idle inside its
transaction, holding the account lock, as a stopped or stuck worker would.
A PATCH to a matched field must not wait for it without bound: it gets a 503
with the PT-PT retry copy after the edit wait, while an edit to an unmatched
field saves at once. The server ends the idle pull's session, which frees the
lock, so a retried edit saves before the pull would have woken up.
"""

from __future__ import annotations

import os
import sys
import threading
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_edited_at_rows as base  # noqa: E402

PULL_SLEEP = 50.0


def check_hung_pull(account: base.Account) -> None:
    from app.api.documents import EDIT_BUSY_DETAIL
    from app.services.efatura import (
        EDIT_LOCK_WAIT_SECONDS,
        LOCK_HOLDER_IDLE_SECONDS,
        import_purchases,
    )
    from sqlalchemy.orm import sessionmaker

    document_id = account.pull(base._invoice("FT A/7", "2.30")).created[0]
    hung = threading.Event()
    errors: list[BaseException] = []

    def stall(_invoice) -> None:
        hung.set()
        time.sleep(PULL_SLEEP)

    def pull() -> None:
        db = sessionmaker(bind=account.engine)()
        try:
            import_purchases(
                db,
                user_id=account.user_id,
                taxpayer_nif=base.TAXPAYER,
                invoices=[base._invoice("FT A/8", "4.60")],
                after_invoice=stall,
            )
            db.commit()
        except BaseException as exc:  # surfaced below
            errors.append(exc)
        finally:
            db.close()

    puller = threading.Thread(target=pull, daemon=True)
    started = time.monotonic()
    puller.start()
    assert hung.wait(10), "the pull never reached its first invoice"

    begun = time.monotonic()
    unmatched = account.patch(document_id, review_notes="visto")
    assert unmatched.status_code == 200, unmatched.text
    assert time.monotonic() - begun < 2, "an unmatched edit waited for the pull"

    begun = time.monotonic()
    busy = account.patch(document_id, vendor_nif=base.NIF)
    waited = time.monotonic() - begun
    assert busy.status_code == 503, busy.text
    assert busy.json()["detail"] == EDIT_BUSY_DETAIL, busy.text
    assert busy.headers.get("retry-after") == "10", busy.headers
    assert EDIT_LOCK_WAIT_SECONDS - 1 < waited < EDIT_LOCK_WAIT_SECONDS + 3, waited
    print(f"matched edit during a hung pull: 503 after {waited:.1f}s: {busy.json()['detail']}")

    while True:
        response = account.patch(document_id, vendor_nif=base.NIF)
        elapsed = time.monotonic() - started
        if response.status_code == 200:
            break
        assert response.status_code == 503, response.text
        assert elapsed < PULL_SLEEP, "the hung pull kept the lock until it woke up"
        time.sleep(0.5)
    assert LOCK_HOLDER_IDLE_SECONDS - 1 < elapsed < PULL_SLEEP - 5, elapsed
    print(f"server ended the idle pull; retried edit saved {elapsed:.1f}s after the pull hung")

    puller.join(PULL_SLEEP + 10)
    assert errors, "the hung pull committed after its session was ended"
    assert account.vat() == [base.Decimal("2.30")], account.rows()


def check_idle_pull_answer(account: base.Account) -> None:
    """GIL-208 N-5: a pull the idle limit ends is the PT-PT 503, not a generic 500.

    psycopg2 reports the server ending the session only as a closed connection.
    """
    import app.api.efatura as api
    import app.services.efatura as service
    from app.api.efatura import PULL_TIMEOUT_DETAIL

    idle = 2
    real_import, real_idle = api.import_purchases, service.LOCK_HOLDER_IDLE_SECONDS

    def stalled(db, **kwargs):
        return real_import(db, after_invoice=lambda _invoice: time.sleep(idle + 2), **kwargs)

    api.import_purchases, service.LOCK_HOLDER_IDLE_SECONDS = stalled, idle
    try:
        response = account.client.post(
            "/api/efatura/pull",
            headers=account.headers,
            json={"taxpayer_nif": base.TAXPAYER, "period_start": "2026-01-01", "period_end": "2026-12-31"},
        )
    finally:
        api.import_purchases, service.LOCK_HOLDER_IDLE_SECONDS = real_import, real_idle
    assert response.status_code == 503, response.text
    assert response.json()["detail"] == PULL_TIMEOUT_DETAIL, response.text
    assert response.headers.get("retry-after") == "10", response.headers
    print(f"pull ended by the idle limit: 503: {response.json()['detail']}")
    assert account.vat() == [base.Decimal("2.30")], account.rows()


def main() -> None:
    name = f"hungpull_{uuid.uuid4().hex[:8]}"
    try:
        url = base._recreate(name)
        os.environ["DATABASE_URL"] = url
        os.environ.setdefault("AUTH_MOCK_MODE", "true")
        os.environ.setdefault("MOCK_AUTH", "1")
        os.environ.setdefault("STORAGE_MOCK_MODE", "true")
        os.environ.setdefault("OCR_MOCK_MODE", "true")
        os.environ.setdefault("APP_DEBUG", "true")
        os.environ.setdefault("EFATURA_PULL_ENABLED", "true")
        sys.path.insert(0, str(base.BACKEND))
        base._migrate(url)
        from fastapi.testclient import TestClient

        from app.main import app

        with TestClient(app) as client:
            account = base.Account(url, client)
            check_hung_pull(account)
            check_idle_pull_answer(account)
        print("hung pull passed")
    finally:
        from app.core.database import engine

        engine.dispose()
        base._drop(name)


if __name__ == "__main__":
    main()

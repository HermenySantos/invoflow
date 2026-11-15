"""Waits on the account lock share one budget and never stall other accounts, on Postgres 16 (GIL-208).

Postgres only. Real uvicorn servers serve the API, as in production. The
script holds an account's lock from its own session, as a long e-Fatura pull
would, and checks:

- N-1: waiters for the same hold share one budget. A second save after the
  first one's 503, and a third pull after the second one's 503, are refused
  at once instead of waiting their own 10 s / 30 s again.
- N-2: a receipt upload and a new VAT-on-sales entry for the locked account
  do not wait for the pull.
- N-3: a 40-tab retry storm on the locked account answers quickly, and
  another account's reads, saves and /health stay fast on a single worker.
- N-4: four workers hammering one account with pulls, matched saves and
  deletes never answer a 500. A lock clash is a 503 with PT-PT copy.
"""

from __future__ import annotations

import os
import random
import signal
import sys
import threading
import time
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_edited_at_rows as base  # noqa: E402
from check_missing_document_lock import _free_port  # noqa: E402

TAXPAYER = "555555555"
PERIOD = {"taxpayer_nif": TAXPAYER, "period_start": "2026-01-01", "period_end": "2026-12-31"}
HOLD_SECONDS = 45.0
HAMMER_INVOICES = 300
HAMMER_SECONDS = 30.0


def _start_server(url: str, port: int, workers: int):
    import subprocess

    env = dict(
        os.environ,
        DATABASE_URL=url,
        AUTH_MOCK_MODE="true",
        MOCK_AUTH="1",
        STORAGE_MOCK_MODE="true",
        OCR_MOCK_MODE="true",
        APP_DEBUG="true",
        APP_ENV="development",
        EFATURA_PULL_ENABLED="true",
    )
    server = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn", "app.main:app",
            "--host", "127.0.0.1", "--port", str(port), "--workers", str(workers),
            "--log-level", "warning",
        ],
        cwd=base.BACKEND,
        env=env,
        start_new_session=True,
    )
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"http://127.0.0.1:{port}/health", timeout=1).status_code == 200:
                return server
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    _stop(server)
    raise SystemExit("uvicorn did not start")


def _stop(server) -> None:
    # SIGKILL on the master alone would leave its workers running.
    os.killpg(server.pid, signal.SIGKILL)
    server.wait()


def _timed(call):
    started = time.monotonic()
    try:
        try:
            response = call()
        except httpx.RemoteProtocolError:
            # uvicorn closed an idle keep-alive connection just as it was reused.
            response = call()
        return response.status_code, time.monotonic() - started, response
    except httpx.TimeoutException:
        return "timeout", time.monotonic() - started, None


class User:
    def __init__(self, api: str, url: str) -> None:
        clerk = f"storm-{uuid.uuid4().hex[:8]}"
        self.client = httpx.Client(base_url=api, headers={"X-Mock-User-Id": clerk}, timeout=90)
        assert self.client.get("/api/documents").status_code == 200
        from sqlalchemy import create_engine, text

        engine = create_engine(url)
        with engine.connect() as conn:
            self.user_id = conn.execute(
                text("SELECT id FROM users WHERE clerk_id = :clerk"), {"clerk": clerk}
            ).scalar_one()
        engine.dispose()

    def pull(self):
        return self.client.post("/api/efatura/pull", json=PERIOD)

    def documents(self) -> list[dict]:
        return self.client.get("/api/documents", params={"page_size": 100}).json()["documents"]

    def save(self, document_id: str, **fields):
        return self.client.patch(f"/api/documents/{document_id}", json=fields)

    def upload(self):
        issued = self.client.post(
            "/api/documents/upload-url", json={"filename": "r.jpg", "content_type": "image/jpeg"}
        )
        assert issued.status_code == 200, issued.text
        body = issued.json()
        put = self.client.put(body["upload_url"], content=_jpeg())
        assert put.status_code == 200, put.text
        return self.client.post(
            "/api/documents",
            json={"storage_key": body["storage_key"], "original_filename": "r.jpg", "mime_type": "image/jpeg"},
        )

    def vat_sales(self, month: int):
        return self.client.post(
            "/api/vat-sales",
            json={"period_type": "month", "year": 2026, "period_value": month, "vat_amount": "12.30"},
        )


def _jpeg() -> bytes:
    from io import BytesIO

    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", (8, 8), "white").save(buffer, "JPEG")
    return buffer.getvalue()


class Hold:
    """Hold the account lock from another session, as a long pull does."""

    def __init__(self, url: str, user_id: str, seconds: float) -> None:
        self.url, self.user_id, self.seconds = url, user_id, seconds
        self.held = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        from sqlalchemy import create_engine, text
        from sqlalchemy.orm import Session

        from app.services.efatura import PULL_LOCK_WAIT_SECONDS, lock_account

        engine = create_engine(self.url)
        with Session(engine) as db:
            lock_account(db, self.user_id, wait_seconds=PULL_LOCK_WAIT_SECONDS)
            self.held.set()
            try:
                db.execute(text("SELECT pg_sleep(:s)"), {"s": self.seconds})
            except Exception:
                pass
            db.rollback()
        engine.dispose()

    def __enter__(self):
        self.started = time.monotonic()
        self.thread.start()
        assert self.held.wait(10), "could not take the account lock"
        return self

    def __exit__(self, *exc) -> None:
        self.thread.join(self.seconds + 10)


def check_budget_and_storm(api: str, url: str) -> None:
    from app.api.documents import EDIT_BUSY_DETAIL
    from app.api.efatura import PULL_BUSY_DETAIL
    from app.services.efatura import EDIT_LOCK_WAIT_SECONDS, PULL_LOCK_WAIT_SECONDS

    owner, other = User(api, url), User(api, url)
    for user in (owner, other):
        assert user.pull().status_code == 200
    owned = [row["id"] for row in owner.documents()]
    others = [row["id"] for row in other.documents()]
    assert owned and others

    with Hold(url, owner.user_id, HOLD_SECONDS) as hold:
        # N-2: writers that do not take the account lock do not wait for it.
        for name, call in (("upload", owner.upload), ("vat-sales", lambda: owner.vat_sales(3))):
            status, seconds, response = _timed(call)
            assert status == 201, (name, status, response.text if response else None)
            assert seconds < 2, f"{name} waited {seconds:.1f}s for the pull"
            print(f"N-2 {name} during a held pull: {status} in {seconds:.2f}s")

        # N-1: the first save waits the edit budget, the retry does not wait again.
        status, first, response = _timed(lambda: owner.save(owned[0], vendor_nif=base.NIF))
        assert status == 503 and response.json()["detail"] == EDIT_BUSY_DETAIL, (status, response.text)
        assert first < EDIT_LOCK_WAIT_SECONDS + 2, first
        status, second, response = _timed(lambda: owner.save(owned[0], vendor_nif=base.NIF))
        assert status == 503 and response.json()["detail"] == EDIT_BUSY_DETAIL, (status, response.text)
        assert second < 2, f"the second save waited {second:.1f}s again"
        print(f"N-1 saves during a held pull: 503 after {first:.1f}s, retry 503 after {second:.2f}s")

        # N-1: pulls share the pull budget, counted from when the lock was taken.
        status, pull_wait, response = _timed(owner.pull)
        assert status == 503 and response.json()["detail"] == PULL_BUSY_DETAIL, (status, response.text)
        since_hold = time.monotonic() - hold.started
        assert since_hold < PULL_LOCK_WAIT_SECONDS + 3, since_hold
        waits = [pull_wait]
        for _ in range(2):
            status, seconds, response = _timed(owner.pull)
            assert status == 503 and response.json()["detail"] == PULL_BUSY_DETAIL, (status, response.text)
            waits.append(seconds)
        assert max(waits[1:]) < 2, f"later pulls waited again: {waits}"
        print("N-1 pulls during a held pull: " + ", ".join(f"503 after {w:.1f}s" for w in waits))

    with Hold(url, owner.user_id, 25.0):
        # N-3: a 40-tab storm on the locked account, another account keeps working.
        with ThreadPoolExecutor(max_workers=48) as pool:
            storm = [
                pool.submit(_timed, lambda i=i: owner.save(owned[i % len(owned)], vendor_nif=base.NIF))
                for i in range(40)
            ]
            time.sleep(1.0)
            probes = {
                "health": _timed(lambda: httpx.get(f"{api}/health", timeout=30)),
                "other list": _timed(lambda: other.client.get("/api/documents")),
                "other save": _timed(lambda: other.save(others[0], vendor_nif=base.NIF)),
                "other note": _timed(lambda: other.save(others[0], review_notes="visto")),
            }
            outcomes = [future.result() for future in storm]
        for name, (status, seconds, response) in probes.items():
            assert status == 200, (name, status, response.text if response else None)
            assert seconds < 2, f"{name} took {seconds:.1f}s during the storm"
        statuses = Counter(status for status, _, _ in outcomes)
        slowest = max(seconds for _, seconds, _ in outcomes)
        assert set(statuses) == {503}, statuses
        assert slowest < EDIT_LOCK_WAIT_SECONDS + 3, slowest
        fast = sum(1 for _, seconds, _ in outcomes if seconds < 2)
        assert fast >= 30, f"only {fast} of 40 storm saves were refused at once"
        print(
            f"N-3 40-tab storm: {dict(statuses)}, {fast} refused at once, slowest {slowest:.1f}s; "
            + ", ".join(f"{name} {seconds:.2f}s" for name, (_, seconds, _) in probes.items())
        )


def _hammer_invoices():
    return [base._invoice(f"FT H/{n}", f"{n % 50 + 1}.23") for n in range(1, HAMMER_INVOICES + 1)]


def _seed_scans(engine, user_id: str) -> None:
    """Scans the first pull links, so deleting one stores its invoice again as an AT row."""
    from datetime import datetime

    from sqlalchemy import text

    now = datetime.utcnow()
    with engine.begin() as conn:
        for invoice in _hammer_invoices():
            conn.execute(
                text(
                    "INSERT INTO documents ("
                    "id, user_id, status, storage_key, original_filename, mime_type, "
                    "vendor_nif, invoice_number, document_type, document_date, "
                    "net_amount, vat_amount, gross_amount, expense_category, created_at, updated_at"
                    ") VALUES ("
                    ":id, :user_id, 'ready', 'storm/scan.jpg', 'scan.jpg', 'image/jpeg', "
                    ":nif, :number, 'FT', :issued, :net, :vat, :gross, 'office', :now, :now)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "user_id": user_id,
                    "nif": invoice.issuer_nif,
                    "number": invoice.invoice_number,
                    "issued": invoice.issue_date,
                    "net": invoice.net_total,
                    "vat": invoice.tax_payable,
                    "gross": invoice.gross_total,
                    "now": now,
                },
            )


def check_hammer(api: str, url: str) -> None:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from sqlalchemy.exc import OperationalError

    from app.core.db_errors import sqlstate
    from app.services.efatura import AccountBusy, import_purchases

    owner = User(api, url)
    engine = create_engine(url)
    invoices = _hammer_invoices()

    def pull_in_process():
        db = sessionmaker(bind=engine)()
        try:
            import_purchases(db, user_id=owner.user_id, taxpayer_nif=TAXPAYER, invoices=invoices)
            db.commit()
            return "ok"
        except AccountBusy:
            return "busy"
        except OperationalError as exc:
            return f"error {sqlstate(exc)}"
        finally:
            db.close()

    _seed_scans(engine, owner.user_id)
    assert pull_in_process() == "ok"
    deadline = time.monotonic() + HAMMER_SECONDS
    statuses: Counter = Counter()
    failures: list[str] = []
    slowest: dict[str, float] = {}
    lock = threading.Lock()

    def puller() -> None:
        while time.monotonic() < deadline:
            outcome = pull_in_process()
            with lock:
                statuses[("long pull", outcome)] += 1
                if outcome == "error 40P01":
                    failures.append("long pull: deadlock")
            if outcome != "ok":
                time.sleep(0.2)

    def worker(seed: int) -> None:
        rng = random.Random(seed)
        while time.monotonic() < deadline:
            listed = owner.client.get("/api/documents", params={"page_size": 100, "page": rng.randint(1, 3)})
            rows = listed.json()["documents"] if listed.status_code == 200 else []
            action = rng.choice(["pull", "save", "save", "note", "delete", "delete", "delete"])
            target = rng.choice(rows)["id"] if rows else None
            if action == "pull" or target is None:
                action, call = "pull", owner.pull
            elif action == "save":
                call = lambda: owner.save(target, vendor_nif=rng.choice([base.NIF, "123456002"]))  # noqa: E731
            elif action == "note":
                call = lambda: owner.save(target, review_notes=f"n{rng.randint(0, 9)}")  # noqa: E731
            else:
                call = lambda: owner.client.delete(f"/api/documents/{target}")  # noqa: E731
            status, seconds, response = _timed(call)
            with lock:
                slowest[action] = max(slowest.get(action, 0.0), seconds)
                if response is None:
                    failures.append(f"{action}: no answer after {seconds:.1f}s")
                    continue
                statuses[(action, response.status_code)] += 1
                if response.status_code >= 500 and response.status_code != 503:
                    failures.append(f"{action}: {response.status_code} {response.text[:200]}")
                if response.status_code == 503:
                    detail = response.json().get("detail", "")
                    if not detail or "error occurred" in detail:
                        failures.append(f"{action}: 503 without PT-PT copy: {detail}")

    with ThreadPoolExecutor(max_workers=12) as pool:
        jobs = [pool.submit(puller) for _ in range(2)] + [pool.submit(worker, seed) for seed in range(10)]
        for job in jobs:
            job.result()
    engine.dispose()
    print(f"N-4 4-worker hammer: {dict(sorted(statuses.items()))}")
    print("N-4 slowest: " + ", ".join(f"{action} {seconds:.1f}s" for action, seconds in sorted(slowest.items())))
    assert not failures, failures[:10]


def main() -> None:
    name = f"lockstorm_{uuid.uuid4().hex[:8]}"
    url = base._recreate(name)
    servers = []
    try:
        os.environ["DATABASE_URL"] = url
        sys.path.insert(0, str(base.BACKEND))
        base._migrate(url)
        port = _free_port()
        servers.append(_start_server(url, port, workers=1))
        check_budget_and_storm(f"http://127.0.0.1:{port}", url)
        _stop(servers.pop())
        port = _free_port()
        servers.append(_start_server(url, port, workers=4))
        check_hammer(f"http://127.0.0.1:{port}", url)
        print("lock storm passed")
    finally:
        for server in servers:
            _stop(server)
        from app.core.database import engine

        engine.dispose()
        base._drop(name)


if __name__ == "__main__":
    main()

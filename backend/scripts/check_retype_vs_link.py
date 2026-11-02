"""A retype racing an e-Fatura link must not leave an NC scan on an FT invoice.

Postgres only. Link first, and the retype waits on the scan row, then returns
422 and the scan stays FT with one link. Retype first, and the import waits,
then the scan stays NC with no link and the invoice is its own AT row.
The scan numbers carry no series token, so an unlinked row would accept NC.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker


BACKEND = Path(__file__).resolve().parents[1]
ISSUER_NIF = "500829993"
TAXPAYER_NIF = "555555555"
LINK_NUMBER = "LJA/101"
RETYPE_NUMBER = "LJA/102"
MISMATCH_DETAIL = "O n.º do documento não corresponde ao tipo indicado."
AT_MIME = "application/vnd.invoflow.efatura%"
# The other side has to reach the row lock before this window counts.
ARRIVE_SECONDS = 10
WAIT_SECONDS = 2
LOG_PATH = Path("/tmp/invoflow-retype-vs-link.log")


def _admin_url():
    url = os.environ.get("DATABASE_URL", "")
    if not url.startswith("postgres"):
        raise SystemExit("DATABASE_URL must be a Postgres URL")
    return make_url(url)


def _recreate(name: str) -> str:
    admin = _admin_url().set(database="postgres")
    engine = create_engine(admin, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    engine.dispose()
    return _admin_url().set(database=name).render_as_string(hide_password=False)


def _drop(name: str) -> None:
    admin = _admin_url().set(database="postgres")
    engine = create_engine(admin, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        conn.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = :name AND pid <> pg_backend_pid()"
            ),
            {"name": name},
        )
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    engine.dispose()


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _invoice(number: str):
    sys.path.insert(0, str(BACKEND))
    from app.services.efatura import EFaturaInvoice, VatLine

    return EFaturaInvoice(
        document_type="FT",
        invoice_number=number,
        issue_date=date(2026, 3, 2),
        issuer_nif=ISSUER_NIF,
        acquirer_nif=TAXPAYER_NIF,
        acquirer_country="PT",
        fiscal_status="normal",
        lines=(VatLine("IVA", "PT", "NOR", Decimal("23"), Decimal("10"), Decimal("2.30"), None),),
        tax_payable=Decimal("2.30"),
        net_total=Decimal("10"),
        gross_total=Decimal("12.30"),
        issuer_name="Loja",
    )


def _seed(url: str) -> tuple[str, str, str, str]:
    from alembic import command
    from alembic.config import Config

    os.environ["DATABASE_URL"] = url
    sys.path.insert(0, str(BACKEND))
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    from app.schemas.document import invoice_series_prefix

    for number in (LINK_NUMBER, RETYPE_NUMBER):
        prefix = invoice_series_prefix(number)
        assert prefix is None, (
            f"{number} has series token {prefix}; an unlinked retype would be refused without a link"
        )
    engine = create_engine(url)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    user_id = str(uuid.uuid4())
    clerk_id = f"test-user-{user_id[:8]}"
    scans = {}
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO users (id, clerk_id, email, created_at, updated_at) "
                "VALUES (:id, :clerk, :email, :now, :now)"
            ),
            {"id": user_id, "clerk": clerk_id, "email": "retype@example.com", "now": now},
        )
        for key, number, filename in (
            ("link", LINK_NUMBER, "link.jpg"),
            ("retype", RETYPE_NUMBER, "retype.jpg"),
        ):
            scan_id = str(uuid.uuid4())
            conn.execute(
                text(
                    "INSERT INTO documents ("
                    "id, user_id, status, storage_key, original_filename, mime_type, "
                    "vendor_nif, invoice_number, document_type, document_date, "
                    "net_amount, vat_amount, gross_amount, expense_category, "
                    "ocr_raw_response, created_at, updated_at"
                    ") VALUES ("
                    ":id, :user_id, 'needs_review', :storage_key, :filename, 'image/jpeg', "
                    ":nif, :number, 'FT', '2026-03-02', "
                    "8.13, 1.87, 10.00, 'office', :raw, :now, :now)"
                ),
                {
                    "id": scan_id,
                    "user_id": user_id,
                    "storage_key": f"retype/{filename}",
                    "filename": filename,
                    "nif": ISSUER_NIF,
                    "number": number,
                    "raw": json.dumps({"text": "scan"}),
                    "now": now,
                },
            )
            scans[key] = scan_id
    engine.dispose()
    return clerk_id, user_id, scans["link"], scans["retype"]


def _activity(engine) -> str:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT pid, state, coalesce(wait_event_type, '') AS wait_type, "
                "coalesce(wait_event, '') AS wait_event, left(query, 160) AS query "
                "FROM pg_stat_activity "
                "WHERE datname = current_database() AND pid <> pg_backend_pid() "
                "AND state IS NOT NULL AND state <> 'idle'"
            )
        ).mappings().all()
    return "; ".join(
        f"{row['pid']} {row['state']} {row['wait_type']}.{row['wait_event']} {row['query']}"
        for row in rows
    ) or "no active sessions"


def _waiting(engine) -> int:
    with engine.connect() as conn:
        return int(
            conn.execute(
                text(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE datname = current_database() "
                    "AND wait_event_type = 'Lock' "
                    "AND pid <> pg_backend_pid()"
                )
            ).scalar()
        )


def _assert_blocked(engine, thread: threading.Thread, label: str, outcome: dict | None = None) -> None:
    # Count the two seconds only after the other side is waiting on the row.
    # A request that has not reached Postgres yet is not evidence of the lock.
    def detail() -> str:
        return _outcome_text(outcome) if outcome else ""

    deadline = time.monotonic() + ARRIVE_SECONDS
    while time.monotonic() < deadline:
        if not thread.is_alive():
            raise AssertionError(f"{label} finished while the other side held the scan: {detail()}")
        if _waiting(engine) >= 1:
            break
        time.sleep(0.05)
    else:
        raise AssertionError(f"{label} did not reach the scan row lock: {_activity(engine)}")
    time.sleep(WAIT_SECONDS)
    if not thread.is_alive():
        raise AssertionError(f"{label} finished while the other side held the scan: {detail()}")
    if _waiting(engine) < 1:
        raise AssertionError(
            f"{label} left the scan row lock before the other side committed: {_activity(engine)}"
        )


def _outcome_text(outcome: dict) -> str:
    if "error" in outcome:
        return repr(outcome["error"])
    if "result" in outcome:
        result = outcome["result"]
        return f"linked {result.linked_existing} created {result.created}"
    body = outcome.get("body")
    detail = body.get("detail") if isinstance(body, dict) else body
    kind = body.get("document_type") if isinstance(body, dict) else None
    return f"status {outcome.get('status')} detail {detail!r} type {kind!r}"


def _patch(port: int, clerk_id: str, scan_id: str, outcome: dict) -> None:
    payload = json.dumps({"document_type": "NC"}).encode()
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/documents/{scan_id}",
        data=payload,
        method="PATCH",
        headers={
            "Content-Type": "application/json",
            "X-Mock-User-Id": clerk_id,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
            outcome["status"] = response.status
            outcome["body"] = json.loads(raw.decode())
    except urllib.error.HTTPError as exc:
        outcome["status"] = exc.code
        outcome["body"] = json.loads(exc.read().decode())
    except Exception as exc:
        outcome["error"] = exc


def _import(url: str, user_id: str, number: str, errors: list, outcome: dict) -> None:
    os.environ["DATABASE_URL"] = url
    sys.path.insert(0, str(BACKEND))
    from app.services.efatura import import_purchases

    engine = create_engine(url)
    db = sessionmaker(bind=engine)()
    try:
        outcome["result"] = import_purchases(
            db,
            user_id=user_id,
            taxpayer_nif=TAXPAYER_NIF,
            invoices=[_invoice(number)],
        )
        db.commit()
    except Exception as exc:
        errors.append(exc)
        outcome["error"] = exc
        db.rollback()
    finally:
        db.close()
        engine.dispose()


def _state(engine, scan_id: str, number: str) -> dict:
    with engine.connect() as conn:
        scan = conn.execute(
            text(
                "SELECT document_type, invoice_number FROM documents "
                "WHERE id = :id AND deleted_at IS NULL"
            ),
            {"id": scan_id},
        ).one()
        links = conn.execute(
            text("SELECT count(*) FROM efatura_links WHERE document_id = :id"),
            {"id": scan_id},
        ).scalar()
        at_rows = conn.execute(
            text(
                "SELECT id, document_type FROM documents "
                "WHERE deleted_at IS NULL AND id <> :id AND invoice_number = :number "
                "AND mime_type LIKE :mime"
            ),
            {"id": scan_id, "number": number, "mime": AT_MIME},
        ).all()
        ft_rows = conn.execute(
            text(
                "SELECT count(*) FROM documents "
                "WHERE deleted_at IS NULL AND invoice_number = :number AND document_type = 'FT'"
            ),
            {"number": number},
        ).scalar()
    return {
        "type": scan.document_type,
        "number": scan.invoice_number,
        "links": int(links),
        "at_rows": [(row.id, row.document_type) for row in at_rows],
        "ft_rows": int(ft_rows),
    }


def _case_link_first(url: str, port: int, clerk_id: str, user_id: str, scan_id: str, locks) -> None:
    from app.services.efatura import import_purchases

    outcome: dict = {}
    holder: dict = {"thread": None}
    engine = create_engine(url)
    db = sessionmaker(bind=engine)()
    try:
        def after_invoice(_invoice) -> None:
            holder["thread"] = threading.Thread(
                target=_patch, args=(port, clerk_id, scan_id, outcome)
            )
            holder["thread"].start()
            _assert_blocked(locks, holder["thread"], "link-first retype", outcome)

        result = import_purchases(
            db,
            user_id=user_id,
            taxpayer_nif=TAXPAYER_NIF,
            invoices=[_invoice(LINK_NUMBER)],
            after_invoice=after_invoice,
        )
        db.commit()
        holder["thread"].join(timeout=30)
        assert not holder["thread"].is_alive(), _outcome_text(outcome)
        assert "error" not in outcome, outcome["error"]
        assert outcome["status"] == 422, _outcome_text(outcome)
        assert outcome["body"]["detail"] == MISMATCH_DETAIL, _outcome_text(outcome)
        assert result.linked_existing == (scan_id,), result
        assert result.created == (), result
        state = _state(locks, scan_id, LINK_NUMBER)
        assert state["type"] == "FT", state
        assert state["number"] == LINK_NUMBER, state
        assert state["links"] == 1, state
        assert state["at_rows"] == [], state
        assert state["ft_rows"] == 1, state
    finally:
        db.close()
        engine.dispose()
        thread = holder["thread"]
        if thread is not None:
            thread.join(timeout=15)


def _case_retype_first(url: str, user_id: str, scan_id: str, locks) -> None:
    engine = create_engine(url)
    nc = sessionmaker(bind=engine)()
    errors: list = []
    outcome: dict = {}
    importer = None
    try:
        # Stands in for the PATCH. The row lock is held and the type is NC,
        # and this transaction stays open until the import is shown to be blocked.
        locked = nc.execute(
            text("SELECT id FROM documents WHERE id = :id FOR UPDATE"),
            {"id": scan_id},
        ).scalar()
        assert locked == scan_id, locked
        updated = nc.execute(
            text("UPDATE documents SET document_type = 'NC' WHERE id = :id"),
            {"id": scan_id},
        )
        assert updated.rowcount == 1, updated.rowcount
        importer = threading.Thread(
            target=_import, args=(url, user_id, RETYPE_NUMBER, errors, outcome)
        )
        importer.start()
        _assert_blocked(locks, importer, "retype-first import", outcome)
        nc.commit()
        importer.join(timeout=30)
        assert not importer.is_alive(), "import did not finish after the retype committed"
        if errors:
            raise errors[0]
        result = outcome["result"]
        assert result.linked_existing == (), result
        assert len(result.created) == 1, result
        state = _state(locks, scan_id, RETYPE_NUMBER)
        assert state["type"] == "NC", state
        assert state["number"] == RETYPE_NUMBER, state
        assert state["links"] == 0, state
        assert state["at_rows"] == [(result.created[0], "FT")], state
        assert state["ft_rows"] == 1, state
        with locks.connect() as conn:
            link = conn.execute(
                text(
                    "SELECT outcome, document_id FROM efatura_links WHERE document_id = :id"
                ),
                {"id": result.created[0]},
            ).one()
        assert (link.outcome, link.document_id) == ("created", result.created[0]), link
    finally:
        nc.close()
        engine.dispose()
        if importer is not None:
            importer.join(timeout=15)


def main() -> None:
    name = f"migretype_{uuid.uuid4().hex[:8]}"
    port = _free_port()
    server = None
    log_file = None
    locks = None
    try:
        url = _recreate(name)
        clerk_id, user_id, link_scan, retype_scan = _seed(url)
        env = os.environ.copy()
        env.update(
            {
                "DATABASE_URL": url,
                "APP_ENV": "development",
                "MOCK_AUTH": "1",
                "AUTH_MOCK_MODE": "true",
                "STORAGE_MOCK_MODE": "true",
                "OCR_MOCK_MODE": "true",
                "APP_DEBUG": "true",
            }
        )
        log_file = open(LOG_PATH, "w")
        server = subprocess.Popen(
            [
                sys.executable, "-m", "uvicorn", "app.main:app",
                "--workers", "4", "--host", "127.0.0.1", "--port", str(port),
            ],
            cwd=BACKEND,
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )
        deadline = time.time() + 30
        while time.time() < deadline:
            if server.poll() is not None:
                log_file.flush()
                raise SystemExit(LOG_PATH.read_text()[-4000:])
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as response:
                    if response.status == 200:
                        break
            except (urllib.error.URLError, TimeoutError):
                time.sleep(0.2)
        else:
            log_file.flush()
            raise SystemExit("uvicorn did not become ready\n" + LOG_PATH.read_text()[-4000:])

        locks = create_engine(url)
        _case_link_first(url, port, clerk_id, user_id, link_scan, locks)
        _case_retype_first(url, user_id, retype_scan, locks)
        print("retype versus link passed")
    finally:
        if locks is not None:
            locks.dispose()
        if server is not None and server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
        if log_file is not None:
            log_file.close()
        _drop(name)


if __name__ == "__main__":
    main()

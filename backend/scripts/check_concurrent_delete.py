"""Parallel DELETEs of one linked scan restore the AT invoice once.

Postgres only. Several uvicorn workers issue the delete at the same time.
Exactly one request returns 204. The others return 404. One AT row and one
efatura_unlink audit entry remain.
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
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


BACKEND = Path(__file__).resolve().parents[1]
WORKERS = 4
DELETES = 8


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


def _payload() -> str:
    return json.dumps(
        {
            "document_type": "FT",
            "invoice_number": "FT 2026/101",
            "issue_date": "2026-03-02",
            "issuer_nif": "500829993",
            "issuer_name": "Loja",
            "acquirer_nif": "555555555",
            "acquirer_country": "PT",
            "fiscal_status": "normal",
            "atcud": "CONC160",
            "lines": [
                {
                    "tax_type": "IVA",
                    "region": "PT",
                    "tax_code": "NOR",
                    "percentage": "23.00",
                    "taxable": "10.00",
                    "tax": "2.30",
                    "exemption_code": None,
                }
            ],
            "tax_payable": "2.30",
            "net_total": "10.00",
            "gross_total": "12.30",
        }
    )


def _seed(url: str) -> tuple[str, str]:
    from alembic import command
    from alembic.config import Config

    # env.py follows DATABASE_URL, not the URL on the Config object.
    os.environ["DATABASE_URL"] = url
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    engine = create_engine(url)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    user_id = str(uuid.uuid4())
    scan_id = str(uuid.uuid4())
    clerk_id = f"test-user-{user_id[:8]}"
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO users (id, clerk_id, email, created_at, updated_at) "
                "VALUES (:id, :clerk, :email, :now, :now)"
            ),
            {
                "id": user_id,
                "clerk": clerk_id,
                "email": "conc@example.com",
                "now": now,
            },
        )
        conn.execute(
            text(
                "INSERT INTO documents ("
                "id, user_id, status, storage_key, original_filename, mime_type, "
                "vendor_nif, invoice_number, document_type, document_date, "
                "net_amount, vat_amount, gross_amount, expense_category, "
                "ocr_raw_response, created_at, updated_at"
                ") VALUES ("
                ":id, :user_id, 'ready', 'conc/scan.jpg', 'scan.jpg', 'image/jpeg', "
                "'500829993', 'FT 2026/101', 'FT', '2026-03-02', "
                "8.13, 1.87, 10.00, 'office', :raw, :now, :now)"
            ),
            {
                "id": scan_id,
                "user_id": user_id,
                "raw": json.dumps({"text": "scan"}),
                "now": now,
            },
        )
        conn.execute(
            text(
                "INSERT INTO efatura_links ("
                "id, user_id, source_key, role, outcome, document_id, fiscal_status, "
                "payload_json, created_at, updated_at"
                ") VALUES ("
                ":id, :user_id, 'atcud:CONC160', 'acquirer', 'linked_existing', "
                ":document_id, 'normal', :payload, :now, :now)"
            ),
            {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "document_id": scan_id,
                "payload": _payload(),
                "now": now,
            },
        )
    engine.dispose()
    return clerk_id, scan_id


def _delete(port: int, clerk_id: str, scan_id: str, barrier: threading.Barrier, codes: list[int]) -> None:
    barrier.wait()
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/documents/{scan_id}",
        method="DELETE",
        headers={"X-Mock-User-Id": clerk_id},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            codes.append(response.status)
    except urllib.error.HTTPError as exc:
        codes.append(exc.code)


def main() -> None:
    name = f"migconc_{uuid.uuid4().hex[:8]}"
    port = _free_port()
    server = None
    try:
        url = _recreate(name)
        clerk_id, scan_id = _seed(url)
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
        log_path = Path("/tmp/invoflow-concurrent-delete.log")
        log_file = open(log_path, "w")
        server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--workers",
                str(WORKERS),
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
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
                raise SystemExit(log_path.read_text()[-4000:])
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as response:
                    if response.status == 200:
                        break
            except (urllib.error.URLError, TimeoutError):
                time.sleep(0.2)
        else:
            log_file.flush()
            raise SystemExit("uvicorn did not become ready\n" + log_path.read_text()[-4000:])

        codes: list[int] = []
        barrier = threading.Barrier(DELETES)
        threads = [
            threading.Thread(target=_delete, args=(port, clerk_id, scan_id, barrier, codes))
            for _ in range(DELETES)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        engine = create_engine(url)
        with engine.connect() as conn:
            live = conn.execute(
                text(
                    "SELECT count(*) FROM documents WHERE deleted_at IS NULL "
                    "AND invoice_number = 'FT 2026/101'"
                )
            ).scalar()
            audits = conn.execute(
                text(
                    "SELECT count(*) FROM audit_logs WHERE entity_id = :id AND action = 'efatura_unlink'"
                ),
                {"id": scan_id},
            ).scalar()
            vats = conn.execute(
                text(
                    "SELECT count(*) FROM documents WHERE deleted_at IS NULL "
                    "AND invoice_number = 'FT 2026/101' AND vat_amount = 2.30"
                )
            ).scalar()
        engine.dispose()
        assert sorted(codes) == [204] + [404] * (DELETES - 1), codes
        assert live == 1, live
        assert vats == 1, vats
        assert audits == 1, audits
        print("concurrent delete passed")
    finally:
        if server is not None and server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
        if "log_file" in locals():
            log_file.close()
        _drop(name)


if __name__ == "__main__":
    main()

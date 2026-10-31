"""A delete overlapping an e-Fatura pull of a two-link scan must not deadlock.

Postgres only. The pull updates the higher link id first, then filler invoices,
then the lower link id. The delete runs during that pull. Both finish, and the
invoice is one AT row.
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


def _invoice_payload(number: str, atcud: str | None) -> str:
    payload = {
        "document_type": "FT",
        "invoice_number": number,
        "issue_date": "2026-03-02",
        "issuer_nif": "500829993",
        "issuer_name": "Loja",
        "acquirer_nif": "555555555",
        "acquirer_country": "PT",
        "fiscal_status": "normal",
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
    if atcud:
        payload["atcud"] = atcud
    return json.dumps(payload)


def _seed(url: str) -> tuple[str, str]:
    from alembic import command
    from alembic.config import Config

    os.environ["DATABASE_URL"] = url
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    engine = create_engine(url)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    user_id = str(uuid.uuid4())
    scan_id = str(uuid.uuid4())
    clerk_id = f"test-user-{user_id[:8]}"
    low_link = "00000000-0000-4000-8000-0000000000a1"
    high_link = "fffffff0-0000-4000-8000-0000000000b2"
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO users (id, clerk_id, email, created_at, updated_at) "
                "VALUES (:id, :clerk, :email, :now, :now)"
            ),
            {"id": user_id, "clerk": clerk_id, "email": "pull@example.com", "now": now},
        )
        conn.execute(
            text(
                "INSERT INTO documents ("
                "id, user_id, status, storage_key, original_filename, mime_type, "
                "vendor_nif, invoice_number, document_type, document_date, "
                "net_amount, vat_amount, gross_amount, expense_category, "
                "ocr_raw_response, created_at, updated_at"
                ") VALUES ("
                ":id, :user_id, 'ready', 'pull/scan.jpg', 'scan.jpg', 'image/jpeg', "
                "'500829993', 'FT D/1', 'FT', '2026-03-02', "
                "8.13, 1.87, 10.00, 'office', :raw, :now, :now)"
            ),
            {"id": scan_id, "user_id": user_id, "raw": json.dumps({"text": "scan"}), "now": now},
        )
        for link_id, source_key, payload in (
            (low_link, "doc:500829993:FT:ft d/1", _invoice_payload("FT D/1", None)),
            (high_link, "atcud:PULL160", _invoice_payload("FT D/1", "PULL160")),
        ):
            conn.execute(
                text(
                    "INSERT INTO efatura_links ("
                    "id, user_id, source_key, role, outcome, document_id, fiscal_status, "
                    "payload_json, created_at, updated_at"
                    ") VALUES ("
                    ":id, :user_id, :source_key, 'acquirer', 'linked_existing', "
                    ":document_id, 'normal', :payload, :now, :now)"
                ),
                {
                    "id": link_id,
                    "user_id": user_id,
                    "source_key": source_key,
                    "document_id": scan_id,
                    "payload": payload,
                    "now": now,
                },
            )
    engine.dispose()
    return clerk_id, scan_id


def _pull(url: str, errors: list[BaseException]) -> None:
    os.environ["DATABASE_URL"] = url
    sys.path.insert(0, str(BACKEND))
    from app.services.efatura import EFaturaInvoice, VatLine, import_purchases

    def invoice(number: str, atcud: str | None) -> EFaturaInvoice:
        return EFaturaInvoice(
            document_type="FT",
            invoice_number=number,
            issue_date=date(2026, 3, 2),
            issuer_nif="500829993",
            acquirer_nif="555555555",
            acquirer_country="PT",
            fiscal_status="normal",
            lines=(VatLine("IVA", "PT", "NOR", Decimal("23"), Decimal("10"), Decimal("2.30"), None),),
            tax_payable=Decimal("2.30"),
            net_total=Decimal("10"),
            gross_total=Decimal("12.30"),
            atcud=atcud,
            issuer_name="Loja",
        )

    # Higher link id first, then fillers, then the lower link id.
    invoices = [invoice("FT D/1", "PULL160")]
    invoices.extend(invoice(f"FT FILL/{index}", None) for index in range(12))
    invoices.append(invoice("FT D/1", None))
    engine = create_engine(url)
    db = sessionmaker(bind=engine)()
    try:
        import_purchases(
            db,
            user_id=_user_id(engine),
            taxpayer_nif="555555555",
            invoices=invoices,
            after_invoice=lambda _invoice: time.sleep(0.05),
        )
        db.commit()
    except Exception as exc:
        errors.append(exc)
    finally:
        db.close()
        engine.dispose()


def _user_id(engine) -> str:
    with engine.connect() as conn:
        return conn.execute(text("SELECT id FROM users LIMIT 1")).scalar()


def main() -> None:
    name = f"migpull_{uuid.uuid4().hex[:8]}"
    port = _free_port()
    server = None
    log_file = None
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
        log_file = open("/tmp/invoflow-delete-vs-pull.log", "w")
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
                raise SystemExit(Path("/tmp/invoflow-delete-vs-pull.log").read_text()[-4000:])
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as response:
                    if response.status == 200:
                        break
            except (urllib.error.URLError, TimeoutError):
                time.sleep(0.2)
        else:
            log_file.flush()
            raise SystemExit("uvicorn did not become ready")

        errors: list[BaseException] = []
        puller = threading.Thread(target=_pull, args=(url, errors))
        puller.start()
        time.sleep(0.08)
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/documents/{scan_id}",
            method="DELETE",
            headers={"X-Mock-User-Id": clerk_id},
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                status = response.status
        except urllib.error.HTTPError as exc:
            status = exc.code
        puller.join()
        if errors:
            raise errors[0]

        engine = create_engine(url)
        with engine.connect() as conn:
            live = conn.execute(
                text(
                    "SELECT count(*) FROM documents WHERE deleted_at IS NULL AND invoice_number = 'FT D/1'"
                )
            ).scalar()
            audits = conn.execute(
                text(
                    "SELECT count(*) FROM audit_logs WHERE entity_id = :id AND action = 'efatura_unlink'"
                ),
                {"id": scan_id},
            ).scalar()
        engine.dispose()
        assert status == 204, status
        assert live == 1, live
        assert audits == 1, audits
        print("delete versus pull passed")
    finally:
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

"""Migration 014 splits rows the casefolded identity merged, on Postgres.

Refuses sqlite. Alembic's env.py reads DATABASE_URL, so the check runs in a
child process pointed at the database it creates.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


BACKEND = Path(__file__).resolve().parents[1]
HEAD = "014_series_case_identity"
BEFORE = "013_recompute_identity"
NIF = "296123456"
AT_MIME = "application/vnd.invoflow.efatura+json"
AT_RAW = '{"source":"efatura"}'


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
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    engine.dispose()


def _cfg():
    from alembic.config import Config

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])
    return cfg


def _version(conn) -> str:
    return conn.execute(text("SELECT version_num FROM alembic_version")).scalar()


def _indexdef(conn) -> str:
    indexdef = conn.execute(
        text("SELECT indexdef FROM pg_indexes WHERE indexname = 'uq_documents_at_invoice_identity'")
    ).scalar()
    assert indexdef and "UNIQUE" in indexdef.upper()
    assert "deleted_at IS NULL" in indexdef
    return indexdef


def _payload(number: str) -> str:
    return json.dumps(
        {
            "document_type": "FT",
            "invoice_number": number,
            "issue_date": "2026-04-01",
            "issuer_nif": NIF,
            "issuer_name": "Loja",
            "acquirer_nif": "123456789",
            "fiscal_status": "normal",
            "net_total": "10.00",
            "gross_total": "12.30",
            "lines": [{"tax_type": "IVA", "tax": "2.30", "percentage": "23.00"}],
        }
    )


def _user(conn, now) -> str:
    user_id = str(uuid.uuid4())
    conn.execute(
        text(
            "INSERT INTO users (id, clerk_id, email, created_at, updated_at) "
            "VALUES (:id, :clerk_id, 'mig014@example.com', :now, :now)"
        ),
        {"id": user_id, "clerk_id": f"mig014-{user_id[:8]}", "now": now},
    )
    return user_id


def _document(conn, *, user_id, number, identity, created, deleted=None, scan=False) -> str:
    document_id = str(uuid.uuid4())
    conn.execute(
        text(
            "INSERT INTO documents ("
            "id, user_id, status, storage_key, original_filename, mime_type, "
            "invoice_number, document_type, vendor_nif, net_amount, vat_amount, "
            "gross_amount, document_date, ocr_raw_response, at_invoice_identity, "
            "deleted_at, created_at, updated_at"
            ") VALUES ("
            ":id, :user_id, :status, :key, :filename, :mime, :number, 'FT', :nif, "
            "10.00, 2.30, 12.30, '2026-04-01', :raw, :identity, :deleted, :created, :created)"
        ),
        {
            "id": document_id,
            "user_id": user_id,
            "status": "ready" if scan else "needs_review",
            "key": f"scan/{document_id}.jpg" if scan else f"efatura/{document_id}",
            "filename": "scan.jpg" if scan else "at.efatura",
            "mime": "image/jpeg" if scan else AT_MIME,
            "number": number,
            "nif": NIF,
            "raw": '{"text": "scan"}' if scan else AT_RAW,
            "identity": identity,
            "deleted": deleted,
            "created": created,
        },
    )
    return document_id


def _link(conn, *, user_id, document_id, number, key, outcome, now) -> str:
    link_id = str(uuid.uuid4())
    conn.execute(
        text(
            "INSERT INTO efatura_links ("
            "id, user_id, source_key, role, outcome, document_id, fiscal_status, "
            "payload_json, created_at, updated_at"
            ") VALUES (:id, :user_id, :key, 'acquirer', :outcome, :document_id, 'normal', "
            ":payload, :now, :now)"
        ),
        {
            "id": link_id,
            "user_id": user_id,
            "key": key,
            "outcome": outcome,
            "document_id": document_id,
            "payload": _payload(number),
            "now": now,
        },
    )
    return link_id


def _audit(conn, *, user_id, document_id, action, changes, now) -> None:
    conn.execute(
        text(
            "INSERT INTO audit_logs (id, entity_type, entity_id, user_id, action, source, "
            "changes_json, created_at) VALUES (:id, 'document', :entity, :user_id, :action, "
            "'efatura', :changes, :now)"
        ),
        {
            "id": str(uuid.uuid4()),
            "entity": document_id,
            "user_id": user_id,
            "action": action,
            "changes": json.dumps(changes),
            "now": now,
        },
    )


def _snapshot(conn):
    def rows(sql: str):
        return tuple(
            tuple(None if value is None else str(value) for value in row)
            for row in conn.execute(text(sql))
        )

    return (
        rows(
            "SELECT id, invoice_number, status, at_invoice_identity, deleted_at, "
            "updated_at, xmin::text FROM documents ORDER BY id"
        ),
        rows(
            "SELECT id, source_key, document_id, outcome, updated_at, xmin::text "
            "FROM efatura_links ORDER BY id"
        ),
        rows("SELECT id, entity_id, action, changes_json, xmin::text FROM audit_logs ORDER BY id"),
    )


def _child() -> None:
    from alembic import command

    source = (BACKEND / "alembic/versions/014_series_case_identity.py").read_text()
    assert "import app" not in source
    assert "from app." not in source
    cfg = _cfg()
    command.upgrade(cfg, BEFORE)
    engine = create_engine(os.environ["DATABASE_URL"])
    base = datetime(2026, 4, 1, 8, 0, 0)
    later = base + timedelta(hours=2)
    with engine.begin() as conn:
        assert _version(conn) == BEFORE
        user_id = _user(conn, base)
        # The U-1 merge: AT 'FT a/5' was linked into the 'FT A/5' row.
        merged = _document(conn, user_id=user_id, number="FT A/5", identity=f"{NIF}|FT|ft a/5", created=base)
        _link(conn, user_id=user_id, document_id=merged, number="FT A/5", key="atcud:A5", outcome="created", now=base)
        merged_lower = _link(
            conn, user_id=user_id, document_id=merged, number="FT a/5", key="atcud:a5",
            outcome="linked_existing", now=later,
        )
        # 013 soft-deleted 'FT b/7' as a duplicate of 'FT B/7' and moved its link.
        keeper = _document(conn, user_id=user_id, number="FT B/7", identity=f"{NIF}|FT|ft b/7", created=base)
        dropped = _document(
            conn, user_id=user_id, number="FT b/7", identity=f"{NIF}|FT|ft b/7", created=later, deleted=later,
        )
        _link(conn, user_id=user_id, document_id=keeper, number="FT B/7", key="atcud:B7", outcome="created", now=base)
        dropped_link = _link(
            conn, user_id=user_id, document_id=keeper, number="FT b/7", key="atcud:b7", outcome="created", now=later,
        )
        _audit(
            conn, user_id=user_id, document_id=dropped, action="efatura_dedupe",
            changes={"kept_document_id": {"old": None, "new": keeper}}, now=later,
        )
        # A scan linked to both case series keeps its own.
        scan = _document(conn, user_id=user_id, number="FT c/9", identity=None, created=base, scan=True)
        scan_wrong = _link(
            conn, user_id=user_id, document_id=scan, number="FT C/9", key="atcud:C9",
            outcome="linked_existing", now=base,
        )
        scan_right = _link(
            conn, user_id=user_id, document_id=scan, number="FT c/9", key="atcud:c9",
            outcome="linked_existing", now=later,
        )
        # Left alone: a plain AT row, and a lowercase scan with one invoice.
        stable = _document(conn, user_id=user_id, number="FT 2026/1", identity=f"{NIF}|FT|ft 2026/1", created=base)
        _link(conn, user_id=user_id, document_id=stable, number="FT 2026/1", key="atcud:S1", outcome="created", now=base)
        lone = _document(conn, user_id=user_id, number="ft d/1", identity=None, created=base, scan=True)
        _link(conn, user_id=user_id, document_id=lone, number="FT D/1", key="atcud:D1", outcome="linked_existing", now=base)
        xmin_stable = {
            row_id: conn.execute(text("SELECT xmin::text FROM documents WHERE id = :id"), {"id": row_id}).scalar()
            for row_id in (stable, lone, scan)
        }

    command.upgrade(cfg, HEAD)
    with engine.connect() as conn:
        assert _version(conn) == HEAD
        _indexdef(conn)
        live = conn.execute(
            text(
                "SELECT id, invoice_number, at_invoice_identity, vat_amount FROM documents "
                "WHERE deleted_at IS NULL ORDER BY invoice_number"
            )
        ).mappings().all()
        numbers = sorted(row["invoice_number"] for row in live)
        assert numbers == sorted(["FT A/5", "FT a/5", "FT B/7", "FT b/7", "FT c/9", "FT C/9", "FT 2026/1", "ft d/1"]), numbers
        assert sum((row["vat_amount"] for row in live), Decimal("0")) == Decimal("18.40")
        identity = {row["invoice_number"]: row["at_invoice_identity"] for row in live}
        assert identity["FT A/5"] == f"{NIF}|FT|ft A/5"
        assert identity["FT a/5"] == f"{NIF}|FT|ft a/5"
        assert identity["FT B/7"] == f"{NIF}|FT|ft B/7"
        assert identity["FT b/7"] == f"{NIF}|FT|ft b/7"
        assert identity["FT C/9"] == f"{NIF}|FT|ft C/9"
        assert identity["FT 2026/1"] == f"{NIF}|FT|ft 2026/1"
        by_number = {row["invoice_number"]: row["id"] for row in live}
        assert by_number["FT B/7"] == keeper
        assert by_number["FT b/7"] == dropped

        def target(link_id):
            return conn.execute(
                text("SELECT document_id FROM efatura_links WHERE id = :id"), {"id": link_id}
            ).scalar()

        assert target(merged_lower) == by_number["FT a/5"] != merged
        assert target(dropped_link) == dropped
        assert target(scan_right) == scan
        assert target(scan_wrong) == by_number["FT C/9"] != scan
        for row_id, xmin in xmin_stable.items():
            assert conn.execute(
                text("SELECT xmin::text FROM documents WHERE id = :id"), {"id": row_id}
            ).scalar() == xmin
        assert conn.execute(
            text("SELECT count(*) FROM audit_logs WHERE action = 'efatura_split'")
        ).scalar() == 4
        snap = _snapshot(conn)
        index_before = _indexdef(conn)

    command.downgrade(cfg, BEFORE)
    with engine.connect() as conn:
        assert _version(conn) == BEFORE
        assert _snapshot(conn) == snap
    command.upgrade(cfg, HEAD)
    with engine.connect() as conn:
        assert _version(conn) == HEAD
        assert _snapshot(conn) == snap
        assert _indexdef(conn) == index_before
    engine.dispose()
    print("migration 014 child passed")


def _empty() -> None:
    from alembic import command

    cfg = _cfg()
    command.upgrade(cfg, HEAD)
    engine = create_engine(os.environ["DATABASE_URL"])
    with engine.connect() as conn:
        assert _version(conn) == HEAD
        _indexdef(conn)
        assert conn.execute(text("SELECT count(*) FROM documents")).scalar() == 0
        assert conn.execute(text("SELECT count(*) FROM audit_logs")).scalar() == 0
    command.downgrade(cfg, "base")
    command.upgrade(cfg, HEAD)
    with engine.connect() as conn:
        assert _version(conn) == HEAD
        _indexdef(conn)
    engine.dispose()
    print("migration 014 empty database passed")


def _run(name: str, arg: str) -> None:
    url = _recreate(name)
    env = os.environ.copy()
    env["DATABASE_URL"] = url
    completed = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), arg], cwd=BACKEND, env=env, check=False
    )
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def main() -> None:
    if "--child" in sys.argv:
        _child()
        return
    if "--empty" in sys.argv:
        _empty()
        return
    name = f"mig014_{uuid.uuid4().hex[:8]}"
    empty = f"mig014e_{uuid.uuid4().hex[:8]}"
    try:
        _run(name, "--child")
        print("migration 014 passed")
        _run(empty, "--empty")
    finally:
        for database in (name, empty):
            _drop(database)


if __name__ == "__main__":
    main()

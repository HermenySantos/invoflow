"""Migration 013 recomputes stale e-Fatura identities on Postgres.

Refuses sqlite. Alembic's env.py reads DATABASE_URL, so the check runs in a
child process pointed at the database it creates. Otherwise upgrade would
migrate the caller's database and this one would stay empty.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


BACKEND = Path(__file__).resolve().parents[1]
HEAD = "013_recompute_identity"
BEFORE = "012_at_invoice_identity"
NIF = "296123456"
AT_MIME = "application/vnd.invoflow.efatura+json"
AT_RAW = '{"source":"efatura"}'

FTA_OLD = f"{NIF}|FT|ft a 2026/5"
FTA_NEW = f"{NIF}|FT|fta 2026/5"
FT_A_NEW = f"{NIF}|FT|ft a 2026/5"
NC_DOT_OLD = f"{NIF}|NC|nc . 2026/5"
NC_NEW = f"{NIF}|NC|nc 2026/5"
ND_DOT_OLD = f"{NIF}|ND|nd . 2026/4"
ND_NEW = f"{NIF}|ND|nd 2026/4"
FS_DOT_OLD = f"{NIF}|FS|fs . 2026/2"
FS_NEW = f"{NIF}|FS|fs 2026/2"
FR_DOT_OLD = f"{NIF}|FR|fr . 2026/3"
FT_STABLE = f"{NIF}|FT|ft 2026/1"


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


def _cfg():
    from alembic.config import Config

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])
    return cfg


def _indexdef(conn) -> str:
    indexdef = conn.execute(
        text(
            "SELECT indexdef FROM pg_indexes WHERE indexname = 'uq_documents_at_invoice_identity'"
        )
    ).scalar()
    assert indexdef and "UNIQUE" in indexdef.upper()
    assert "deleted_at IS NULL" in indexdef
    return indexdef


def _insert_user(conn, now) -> str:
    user_id = str(uuid.uuid4())
    conn.execute(
        text(
            "INSERT INTO users (id, clerk_id, email, created_at, updated_at) "
            "VALUES (:id, :clerk_id, :email, :now, :now)"
        ),
        {
            "id": user_id,
            "clerk_id": f"mig013-{user_id[:8]}",
            "email": "mig013@example.com",
            "now": now,
        },
    )
    return user_id


def _insert_document(
    conn,
    *,
    user_id: str,
    number: str,
    document_type: str,
    status: str,
    created,
    updated,
    deleted,
    identity,
    mime: str = AT_MIME,
    raw: str = AT_RAW,
    filename: str = "at.efatura",
) -> str:
    document_id = str(uuid.uuid4())
    conn.execute(
        text(
            "INSERT INTO documents ("
            "id, user_id, status, storage_key, original_filename, mime_type, "
            "invoice_number, document_type, vendor_nif, net_amount, vat_amount, "
            "gross_amount, document_date, ocr_raw_response, at_invoice_identity, "
            "deleted_at, created_at, updated_at"
            ") VALUES ("
            ":id, :user_id, :status, :storage_key, :filename, :mime, "
            ":number, :document_type, :nif, 10.00, 2.30, 12.30, '2026-04-01', :raw, "
            ":identity, :deleted_at, :created, :updated)"
        ),
        {
            "id": document_id,
            "user_id": user_id,
            "status": status,
            "storage_key": f"efatura/{document_id}.efatura",
            "filename": filename,
            "mime": mime,
            "number": number,
            "document_type": document_type,
            "nif": NIF,
            "raw": raw,
            "identity": identity,
            "deleted_at": deleted,
            "created": created,
            "updated": updated,
        },
    )
    return document_id


def _insert_link(conn, *, user_id: str, document_id: str, now, source_key: str) -> str:
    link_id = str(uuid.uuid4())
    conn.execute(
        text(
            "INSERT INTO efatura_links ("
            "id, user_id, source_key, role, outcome, document_id, fiscal_status, "
            "payload_json, created_at, updated_at"
            ") VALUES ("
            ":id, :user_id, :source_key, 'acquirer', 'created', :document_id, 'normal', "
            "'{}', :now, :now)"
        ),
        {
            "id": link_id,
            "user_id": user_id,
            "source_key": source_key,
            "document_id": document_id,
            "now": now,
        },
    )
    return link_id


def _insert_user_audit(conn, *, user_id: str, document_id: str, now) -> None:
    conn.execute(
        text(
            "INSERT INTO audit_logs ("
            "id, entity_type, entity_id, user_id, action, source, changes_json, created_at"
            ") VALUES ("
            ":id, 'document', :entity_id, :user_id, 'update', 'user', '{}', :now)"
        ),
        {
            "id": str(uuid.uuid4()),
            "entity_id": document_id,
            "user_id": user_id,
            "now": now,
        },
    )


def _xmin(conn, table: str, row_id: str):
    return conn.execute(
        text(f"SELECT xmin::text FROM {table} WHERE id = :id"),
        {"id": row_id},
    ).scalar()


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
        rows(
            "SELECT id, entity_type, entity_id, user_id, action, source, changes_json, "
            "xmin::text FROM audit_logs ORDER BY id"
        ),
    )


def _child() -> None:
    from alembic import command

    source = (BACKEND / "alembic/versions/013_recompute_identity.py").read_text()
    assert "import app" not in source
    assert "from app." not in source
    cfg = _cfg()
    command.upgrade(cfg, BEFORE)
    engine = create_engine(os.environ["DATABASE_URL"])
    base = datetime(2026, 4, 1, 8, 0, 0)
    older = base
    newer = base + timedelta(hours=5)
    deleted_stamp = datetime(2026, 3, 1, 9, 0, 0)
    with engine.begin() as conn:
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == BEFORE
        user_id = _insert_user(conn, base)
        # The old FTA key is the same string as a real "FT A" series. Both cannot
        # be live under 012's partial unique index, so the spaced row starts unset.
        fta = _insert_document(
            conn,
            user_id=user_id,
            number="FTA 2026/5",
            document_type="FT",
            status="needs_review",
            created=older,
            updated=older,
            deleted=None,
            identity=FTA_OLD,
        )
        ft_a = _insert_document(
            conn,
            user_id=user_id,
            number="FT A 2026/5",
            document_type="FT",
            status="needs_review",
            created=older,
            updated=older,
            deleted=None,
            identity=None,
        )
        nc_keeper = _insert_document(
            conn,
            user_id=user_id,
            number="NC 2026/5",
            document_type="NC",
            status="accountant_review",
            created=older,
            updated=older,
            deleted=None,
            identity=NC_NEW,
        )
        nc_loser = _insert_document(
            conn,
            user_id=user_id,
            number="NC. 2026/5",
            document_type="NC",
            status="needs_review",
            created=newer,
            updated=newer,
            deleted=None,
            identity=NC_DOT_OLD,
        )
        nd_keeper = _insert_document(
            conn,
            user_id=user_id,
            number="ND 2026/4",
            document_type="ND",
            status="needs_review",
            created=older,
            updated=older,
            deleted=None,
            identity=ND_NEW,
        )
        nd_loser = _insert_document(
            conn,
            user_id=user_id,
            number="ND. 2026/4",
            document_type="ND",
            status="needs_review",
            created=newer,
            updated=newer,
            deleted=None,
            identity=ND_DOT_OLD,
        )
        stable = _insert_document(
            conn,
            user_id=user_id,
            number="FT 2026/1",
            document_type="FT",
            status="needs_review",
            created=older,
            updated=older,
            deleted=None,
            identity=FT_STABLE,
        )
        # Old split on a photo. Treating it as an AT row would rewrite the key.
        scan = _insert_document(
            conn,
            user_id=user_id,
            number="FR. 2026/3",
            document_type="FR",
            status="needs_review",
            created=older,
            updated=older,
            deleted=None,
            identity=FR_DOT_OLD,
            mime="image/jpeg",
            raw='{"text": "scan"}',
            filename="scan.jpg",
        )
        fs_deleted = _insert_document(
            conn,
            user_id=user_id,
            number="FS. 2026/2",
            document_type="FS",
            status="needs_review",
            created=older,
            updated=older,
            deleted=deleted_stamp,
            identity=FS_DOT_OLD,
        )
        _insert_link(
            conn,
            user_id=user_id,
            document_id=nc_loser,
            now=base,
            source_key="doc:296123456:NC:nc. 2026/5",
        )
        _insert_link(
            conn,
            user_id=user_id,
            document_id=nc_loser,
            now=base,
            source_key="atcud:NC-DOT",
        )
        _insert_link(
            conn,
            user_id=user_id,
            document_id=nd_loser,
            now=base,
            source_key="doc:296123456:ND:nd. 2026/4",
        )
        _insert_user_audit(conn, user_id=user_id, document_id=nd_keeper, now=base)
        stable_ids = (nc_keeper, nd_keeper, stable, scan)
        changed_ids = (fta, ft_a, nc_loser, nd_loser, fs_deleted)
        xmin_before = {row_id: _xmin(conn, "documents", row_id) for row_id in stable_ids + changed_ids}

    command.upgrade(cfg, HEAD)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == HEAD
        _indexdef(conn)
        rows = {
            row.id: row
            for row in conn.execute(
                text(
                    "SELECT id, invoice_number, at_invoice_identity, deleted_at, updated_at "
                    "FROM documents"
                )
            )
        }
        assert len(rows) == 9
        assert rows[fta].at_invoice_identity == FTA_NEW
        assert rows[fta].deleted_at is None
        assert rows[fta].updated_at == older
        assert rows[ft_a].at_invoice_identity == FT_A_NEW
        assert rows[ft_a].deleted_at is None
        assert rows[fta].at_invoice_identity != rows[ft_a].at_invoice_identity
        assert rows[nc_keeper].at_invoice_identity == NC_NEW
        assert rows[nc_keeper].deleted_at is None
        assert rows[nc_keeper].updated_at == older
        assert rows[nc_loser].at_invoice_identity == NC_NEW
        assert rows[nc_loser].deleted_at is not None
        assert rows[nc_loser].updated_at != newer
        assert rows[nd_keeper].at_invoice_identity == ND_NEW
        assert rows[nd_keeper].deleted_at is None
        assert rows[nd_keeper].updated_at == older
        assert rows[nd_loser].at_invoice_identity == ND_NEW
        assert rows[nd_loser].deleted_at is not None
        assert rows[stable].at_invoice_identity == FT_STABLE
        assert rows[stable].deleted_at is None
        assert rows[stable].updated_at == older
        assert rows[scan].at_invoice_identity == FR_DOT_OLD
        assert rows[scan].deleted_at is None
        assert rows[scan].updated_at == older
        assert rows[fs_deleted].at_invoice_identity == FS_NEW
        assert rows[fs_deleted].deleted_at == deleted_stamp
        live = {
            row.invoice_number
            for row in rows.values()
            if row.deleted_at is None
        }
        assert live == {
            "FTA 2026/5",
            "FT A 2026/5",
            "NC 2026/5",
            "ND 2026/4",
            "FT 2026/1",
            "FR. 2026/3",
        }
        for row_id in stable_ids:
            assert _xmin(conn, "documents", row_id) == xmin_before[row_id]
        for row_id in changed_ids:
            assert _xmin(conn, "documents", row_id) != xmin_before[row_id]
        links = conn.execute(
            text("SELECT source_key, document_id, outcome, updated_at FROM efatura_links")
        ).mappings().all()
        assert len(links) == 3
        by_key = {row["source_key"]: row for row in links}
        assert by_key["doc:296123456:NC:nc. 2026/5"]["document_id"] == nc_keeper
        assert by_key["atcud:NC-DOT"]["document_id"] == nc_keeper
        assert by_key["doc:296123456:ND:nd. 2026/4"]["document_id"] == nd_keeper
        assert {row["outcome"] for row in links} == {"created"}
        assert {row["updated_at"] for row in links} != {base}
        assert len({row["updated_at"] for row in links}) == 1
        assert conn.execute(
            text("SELECT count(*) FROM efatura_links WHERE document_id = :id"),
            {"id": nc_loser},
        ).scalar() == 0
        assert conn.execute(
            text("SELECT count(*) FROM efatura_links WHERE document_id = :id"),
            {"id": nd_loser},
        ).scalar() == 0
        audits = conn.execute(
            text(
                "SELECT entity_id, entity_type, user_id, action, source, changes_json "
                "FROM audit_logs WHERE action = 'efatura_dedupe'"
            )
        ).mappings().all()
        assert len(audits) == 2
        by_entity = {row["entity_id"]: row for row in audits}
        assert set(by_entity) == {nc_loser, nd_loser}
        expected = {
            nc_loser: (nc_keeper, NC_NEW),
            nd_loser: (nd_keeper, ND_NEW),
        }
        for entity_id, (keeper, identity) in expected.items():
            row = by_entity[entity_id]
            assert row["entity_type"] == "document"
            assert row["user_id"] == user_id
            assert row["source"] == "efatura"
            body = json.loads(row["changes_json"])
            assert set(body) == {"deleted_at", "kept_document_id", "at_invoice_identity"}
            assert body["deleted_at"]["old"] is None
            assert body["deleted_at"]["new"].endswith("Z")
            assert body["kept_document_id"] == {"old": None, "new": keeper}
            assert body["at_invoice_identity"] == {"old": None, "new": identity}
        assert conn.execute(
            text(
                "SELECT count(*) FROM audit_logs WHERE source = 'user' AND entity_id = :id"
            ),
            {"id": nd_keeper},
        ).scalar() == 1
        snap = _snapshot(conn)
        index_before = _indexdef(conn)

    command.downgrade(cfg, BEFORE)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == BEFORE
        assert _snapshot(conn) == snap
        assert _indexdef(conn) == index_before
    command.upgrade(cfg, "head")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == HEAD
        assert _snapshot(conn) == snap
        assert _indexdef(conn) == index_before
        assert conn.execute(
            text("SELECT count(*) FROM audit_logs WHERE action = 'efatura_dedupe'")
        ).scalar() == 2
    engine.dispose()
    print("migration 013 child passed")


def _empty() -> None:
    from alembic import command

    cfg = _cfg()
    command.upgrade(cfg, "head")
    engine = create_engine(os.environ["DATABASE_URL"])
    with engine.connect() as conn:
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == HEAD
        column = conn.execute(
            text(
                "SELECT count(*) FROM information_schema.columns "
                "WHERE table_name = 'documents' AND column_name = 'at_invoice_identity'"
            )
        ).scalar()
        assert column == 1
        _indexdef(conn)
        assert conn.execute(text("SELECT count(*) FROM documents")).scalar() == 0
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == HEAD
        _indexdef(conn)
        assert conn.execute(text("SELECT count(*) FROM documents")).scalar() == 0
    engine.dispose()
    print("migration 013 empty database passed")


def _run(name: str, arg: str) -> None:
    url = _recreate(name)
    env = os.environ.copy()
    env["DATABASE_URL"] = url
    completed = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), arg],
        cwd=BACKEND,
        env=env,
        check=False,
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
    name = f"mig013_{uuid.uuid4().hex[:8]}"
    empty = f"mig013e_{uuid.uuid4().hex[:8]}"
    try:
        _run(name, "--child")
        print("migration 013 passed")
        _run(empty, "--empty")
    finally:
        for database in (name, empty):
            _drop(database)


if __name__ == "__main__":
    main()

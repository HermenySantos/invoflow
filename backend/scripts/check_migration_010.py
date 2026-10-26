"""Migration 010 adds series_mismatch_accepted on Postgres. Refuses sqlite.

Alembic's env.py uses DATABASE_URL, not the URL set on the Config object.
The check therefore runs in a child process whose DATABASE_URL is the
database it inspects. Otherwise upgrade head migrates the caller's database
and the new database stays empty.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


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


def _column(conn):
    return conn.execute(
        text(
            """
            SELECT is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'documents'
              AND column_name = 'series_mismatch_accepted'
            """
        )
    ).one_or_none()


def _child() -> None:
    from alembic import command
    from alembic.config import Config

    url = os.environ["DATABASE_URL"]
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    engine = create_engine(url)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    user_id = str(uuid.uuid4())
    document_id = str(uuid.uuid4())
    with engine.begin() as conn:
        found = _column(conn)
        assert found is not None, "series_mismatch_accepted missing at head"
        assert found.is_nullable == "NO"
        assert found.column_default is not None and "false" in str(found.column_default).lower()
        conn.execute(
            text(
                "INSERT INTO users (id, clerk_id, email, created_at, updated_at) "
                "VALUES (:id, :clerk_id, :email, :created_at, :updated_at)"
            ),
            {
                "id": user_id,
                "clerk_id": f"mig010-{user_id[:8]}",
                "email": "mig010@example.com",
                "created_at": now,
                "updated_at": now,
            },
        )
        conn.execute(
            text(
                "INSERT INTO documents ("
                "id, user_id, status, storage_key, original_filename, mime_type, "
                "document_type, created_at, updated_at"
                ") VALUES ("
                ":id, :user_id, 'needs_review', 'mig/a.jpg', 'a.jpg', 'image/jpeg', "
                "'unclassified', :created_at, :updated_at)"
            ),
            {"id": document_id, "user_id": user_id, "created_at": now, "updated_at": now},
        )
        stored = conn.execute(
            text("SELECT series_mismatch_accepted FROM documents WHERE id = :id"),
            {"id": document_id},
        ).scalar()
        assert stored is False
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert version == "010_series_mismatch_accepted"
    command.downgrade(cfg, "009_unclassified_backfill")
    with engine.connect() as conn:
        assert _column(conn) is None
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == "009_unclassified_backfill"
    command.upgrade(cfg, "head")
    with engine.connect() as conn:
        assert _column(conn) is not None
        stored = conn.execute(
            text("SELECT series_mismatch_accepted FROM documents WHERE id = :id"),
            {"id": document_id},
        ).scalar()
        assert stored is False
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == "010_series_mismatch_accepted"
    engine.dispose()
    print("migration 010 child passed")


def main() -> None:
    if "--child" in sys.argv:
        _child()
        return
    name = f"mig010_{uuid.uuid4().hex[:8]}"
    try:
        url = _recreate(name)
        env = os.environ.copy()
        env["DATABASE_URL"] = url
        completed = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--child"],
            cwd=BACKEND,
            env=env,
            check=False,
        )
        if completed.returncode != 0:
            raise SystemExit(completed.returncode)
        print("migration 010 passed")
    finally:
        _drop(name)


if __name__ == "__main__":
    main()

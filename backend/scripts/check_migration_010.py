"""Migration 010 adds series_mismatch_accepted on Postgres. Refuses sqlite."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from alembic import command
from alembic.config import Config
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
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    engine.dispose()
    return _admin_url().set(database=name).render_as_string(hide_password=False)


def _column(conn):
    return conn.execute(
        text(
            """
            SELECT is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = 'documents'
              AND column_name = 'series_mismatch_accepted'
            """
        )
    ).one_or_none()


def main() -> None:
    os.chdir(BACKEND)
    name = f"mig010_{uuid.uuid4().hex[:8]}"
    url = _recreate(name)
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
    command.downgrade(cfg, "009_unclassified_backfill")
    with engine.connect() as conn:
        assert _column(conn) is None
    command.upgrade(cfg, "head")
    with engine.connect() as conn:
        assert _column(conn) is not None
        stored = conn.execute(
            text("SELECT series_mismatch_accepted FROM documents WHERE id = :id"),
            {"id": document_id},
        ).scalar()
        assert stored is False
    engine.dispose()
    print("migration 010 passed")


if __name__ == "__main__":
    main()

"""Migration 009 on Postgres 16.

Three checks, each in its own database:

- a database created at head
- a database that ran the current 008 (varchar(20)), then 009, down, and up
- a database stamped at 008 with an 8-character document_type, as 2f8c720 shipped it

Refuses sqlite.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


BACKEND = Path(__file__).resolve().parents[1]
HEADING_OK = "migration 009 passed"


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


def _run(database_url: str, mode: str) -> None:
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url
    env["MIG009_MODE"] = mode
    completed = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--child"],
        cwd=BACKEND,
        env=env,
        check=False,
    )
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def _insert_user(conn, user_id: str, now) -> None:
    conn.execute(
        text(
            "INSERT INTO users (id, clerk_id, email, created_at, updated_at) "
            "VALUES (:id, :clerk_id, :email, :created_at, :updated_at)"
        ),
        {
            "id": user_id,
            "clerk_id": f"mig009-{user_id[:8]}",
            "email": "mig009@example.com",
            "created_at": now,
            "updated_at": now,
        },
    )


def _insert_document(conn, **fields) -> None:
    conn.execute(
        text(
            "INSERT INTO documents ("
            "id, user_id, status, storage_key, original_filename, mime_type, "
            "document_type, net_amount, vat_amount, gross_amount, ocr_raw_response, "
            "created_at, updated_at"
            ") VALUES ("
            ":id, :user_id, :status, :storage_key, :original_filename, :mime_type, "
            ":document_type, :net_amount, :vat_amount, :gross_amount, :ocr_raw_response, "
            ":created_at, :updated_at)"
        ),
        fields,
    )


def _width(conn) -> int:
    return int(
        conn.execute(
            text(
                """
                SELECT character_maximum_length
                FROM information_schema.columns
                WHERE table_name = 'documents' AND column_name = 'document_type'
                """
            )
        ).scalar()
    )


def _rows(conn, user_id: str, *, with_at: bool) -> dict:
    at_column = ", at_document_type" if with_at else ""
    found = conn.execute(
        text(
            "SELECT id, status, document_type"
            f"{at_column}, ocr_raw_response "
            "FROM documents WHERE user_id = :user_id"
        ),
        {"user_id": user_id},
    ).mappings()
    return {row["id"]: dict(row) for row in found}


def _child() -> None:
    from alembic import command
    from alembic.config import Config

    mode = os.environ["MIG009_MODE"]
    url = os.environ["DATABASE_URL"]
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    engine = create_engine(url)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    user_id = str(uuid.uuid4())

    if mode == "fresh":
        command.upgrade(cfg, "head")
        with engine.connect() as conn:
            assert _width(conn) >= 20
            nullable = conn.execute(
                text(
                    """
                    SELECT is_nullable FROM information_schema.columns
                    WHERE table_name = 'documents' AND column_name = 'document_type'
                    """
                )
            ).scalar()
            assert nullable == "NO"
        print("fresh head accepts unclassified")
        return

    if mode == "from008":
        command.upgrade(cfg, "008_document_type")
        ids = {
            name: str(uuid.uuid4())
            for name in ("ft_ready", "qr_nc", "qr_pf", "already", "raw_text", "raw_list")
        }
        with engine.begin() as conn:
            _insert_user(conn, user_id, now)
            common = dict(
                user_id=user_id,
                storage_key="mig/a.jpg",
                original_filename="a.jpg",
                mime_type="image/jpeg",
                net_amount="10.00",
                vat_amount="2.30",
                gross_amount="12.30",
                created_at=now,
                updated_at=now,
            )
            _insert_document(
                conn,
                id=ids["ft_ready"],
                status="ready",
                document_type="FT",
                ocr_raw_response=None,
                **common,
            )
            _insert_document(
                conn,
                id=ids["qr_nc"],
                status="ready",
                document_type="NC",
                ocr_raw_response=json.dumps({"qr": {"document_type": "NC"}}),
                **common,
            )
            _insert_document(
                conn,
                id=ids["qr_pf"],
                status="ready",
                document_type="PF",
                ocr_raw_response=json.dumps({"qr": {"document_type": "PF"}}),
                **common,
            )
            _insert_document(
                conn,
                id=ids["already"],
                status="needs_review",
                document_type="unclassified",
                ocr_raw_response=None,
                **common,
            )
            _insert_document(
                conn,
                id=ids["raw_text"],
                status="ready",
                document_type="FT",
                ocr_raw_response="Processing error",
                **common,
            )
            _insert_document(
                conn,
                id=ids["raw_list"],
                status="needs_review",
                document_type="FT",
                ocr_raw_response="[1, 2]",
                **common,
            )
        command.upgrade(cfg, "009_unclassified_backfill")
        with engine.connect() as conn:
            assert _width(conn) >= 20
            got = _rows(conn, user_id, with_at=True)
        assert got[ids["ft_ready"]]["document_type"] == "unclassified"
        assert got[ids["ft_ready"]]["status"] == "needs_review"
        assert got[ids["qr_nc"]]["document_type"] == "NC"
        assert got[ids["qr_nc"]]["status"] == "ready"
        assert got[ids["qr_pf"]]["document_type"] == "unclassified"
        assert got[ids["qr_pf"]]["status"] == "needs_review"
        assert got[ids["qr_pf"]]["at_document_type"] == "PF"
        assert got[ids["already"]]["document_type"] == "unclassified"
        assert got[ids["already"]]["status"] == "needs_review"
        assert got[ids["raw_text"]]["ocr_raw_response"] == "Processing error"
        assert got[ids["raw_text"]]["document_type"] == "unclassified"
        assert got[ids["raw_text"]]["status"] == "needs_review"
        assert got[ids["raw_list"]]["ocr_raw_response"] == "[1, 2]"
        assert got[ids["raw_list"]]["document_type"] == "unclassified"
        command.downgrade(cfg, "008_document_type")
        with engine.connect() as conn:
            restored = _rows(conn, user_id, with_at=False)
            assert _width(conn) >= 20
        assert restored[ids["ft_ready"]]["document_type"] == "FT"
        assert restored[ids["ft_ready"]]["status"] == "ready"
        assert json.loads(restored[ids["qr_nc"]]["ocr_raw_response"]) == {"qr": {"document_type": "NC"}}
        assert restored[ids["qr_pf"]]["document_type"] == "PF"
        assert restored[ids["already"]]["document_type"] == "unclassified"
        assert restored[ids["raw_text"]]["ocr_raw_response"] == "Processing error"
        assert restored[ids["raw_list"]]["ocr_raw_response"] == "[1, 2]"
        # Non-object raw text has nowhere to store _type_backup without rewriting it.
        assert restored[ids["raw_text"]]["document_type"] == "unclassified"
        command.upgrade(cfg, "009_unclassified_backfill")
        with engine.connect() as conn:
            again = _rows(conn, user_id, with_at=True)
        for key, row_id in ids.items():
            assert again[row_id]["document_type"] == got[row_id]["document_type"]
            assert again[row_id]["status"] == got[row_id]["status"]
            assert again[row_id]["at_document_type"] == got[row_id]["at_document_type"]
            assert again[row_id]["ocr_raw_response"] == got[row_id]["ocr_raw_response"]
        assert again[ids["raw_text"]]["ocr_raw_response"] == "Processing error"
        assert again[ids["raw_list"]]["ocr_raw_response"] == "[1, 2]"
        print("008 varchar(20) up/down/up keeps json rows; non-json text is unchanged")
        return

    if mode == "varchar8":
        # 2f8c720's 008 (never merged) stored no _amount_sign_backup. Downgrading
        # that lineage through 008 to 007 cannot restore original minuses. Dev
        # databases only. This check does not edit 008; it only widens varchar(8).
        command.upgrade(cfg, "007_efatura_links")
        ids = {name: str(uuid.uuid4()) for name in ("nc_ready", "ft_ready", "qr_nc", "qr_ft", "qr_gt")}
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE documents ADD COLUMN document_type VARCHAR(8)"))
            _insert_user(conn, user_id, now)
            common = dict(
                user_id=user_id,
                storage_key="mig/a.jpg",
                original_filename="a.jpg",
                mime_type="image/jpeg",
                net_amount="8.13",
                vat_amount="1.87",
                gross_amount="10.00",
                created_at=now,
                updated_at=now,
            )
            _insert_document(conn, id=ids["nc_ready"], status="ready", document_type="NC", ocr_raw_response=None, **common)
            _insert_document(conn, id=ids["ft_ready"], status="ready", document_type="FT", ocr_raw_response=None, **common)
            _insert_document(
                conn,
                id=ids["qr_nc"],
                status="ready",
                document_type="NC",
                ocr_raw_response=json.dumps({"qr": {"document_type": "NC"}}),
                **common,
            )
            _insert_document(
                conn,
                id=ids["qr_ft"],
                status="accountant_review",
                document_type="FT",
                ocr_raw_response=json.dumps({"qr": {"document_type": "FT"}}),
                **common,
            )
            _insert_document(
                conn,
                id=ids["qr_gt"],
                status="ready",
                document_type="GT",
                ocr_raw_response=json.dumps({"qr": {"document_type": "GT"}}),
                **common,
            )
        command.stamp(cfg, "008_document_type")
        command.upgrade(cfg, "head")
        with engine.connect() as conn:
            assert _width(conn) >= 20
            got = _rows(conn, user_id, with_at=True)
        assert got[ids["nc_ready"]]["document_type"] == "unclassified"
        assert got[ids["nc_ready"]]["status"] == "needs_review"
        assert got[ids["ft_ready"]]["document_type"] == "unclassified"
        assert got[ids["ft_ready"]]["status"] == "needs_review"
        assert got[ids["qr_nc"]]["document_type"] == "NC"
        assert got[ids["qr_nc"]]["status"] == "ready"
        assert got[ids["qr_ft"]]["document_type"] == "FT"
        assert got[ids["qr_ft"]]["status"] == "accountant_review"
        assert got[ids["qr_gt"]]["document_type"] == "unclassified"
        assert got[ids["qr_gt"]]["at_document_type"] == "GT"
        assert got[ids["qr_gt"]]["status"] == "needs_review"
        command.downgrade(cfg, "008_document_type")
        with engine.connect() as conn:
            restored = _rows(conn, user_id, with_at=False)
            assert _width(conn) >= 13
        assert restored[ids["nc_ready"]]["document_type"] == "NC"
        assert restored[ids["nc_ready"]]["status"] == "ready"
        assert restored[ids["ft_ready"]]["status"] == "ready"
        assert restored[ids["qr_gt"]]["document_type"] == "GT"
        command.upgrade(cfg, "head")
        with engine.connect() as conn:
            again = _rows(conn, user_id, with_at=True)
        for key, row_id in ids.items():
            assert again[row_id]["document_type"] == got[row_id]["document_type"]
            assert again[row_id]["status"] == got[row_id]["status"]
            assert again[row_id]["at_document_type"] == got[row_id]["at_document_type"]
        print("varchar(8) 008 up/down/up is lossless")
        return

    raise SystemExit(f"unknown mode {mode}")


def main() -> None:
    if "--child" in sys.argv:
        _child()
        return
    names = {
        "fresh": "invoflow_mig009_fresh",
        "from008": "invoflow_mig009_from008",
        "varchar8": "invoflow_mig009_varchar8",
    }
    try:
        for mode, name in names.items():
            _run(_recreate(name), mode)
        print(HEADING_OK)
    finally:
        for name in names.values():
            _drop(name)


if __name__ == "__main__":
    main()

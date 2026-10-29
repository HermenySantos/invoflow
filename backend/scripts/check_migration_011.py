"""Migration 011 restores an e-Fatura invoice whose scan was deleted.

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
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


BACKEND = Path(__file__).resolve().parents[1]
HEAD = "012_at_invoice_identity"
STAMP = "011_restore_orphaned_efatura"
BEFORE = "010_series_mismatch_accepted"


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


def _payload() -> str:
    return json.dumps(
        {
            "document_type": "FT",
            "invoice_number": "FT A/123",
            "issue_date": "2026-01-20",
            "issuer_nif": "500100144",
            "issuer_name": "Continente",
            "acquirer_nif": "555555555",
            "acquirer_country": "PT",
            "fiscal_status": "normal",
            "atcud": "GIL160",
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


def _insert_user(conn, now) -> str:
    user_id = str(uuid.uuid4())
    conn.execute(
        text(
            "INSERT INTO users (id, clerk_id, email, created_at, updated_at) "
            "VALUES (:id, :clerk_id, :email, :now, :now)"
        ),
        {
            "id": user_id,
            "clerk_id": f"mig011-{user_id[:8]}",
            "email": "mig011@example.com",
            "now": now,
        },
    )
    return user_id


def _insert_document(conn, *, user_id: str, now, mime: str, number: str, deleted: bool) -> str:
    document_id = str(uuid.uuid4())
    conn.execute(
        text(
            "INSERT INTO documents ("
            "id, user_id, status, storage_key, original_filename, mime_type, "
            "invoice_number, document_type, vendor_nif, net_amount, vat_amount, "
            "gross_amount, document_date, ocr_raw_response, deleted_at, "
            "created_at, updated_at"
            ") VALUES ("
            ":id, :user_id, 'ready', :storage_key, 'scan.jpg', :mime, "
            ":number, 'FT', '500100144', 8.00, 1.84, 9.84, '2026-01-20', "
            ":raw, :deleted_at, :now, :now)"
        ),
        {
            "id": document_id,
            "user_id": user_id,
            "storage_key": f"mig/{document_id}.jpg",
            "mime": mime,
            "number": number,
            "raw": json.dumps({"text": "scan"}),
            "deleted_at": now if deleted else None,
            "now": now,
        },
    )
    return document_id


def _insert_link(conn, *, user_id: str, document_id: str | None, now, source_key: str, outcome: str, payload: str):
    link_id = str(uuid.uuid4())
    conn.execute(
        text(
            "INSERT INTO efatura_links ("
            "id, user_id, source_key, role, outcome, document_id, fiscal_status, "
            "warning, payload_json, created_at, updated_at"
            ") VALUES ("
            ":id, :user_id, :source_key, 'acquirer', :outcome, :document_id, 'normal', "
            ":warning, :payload, :now, :now)"
        ),
        {
            "id": link_id,
            "user_id": user_id,
            "source_key": source_key,
            "outcome": outcome,
            "document_id": document_id,
            "warning": "linked" if document_id else None,
            "payload": payload,
            "now": now,
        },
    )
    return link_id


def _child() -> None:
    import logging
    from alembic import command
    from alembic.config import Config

    source = (BACKEND / "alembic/versions/011_restore_orphaned_efatura.py").read_text()
    assert "import app" not in source
    assert "from app." not in source
    warnings: list[str] = []

    class _Capture(logging.Handler):
        def emit(self, record):
            if record.levelno >= logging.WARNING:
                warnings.append(record.getMessage())

    import logging.config

    original_file_config = logging.config.fileConfig

    def _file_config(*args, **kwargs):
        original_file_config(*args, **kwargs)
        logger = logging.getLogger("alembic.runtime.migration")
        logger.setLevel(logging.INFO)
        logger.addHandler(_Capture())

    logging.config.fileConfig = _file_config
    url = os.environ["DATABASE_URL"]
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, BEFORE)
    engine = create_engine(url)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    payload = _payload()
    with engine.begin() as conn:
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == BEFORE
        user_id = _insert_user(conn, now)
        orphan_id = _insert_document(
            conn, user_id=user_id, now=now, mime="image/jpeg", number="FT A/123", deleted=True
        )
        live_id = _insert_document(
            conn, user_id=user_id, now=now, mime="image/jpeg", number="FT B/9", deleted=False
        )
        _insert_link(
            conn,
            user_id=user_id,
            document_id=orphan_id,
            now=now,
            source_key="atcud:GIL160",
            outcome="linked_existing",
            payload=payload,
        )
        _insert_link(
            conn,
            user_id=user_id,
            document_id=orphan_id,
            now=now,
            source_key="doc:500100144:FT:ft a/123",
            outcome="linked_existing",
            payload=payload,
        )
        deleted_at_id = _insert_document(
            conn,
            user_id=user_id,
            now=now,
            mime="application/vnd.invoflow.efatura+json",
            number="FT Z/1",
            deleted=True,
        )
        _insert_link(
            conn,
            user_id=user_id,
            document_id=deleted_at_id,
            now=now,
            source_key="atcud:GIL160-AT",
            outcome="created",
            payload=payload.replace("FT A/123", "FT Z/1").replace("GIL160", "GIL160-AT"),
        )
        bad_id = _insert_document(
            conn, user_id=user_id, now=now, mime="image/jpeg", number="FT BAD/1", deleted=True
        )
        _insert_link(
            conn,
            user_id=user_id,
            document_id=bad_id,
            now=now,
            source_key="atcud:GIL160-BAD",
            outcome="linked_existing",
            payload="{",
        )
        _insert_link(
            conn,
            user_id=user_id,
            document_id=live_id,
            now=now,
            source_key="atcud:GIL160-LIVE",
            outcome="linked_existing",
            payload=payload.replace("FT A/123", "FT B/9").replace("GIL160", "GIL160-LIVE"),
        )
        _insert_link(
            conn,
            user_id=user_id,
            document_id=None,
            now=now,
            source_key="atcud:GIL160-NC",
            outcome="credit_note",
            payload=payload.replace('"document_type": "FT"', '"document_type": "NC"'),
        )

    command.upgrade(cfg, "head")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == HEAD
        orphan_deleted = conn.execute(
            text("SELECT deleted_at IS NOT NULL FROM documents WHERE id = :id"),
            {"id": orphan_id},
        ).scalar()
        assert orphan_deleted is True
        live_targets = conn.execute(
            text(
                "SELECT id FROM documents WHERE user_id = :user_id AND deleted_at IS NULL "
                "AND invoice_number = 'FT A/123'"
            ),
            {"user_id": user_id},
        ).scalars().all()
        assert len(live_targets) == 1
        at_id = live_targets[0]
        assert at_id != orphan_id
        mime, vat = conn.execute(
            text("SELECT mime_type, vat_amount FROM documents WHERE id = :id"),
            {"id": at_id},
        ).one()
        assert mime == "application/vnd.invoflow.efatura+json"
        assert str(vat) in ("2.30", "2.300") or float(vat) == 2.30
        pointed = conn.execute(
            text(
                "SELECT document_id, outcome FROM efatura_links WHERE source_key = 'atcud:GIL160'"
            )
        ).one()
        assert pointed.document_id == at_id
        assert pointed.outcome == "created"
        doc_key = conn.execute(
            text(
                "SELECT document_id FROM efatura_links WHERE source_key = 'doc:500100144:FT:ft a/123'"
            )
        ).scalar()
        assert doc_key == at_id
        assert conn.execute(
            text(
                "SELECT deleted_at IS NOT NULL FROM documents WHERE id = :id"
            ),
            {"id": deleted_at_id},
        ).scalar() is True
        assert conn.execute(
            text(
                "SELECT count(*) FROM documents WHERE deleted_at IS NULL AND invoice_number = 'FT Z/1'"
            )
        ).scalar() == 0
        assert conn.execute(
            text(
                "SELECT count(*) FROM documents WHERE deleted_at IS NULL AND invoice_number = 'FT BAD/1'"
            )
        ).scalar() == 0
        assert "not readable" in " ".join(warnings)
        still_live = conn.execute(
            text("SELECT document_id FROM efatura_links WHERE source_key = 'atcud:GIL160-LIVE'")
        ).scalar()
        assert still_live == live_id
        credit = conn.execute(
            text("SELECT document_id FROM efatura_links WHERE source_key = 'atcud:GIL160-NC'")
        ).scalar()
        assert credit is None
        visible = conn.execute(
            text(
                "SELECT count(*) FROM documents WHERE user_id = :user_id AND deleted_at IS NULL"
            ),
            {"user_id": user_id},
        ).scalar()
        assert visible == 2

    command.upgrade(cfg, "head")
    with engine.connect() as conn:
        visible = conn.execute(
            text(
                "SELECT count(*) FROM documents WHERE deleted_at IS NULL AND invoice_number = 'FT A/123'"
            )
        ).scalar()
        assert visible == 1

    command.downgrade(cfg, BEFORE)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == BEFORE
        assert conn.execute(
            text("SELECT count(*) FROM documents WHERE id = :id AND deleted_at IS NULL"),
            {"id": at_id},
        ).scalar() == 1
    command.upgrade(cfg, "head")
    with engine.connect() as conn:
        assert conn.execute(
            text(
                "SELECT count(*) FROM documents WHERE deleted_at IS NULL AND invoice_number = 'FT A/123'"
            )
        ).scalar() == 1
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == HEAD
    engine.dispose()
    print("migration 011 child passed")


def _drift() -> None:
    """010 -> 011 still repairs when the live Document model has a new column."""
    sys.path.insert(0, str(BACKEND))
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import Column, String

    from app.models.document import Document

    if "future_col_012" not in Document.__table__.c:
        Document.__table__.append_column(Column("future_col_012", String(20), nullable=True))
    url = os.environ["DATABASE_URL"]
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, BEFORE)
    engine = create_engine(url)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with engine.begin() as conn:
        user_id = _insert_user(conn, now)
        orphan_id = _insert_document(
            conn, user_id=user_id, now=now, mime="image/jpeg", number="FT A/123", deleted=True
        )
        _insert_link(
            conn,
            user_id=user_id,
            document_id=orphan_id,
            now=now,
            source_key="atcud:DRIFT",
            outcome="linked_existing",
            payload=_payload(),
        )
    command.upgrade(cfg, "head")
    with engine.connect() as conn:
        count = conn.execute(
            text(
                "SELECT count(*) FROM documents WHERE deleted_at IS NULL AND invoice_number = 'FT A/123'"
            )
        ).scalar()
        assert count == 1, count
    engine.dispose()
    print("migration 011 model drift passed")


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


def _stamp() -> None:
    """A database already at 011, without the identity column, upgrades to head."""
    from alembic import command
    from alembic.config import Config

    url = os.environ["DATABASE_URL"]
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, STAMP)
    engine = create_engine(url)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == STAMP
        column = conn.execute(
            text(
                "SELECT count(*) FROM information_schema.columns "
                "WHERE table_name = 'documents' AND column_name = 'at_invoice_identity'"
            )
        ).scalar()
        assert column == 0
    command.upgrade(cfg, "head")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == HEAD
        column = conn.execute(
            text(
                "SELECT count(*) FROM information_schema.columns "
                "WHERE table_name = 'documents' AND column_name = 'at_invoice_identity'"
            )
        ).scalar()
        assert column == 1
        indexdef = conn.execute(
            text(
                "SELECT indexdef FROM pg_indexes WHERE indexname = 'uq_documents_at_invoice_identity'"
            )
        ).scalar()
        assert indexdef and "deleted_at IS NULL" in indexdef
    engine.dispose()
    print("migration 012 from stamped 011 passed")


def _dupes() -> None:
    """Duplicate AT rows left by an older 011 collapse to one live row."""
    from alembic import command
    from alembic.config import Config

    url = os.environ["DATABASE_URL"]
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, STAMP)
    engine = create_engine(url)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with engine.begin() as conn:
        user_id = _insert_user(conn, now)
        for _ in range(2):
            _insert_document(
                conn,
                user_id=user_id,
                now=now,
                mime="application/vnd.invoflow.efatura+json",
                number="FT 2026/101",
                deleted=False,
            )
    command.upgrade(cfg, "head")
    with engine.connect() as conn:
        live = conn.execute(
            text(
                "SELECT count(*) FROM documents WHERE deleted_at IS NULL AND invoice_number = 'FT 2026/101'"
            )
        ).scalar()
        hidden = conn.execute(
            text(
                "SELECT count(*) FROM documents WHERE deleted_at IS NOT NULL AND invoice_number = 'FT 2026/101'"
            )
        ).scalar()
        audits = conn.execute(
            text("SELECT count(*) FROM audit_logs WHERE action = 'efatura_dedupe'")
        ).scalar()
        assert live == 1, live
        assert hidden == 1, hidden
        assert audits == 1, audits
    engine.dispose()
    print("migration 012 dedupe passed")


def _insert_at(
    conn,
    *,
    user_id: str,
    number: str,
    vat: str,
    status: str,
    category: str,
    created,
    updated,
    deleted,
    identity: str | None,
    review_notes: str | None,
) -> str:
    document_id = str(uuid.uuid4())
    columns = (
        "id, user_id, status, storage_key, original_filename, mime_type, "
        "invoice_number, document_type, vendor_nif, vendor_name, net_amount, vat_amount, "
        "gross_amount, expense_category, review_notes, document_date, ocr_raw_response, "
        "deleted_at, created_at, updated_at"
    )
    values = (
        ":id, :user_id, :status, :storage_key, 'at.efatura', "
        "'application/vnd.invoflow.efatura+json', :number, 'FT', '123456002', 'Loja', "
        "10.00, :vat, :gross, :category, :notes, '2026-04-01', :raw, :deleted_at, "
        ":created, :updated"
    )
    params = {
        "id": document_id,
        "user_id": user_id,
        "status": status,
        "storage_key": f"efatura/{document_id}.efatura",
        "number": number,
        "vat": vat,
        "gross": str(Decimal(vat) + Decimal("10.00")),
        "category": category,
        "notes": review_notes,
        "raw": json.dumps({"source": "efatura"}),
        "deleted_at": deleted,
        "created": created,
        "updated": updated,
    }
    if identity is not None:
        columns += ", at_invoice_identity"
        values += ", :identity"
        params["identity"] = identity
    conn.execute(
        text(f"INSERT INTO documents ({columns}) VALUES ({values})"),
        params,
    )
    return document_id


def _keeper() -> None:
    """The reviewed duplicate survives, and distinct numbers are not merged."""
    from alembic import command
    from alembic.config import Config

    url = os.environ["DATABASE_URL"]
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, STAMP)
    engine = create_engine(url)
    base = datetime.now(timezone.utc).replace(tzinfo=None)
    with engine.begin() as conn:
        user_id = _insert_user(conn, base)
        loser = _insert_at(
            conn,
            user_id=user_id,
            number="FT 5/1",
            vat="2.30",
            status="needs_review",
            category="other",
            created=base,
            updated=base + timedelta(hours=2),
            deleted=None,
            identity=None,
            review_notes=None,
        )
        keeper = _insert_at(
            conn,
            user_id=user_id,
            number="FT 5/01",
            vat="2.00",
            status="ready",
            category="office",
            created=base + timedelta(minutes=1),
            updated=base + timedelta(minutes=1),
            deleted=None,
            identity=None,
            review_notes="VAT corrected",
        )
        for number, vat in (
            ("FT A01/5", "2.30"),
            ("FT A1/5", "4.60"),
            ("FT 1 23/4", "3.00"),
            ("FT 12 3/4", "1.00"),
        ):
            _insert_at(
                conn,
                user_id=user_id,
                number=number,
                vat=vat,
                status="needs_review",
                category="other",
                created=base + timedelta(minutes=5),
                updated=base + timedelta(minutes=5),
                deleted=None,
                identity=None,
                review_notes=None,
            )
        _insert_link(
            conn,
            user_id=user_id,
            document_id=loser,
            now=base,
            source_key="doc:123456002:FT:ft 5/1",
            outcome="created",
            payload=_payload(),
        )
    command.upgrade(cfg, "head")
    with engine.connect() as conn:
        live = conn.execute(
            text(
                "SELECT invoice_number, status, expense_category, vat_amount "
                "FROM documents WHERE user_id = :user_id AND deleted_at IS NULL "
                "ORDER BY invoice_number"
            ),
            {"user_id": user_id},
        ).mappings().all()
        assert len(live) == 5, [row["invoice_number"] for row in live]
        total = conn.execute(
            text(
                "SELECT coalesce(sum(vat_amount), 0) FROM documents "
                "WHERE user_id = :user_id AND deleted_at IS NULL"
            ),
            {"user_id": user_id},
        ).scalar()
        assert Decimal(total) == Decimal("12.90"), total
        numbers = {row["invoice_number"] for row in live}
        assert "FT 5/01" in numbers
        assert "FT 5/1" not in numbers
        assert {"FT A01/5", "FT A1/5", "FT 1 23/4", "FT 12 3/4"} <= numbers
        kept = next(row for row in live if row["invoice_number"] == "FT 5/01")
        assert kept["status"] == "ready"
        assert kept["expense_category"] == "office"
        assert Decimal(kept["vat_amount"]) == Decimal("2.00")
        pointed = conn.execute(
            text("SELECT document_id FROM efatura_links WHERE source_key = 'doc:123456002:FT:ft 5/1'")
        ).scalar()
        assert pointed == keeper
        hidden = conn.execute(
            text(
                "SELECT count(*) FROM documents WHERE id = :id AND deleted_at IS NOT NULL"
            ),
            {"id": loser},
        ).scalar()
        assert hidden == 1
        audits = conn.execute(
            text("SELECT changes_json FROM audit_logs WHERE action = 'efatura_dedupe'")
        ).scalars().all()
        assert len(audits) == 1
        assert keeper in audits[0]
    engine.dispose()
    print("migration 012 keeps the reviewed row passed")


def _legacy_011() -> None:
    """71576aa's 011 already had a non-partial unique index. Upgrade must succeed."""
    from alembic import command
    from alembic.config import Config

    url = os.environ["DATABASE_URL"]
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, STAMP)
    engine = create_engine(url)
    base = datetime.now(timezone.utc).replace(tzinfo=None)
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE documents ADD COLUMN at_invoice_identity VARCHAR(200)"))
        conn.execute(
            text(
                "CREATE UNIQUE INDEX uq_documents_at_invoice_identity "
                "ON documents (user_id, at_invoice_identity)"
            )
        )
        user_id = _insert_user(conn, base)
        _insert_at(
            conn,
            user_id=user_id,
            number="FT5/9",
            vat="1.00",
            status="needs_review",
            category="other",
            created=base,
            updated=base,
            deleted=base,
            identity="123456002|FT|ft5/9",
            review_notes=None,
        )
        _insert_at(
            conn,
            user_id=user_id,
            number="FT 5/9",
            vat="1.50",
            status="needs_review",
            category="other",
            created=base + timedelta(minutes=1),
            updated=base + timedelta(minutes=1),
            deleted=None,
            identity="123456002|FT|ft 5/9",
            review_notes=None,
        )
        _insert_at(
            conn,
            user_id=user_id,
            number="FT A1/5",
            vat="2.30",
            status="needs_review",
            category="other",
            created=base,
            updated=base,
            deleted=base,
            identity="123456002|FT|ft a1/5",
            review_notes=None,
        )
        _insert_at(
            conn,
            user_id=user_id,
            number="FT A1/005",
            vat="2.30",
            status="ready",
            category="office",
            created=base + timedelta(minutes=1),
            updated=base + timedelta(minutes=1),
            deleted=None,
            identity="123456002|FT|ft a1/005",
            review_notes=None,
        )
    command.upgrade(cfg, "head")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == HEAD
        rows = {
            row["invoice_number"]: row
            for row in conn.execute(
                text(
                    "SELECT invoice_number, deleted_at, at_invoice_identity FROM documents"
                )
            ).mappings()
        }
        assert rows["FT5/9"]["deleted_at"] is not None
        assert rows["FT 5/9"]["deleted_at"] is None
        assert rows["FT5/9"]["at_invoice_identity"] == "123456002|FT|ft5/9"
        assert rows["FT 5/9"]["at_invoice_identity"] == "123456002|FT|ft 5/9"
        assert rows["FT A1/5"]["deleted_at"] is not None
        assert rows["FT A1/005"]["deleted_at"] is None
        assert rows["FT A1/5"]["at_invoice_identity"] == "123456002|FT|ft a1/5"
        assert rows["FT A1/005"]["at_invoice_identity"] == rows["FT A1/5"]["at_invoice_identity"]
        indexdef = conn.execute(
            text(
                "SELECT indexdef FROM pg_indexes WHERE indexname = 'uq_documents_at_invoice_identity'"
            )
        ).scalar()
        assert indexdef and "deleted_at IS NULL" in indexdef
    engine.dispose()
    print("migration 012 from 71576aa 011 passed")


def main() -> None:
    if "--child" in sys.argv:
        _child()
        return
    if "--drift" in sys.argv:
        _drift()
        return
    if "--stamp" in sys.argv:
        _stamp()
        return
    if "--dupes" in sys.argv:
        _dupes()
        return
    if "--keeper" in sys.argv:
        _keeper()
        return
    if "--legacy" in sys.argv:
        _legacy_011()
        return
    name = f"mig011_{uuid.uuid4().hex[:8]}"
    drift = f"mig011d_{uuid.uuid4().hex[:8]}"
    stamp = f"mig011s_{uuid.uuid4().hex[:8]}"
    dupes = f"mig011u_{uuid.uuid4().hex[:8]}"
    keeper = f"mig011k_{uuid.uuid4().hex[:8]}"
    legacy = f"mig011b_{uuid.uuid4().hex[:8]}"
    try:
        _run(name, "--child")
        print("migration 011 passed")
        _run(drift, "--drift")
        _run(stamp, "--stamp")
        _run(dupes, "--dupes")
        _run(keeper, "--keeper")
        _run(legacy, "--legacy")
    finally:
        for database in (name, drift, stamp, dupes, keeper, legacy):
            _drop(database)


if __name__ == "__main__":
    main()

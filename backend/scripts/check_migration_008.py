"""Up, down, up of migration 008 on Postgres, with the amounts restored.

Refuses sqlite. The migrations job runs this against its Postgres service.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text


def _money(value) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def main() -> None:
    url = os.environ.get("DATABASE_URL", "")
    if not url.startswith("postgres"):
        raise SystemExit("DATABASE_URL must be a Postgres URL")

    cfg = Config("alembic.ini")
    engine = create_engine(url)
    user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    rows = {
        "neg": {
            "net": "-8.13",
            "vat": "1.87",
            "gross": "-10.00",
            "status": "ready",
            "raw": None,
        },
        "qr": {
            "net": "-8.13",
            "vat": "-1.87",
            "gross": "-10.00",
            "status": "ready",
            "raw": json.dumps({"qr": {"document_type": "NC"}}),
        },
        "pos": {
            "net": "10.00",
            "vat": "2.30",
            "gross": "12.30",
            "status": "ready",
            "raw": None,
        },
        "fs": {
            "net": "10.00",
            "vat": "2.30",
            "gross": "12.30",
            "status": "needs_review",
            "raw": json.dumps({"qr": {"document_type": "FS"}}),
        },
    }
    ids = {name: str(uuid.uuid4()) for name in rows}

    def upgrade_head() -> None:
        command.upgrade(cfg, "head")

    def snapshot() -> dict:
        with engine.connect() as conn:
            found = conn.execute(
                text(
                    "SELECT id, net_amount, vat_amount, gross_amount, status, "
                    "document_type, ocr_raw_response FROM documents WHERE user_id = :user_id"
                ),
                {"user_id": user_id},
            ).mappings()
            return {row["id"]: dict(row) for row in found}

    try:
        command.downgrade(cfg, "007_efatura_links")
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO users (id, clerk_id, email, created_at, updated_at) "
                    "VALUES (:id, :clerk_id, :email, :created_at, :updated_at)"
                ),
                {
                    "id": user_id,
                    "clerk_id": f"mig008-{user_id[:8]}",
                    "email": "mig008@example.com",
                    "created_at": now,
                    "updated_at": now,
                },
            )
            for name, amounts in rows.items():
                conn.execute(
                    text(
                        "INSERT INTO documents ("
                        "id, user_id, status, storage_key, original_filename, mime_type, "
                        "net_amount, vat_amount, gross_amount, ocr_raw_response, "
                        "created_at, updated_at"
                        ") VALUES ("
                        ":id, :user_id, :status, :storage_key, :original_filename, :mime_type, "
                        ":net_amount, :vat_amount, :gross_amount, :ocr_raw_response, "
                        ":created_at, :updated_at)"
                    ),
                    {
                        "id": ids[name],
                        "user_id": user_id,
                        "status": amounts["status"],
                        "storage_key": f"mig/{name}.jpg",
                        "original_filename": f"{name}.jpg",
                        "mime_type": "image/jpeg",
                        "net_amount": amounts["net"],
                        "vat_amount": amounts["vat"],
                        "gross_amount": amounts["gross"],
                        "ocr_raw_response": amounts["raw"],
                        "created_at": now,
                        "updated_at": now,
                    },
                )

        command.upgrade(cfg, "008_document_type")
        first = snapshot()
        neg = first[ids["neg"]]
        assert neg["document_type"] == "unclassified"
        assert neg["status"] == "needs_review"
        assert _money(neg["gross_amount"]) == Decimal("10.00")
        assert _money(neg["net_amount"]) == Decimal("8.13")
        qr = first[ids["qr"]]
        assert qr["document_type"] == "NC"
        assert qr["status"] == "ready"
        assert _money(qr["gross_amount"]) == Decimal("10.00")
        assert first[ids["pos"]]["document_type"] == "FT"
        assert _money(first[ids["pos"]]["gross_amount"]) == Decimal("12.30")
        assert first[ids["fs"]]["document_type"] == "FS"
        assert first[ids["fs"]]["status"] == "needs_review"

        command.downgrade(cfg, "007_efatura_links")
        with engine.connect() as conn:
            columns = {col["name"] for col in conn.execute(text(
                "SELECT column_name AS name FROM information_schema.columns "
                "WHERE table_name = 'documents'"
            )).mappings()}
        assert "document_type" not in columns
        with engine.connect() as conn:
            restored = {
                row["id"]: dict(row)
                for row in conn.execute(
                    text(
                        "SELECT id, net_amount, vat_amount, gross_amount, status, ocr_raw_response "
                        "FROM documents WHERE user_id = :user_id"
                    ),
                    {"user_id": user_id},
                ).mappings()
            }
        assert _money(restored[ids["neg"]]["gross_amount"]) == Decimal("-10.00")
        assert _money(restored[ids["neg"]]["net_amount"]) == Decimal("-8.13")
        assert restored[ids["neg"]]["status"] == "ready"
        assert _money(restored[ids["qr"]]["vat_amount"]) == Decimal("-1.87")
        assert json.loads(restored[ids["qr"]]["ocr_raw_response"]) == {"qr": {"document_type": "NC"}}
        assert restored[ids["pos"]]["status"] == "ready"
        assert _money(restored[ids["fs"]]["gross_amount"]) == Decimal("12.30")

        command.upgrade(cfg, "008_document_type")
        second = snapshot()
        for name in rows:
            left = first[ids[name]]
            right = second[ids[name]]
            assert right["document_type"] == left["document_type"]
            assert right["status"] == left["status"]
            assert _money(right["net_amount"]) == _money(left["net_amount"])
            assert _money(right["vat_amount"]) == _money(left["vat_amount"])
            assert _money(right["gross_amount"]) == _money(left["gross_amount"])
        print("migration 008 up/down/up is lossless")
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM documents WHERE user_id = :user_id"), {"user_id": user_id})
            conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
        upgrade_head()


if __name__ == "__main__":
    main()

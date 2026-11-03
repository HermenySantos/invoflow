"""A user-edited AT number on Postgres 16: no VAT lost or doubled, and the unique index holds.

Postgres only. Runs the real PATCH endpoint and the importer against the
partial unique index on (user_id, at_invoice_identity):

- G-1: 'FT a/5' (4.60) edited to 'FT A/5', then the real 'FT A/5' (2.30)
  arrives. It is held on its own row and the total is 6.90. Respelling the
  edited row onto the held row's number is a 409.
- G-2: main's lowercased doc key overwrote the 'FT A/5' row's link with
  'FT a/5' (4.60), and a user edited the row to 'FT a/5'. A pull gives
  6.90 with the overwritten invoice on its own row in review.
- Two rows whose numbers a user swapped get their identities back in one
  pull, through NULL, without a unique violation.
Each pull runs twice and the second changes nothing.
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

BACKEND = Path(__file__).resolve().parents[1]
NIF = "296123456"
TAXPAYER = "555555555"


def _admin_url():
    url = os.environ.get("DATABASE_URL", "")
    if not url.startswith("postgres"):
        raise SystemExit("DATABASE_URL must be a Postgres URL")
    return make_url(url)


def _recreate(name: str) -> str:
    engine = create_engine(_admin_url().set(database="postgres"), isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    engine.dispose()
    return _admin_url().set(database=name).render_as_string(hide_password=False)


def _drop(name: str) -> None:
    engine = create_engine(_admin_url().set(database="postgres"), isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    engine.dispose()


def _migrate(url: str) -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")


def _invoice(number: str, vat: str, atcud: str | None = None):
    from app.services.efatura import EFaturaInvoice, VatLine

    tax = Decimal(vat)
    return EFaturaInvoice(
        document_type="FT",
        invoice_number=number,
        issue_date=date(2026, 4, 1),
        issuer_nif=NIF,
        acquirer_nif=TAXPAYER,
        acquirer_country="PT",
        fiscal_status="normal",
        lines=(VatLine("IVA", "PT", "NOR", Decimal("23"), Decimal("10"), tax, None),),
        tax_payable=tax,
        net_total=Decimal("10"),
        gross_total=Decimal("10") + tax,
        atcud=atcud,
        issuer_name="Loja",
    )


class Account:
    def __init__(self, url: str, client) -> None:
        self.engine = create_engine(url)
        self.client = client
        self.headers = {"X-Mock-User-Id": f"edited-{uuid.uuid4().hex[:8]}"}
        assert client.get("/api/documents", headers=self.headers).status_code == 200
        with self.engine.connect() as conn:
            self.user_id = conn.execute(
                text("SELECT id FROM users WHERE clerk_id = :clerk"), {"clerk": self.headers["X-Mock-User-Id"]}
            ).scalar_one()

    def pull(self, *invoices):
        from app.services.efatura import import_purchases

        db = sessionmaker(bind=self.engine)()
        try:
            result = import_purchases(db, user_id=self.user_id, taxpayer_nif=TAXPAYER, invoices=list(invoices))
            db.commit()
            return result
        finally:
            db.close()

    def patch(self, document_id: str, **fields):
        return self.client.patch(f"/api/documents/{document_id}", headers=self.headers, json=fields)

    def rows(self):
        with self.engine.connect() as conn:
            return sorted(
                (row.id, row.invoice_number, Decimal(row.vat_amount), row.status, row.at_invoice_identity)
                for row in conn.execute(
                    text(
                        "SELECT id, invoice_number, vat_amount, status, at_invoice_identity "
                        "FROM documents WHERE user_id = :user AND deleted_at IS NULL"
                    ),
                    {"user": self.user_id},
                )
            )

    def vat(self):
        return sorted(row[2] for row in self.rows())

    def warning_on(self, document_id: str):
        with self.engine.connect() as conn:
            return conn.execute(
                text("SELECT warning FROM efatura_links WHERE document_id = :id"), {"id": document_id}
            ).scalar_one()

    def snapshot(self):
        with self.engine.connect() as conn:
            links = sorted(
                tuple(row)
                for row in conn.execute(
                    text("SELECT id, document_id, outcome, warning FROM efatura_links WHERE user_id = :user"),
                    {"user": self.user_id},
                )
            )
            audits = conn.execute(
                text("SELECT count(*) FROM audit_logs WHERE user_id = :user"), {"user": self.user_id}
            ).scalar_one()
        return self.rows(), links, audits


EXPECTED = [Decimal("2.30"), Decimal("4.60")]


def check_g1(account: Account) -> None:
    from app.services.efatura import at_invoice_identity, review_receipt_id

    lower = _invoice("FT a/5", "4.60")
    upper = _invoice("FT A/5", "2.30")
    edited_id = account.pull(lower).created[0]
    assert account.patch(edited_id, invoice_number="FT A/5").status_code == 200

    result = account.pull(upper, lower)
    assert result.linked_existing == (), result
    held_id = result.created[0]
    assert account.vat() == EXPECTED, account.rows()
    held = next(row for row in account.rows() if row[0] == held_id)
    assert held[1:4] == ("FT A/5", Decimal("2.30"), "needs_review"), held
    assert review_receipt_id(account.warning_on(held_id)) == edited_id
    edited = next(row for row in account.rows() if row[0] == edited_id)
    assert edited[4] == at_invoice_identity(NIF, "FT", "FT a/5"), edited

    respelled = account.patch(edited_id, invoice_number="FTA/5")
    assert respelled.status_code == 409, respelled.text
    assert "FT A/5" in respelled.json()["detail"]

    before = account.snapshot()
    account.pull(upper, lower)
    assert account.snapshot() == before
    print("G-1 on Postgres: 4.60 + 2.30 = 6.90, held row names the edited row")


def check_g2(account: Account) -> None:
    from app.services.efatura import _payload, review_receipt_id

    edited_id = account.pull(_invoice("FT A/5", "2.30")).created[0]
    with account.engine.begin() as conn:
        conn.execute(
            text("UPDATE efatura_links SET payload_json = :payload WHERE document_id = :id"),
            {"payload": _payload(_invoice("FT a/5", "4.60")), "id": edited_id},
        )
    assert account.patch(edited_id, invoice_number="FT a/5").status_code == 200
    assert account.vat() == [Decimal("2.30")]

    account.pull(_invoice("FT A/5", "2.30"), _invoice("FT a/5", "4.60"))
    assert account.vat() == EXPECTED, account.rows()
    split = next(row for row in account.rows() if row[0] != edited_id)
    assert split[1:4] == ("FT a/5", Decimal("4.60"), "needs_review"), split
    assert review_receipt_id(account.warning_on(split[0])) == edited_id

    before = account.snapshot()
    account.pull(_invoice("FT a/5", "4.60"), _invoice("FT A/5", "2.30"))
    assert account.snapshot() == before
    print("G-2 on Postgres: 2.30 + 4.60 = 6.90, split row names the edited row")


def check_swap(account: Account) -> None:
    from app.services.efatura import at_invoice_identity

    upper = _invoice("FT A/5", "2.30", "SWAP-UPPER")
    lower = _invoice("FT a/5", "4.60", "SWAP-LOWER")
    upper_id, lower_id = account.pull(upper, lower).created
    assert account.patch(upper_id, invoice_number="FT X/5").status_code == 200
    assert account.patch(lower_id, invoice_number="FT A/5").status_code == 200
    assert account.patch(upper_id, invoice_number="FT a/5").status_code == 200

    result = account.pull(upper, lower)
    assert result.created == () and result.linked_existing == (), result
    identities = {row[0]: row[4] for row in account.rows()}
    assert identities == {
        upper_id: at_invoice_identity(NIF, "FT", "FT A/5"),
        lower_id: at_invoice_identity(NIF, "FT", "FT a/5"),
    }, identities
    assert account.vat() == EXPECTED
    print("swapped numbers on Postgres: identities restored through NULL")


def main() -> None:
    name = f"edited_{uuid.uuid4().hex[:8]}"
    try:
        url = _recreate(name)
        os.environ["DATABASE_URL"] = url
        os.environ.setdefault("AUTH_MOCK_MODE", "true")
        os.environ.setdefault("MOCK_AUTH", "1")
        os.environ.setdefault("STORAGE_MOCK_MODE", "true")
        os.environ.setdefault("OCR_MOCK_MODE", "true")
        os.environ.setdefault("APP_DEBUG", "true")
        sys.path.insert(0, str(BACKEND))
        _migrate(url)
        from fastapi.testclient import TestClient

        from app.main import app

        with TestClient(app) as client:
            for check in (check_g1, check_g2, check_swap):
                check(Account(url, client))
        print("edited AT rows passed")
    finally:
        from app.core.database import engine

        engine.dispose()
        _drop(name)


if __name__ == "__main__":
    main()

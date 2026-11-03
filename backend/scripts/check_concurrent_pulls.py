"""Two pulls of 'FT A/5' and 'FT a/5' without an ATCUD, at the same time.

Postgres only. Both invoices want the doc key doc:<nif>:FT:ft a/5 first.
Each pull keeps its transaction open between invoices, so the two pulls
overlap on that key. Both finish, and each invoice is one live AT row with
one link, also after a second pair of concurrent pulls.
"""

from __future__ import annotations

import os
import sys
import threading
import time
import uuid
from datetime import date, datetime
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


def _seed(url: str) -> str:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    engine = create_engine(url)
    user_id = str(uuid.uuid4())
    now = datetime.utcnow()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO users (id, clerk_id, email, created_at, updated_at) "
                "VALUES (:id, :clerk, 'pulls@example.com', :now, :now)"
            ),
            {"id": user_id, "clerk": f"pulls-{user_id[:8]}", "now": now},
        )
        conn.execute(
            text(
                "INSERT INTO efatura_subjects (user_id, taxpayer_nif, updated_at) "
                "VALUES (:id, :nif, :now)"
            ),
            {"id": user_id, "nif": TAXPAYER, "now": now},
        )
    engine.dispose()
    return user_id


def _invoice(number: str, vat: str):
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
        issuer_name="Loja",
    )


def _pull(url: str, user_id: str, numbers, errors: list[BaseException]) -> None:
    from app.services.efatura import import_purchases

    engine = create_engine(url)
    db = sessionmaker(bind=engine)()
    try:
        import_purchases(
            db,
            user_id=user_id,
            taxpayer_nif=TAXPAYER,
            invoices=[_invoice(number, vat) for number, vat in numbers],
            after_invoice=lambda _invoice: time.sleep(0.3),
        )
        db.commit()
    except Exception as exc:
        errors.append(exc)
    finally:
        db.close()
        engine.dispose()


def _race(url: str, user_id: str) -> None:
    errors: list[BaseException] = []
    pulls = [
        threading.Thread(target=_pull, args=(url, user_id, (("FT A/5", "2.30"), ("FT a/5", "4.60")), errors)),
        threading.Thread(target=_pull, args=(url, user_id, (("FT a/5", "4.60"), ("FT A/5", "2.30")), errors)),
    ]
    for pull in pulls:
        pull.start()
    for pull in pulls:
        pull.join()
    if errors:
        raise errors[0]


def _state(url: str):
    engine = create_engine(url)
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT invoice_number, vat_amount FROM documents WHERE deleted_at IS NULL")
        ).all()
        links = conn.execute(
            text(
                "SELECT l.source_key, d.invoice_number FROM efatura_links l "
                "JOIN documents d ON d.id = l.document_id"
            )
        ).all()
    engine.dispose()
    return sorted((number, Decimal(vat)) for number, vat in rows), [tuple(link) for link in links]


def main() -> None:
    name = f"pulls_{uuid.uuid4().hex[:8]}"
    try:
        url = _recreate(name)
        os.environ["DATABASE_URL"] = url
        sys.path.insert(0, str(BACKEND))
        user_id = _seed(url)
        expected_rows = [("FT A/5", Decimal("2.30")), ("FT a/5", Decimal("4.60"))]
        for round_ in (1, 2):
            _race(url, user_id)
            rows, links = _state(url)
            assert rows == expected_rows, (round_, rows)
            assert sorted(number for _key, number in links) == ["FT A/5", "FT a/5"], (round_, links)
            assert f"doc:{NIF}:FT:ft a/5" in {key for key, _number in links}, (round_, links)
        print("concurrent pulls passed")
    finally:
        _drop(name)


if __name__ == "__main__":
    main()

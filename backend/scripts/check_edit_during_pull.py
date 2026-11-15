"""A PATCH that renumbers an AT row while a pull is running, on Postgres 16 (GIL-207 L-1).

Postgres only. 'FT a/5' (4.60) is stored. A pull carrying the real 'FT A/5'
(2.30) is held inside its match step while the real PATCH endpoint renames
the stored row to 'FT A/5'. The pull read the account's edits before the
PATCH, so if the PATCH commits mid-pull the new invoice links to the edited
row and the total is 9.20. The PATCH must wait for the pull instead: it then
gets a 409, and the total is 6.90 on that pull and on every later one.
Runs with and without ATCUD.
"""

from __future__ import annotations

import sys
import threading
import uuid
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_edited_at_rows as base  # noqa: E402

HOLD_SECONDS = 2.0


def check_race(account: base.Account, atcud: bool) -> None:
    import app.services.efatura as efatura

    tag = uuid.uuid4().hex[:6]
    lower = base._invoice("FT a/5", "4.60", f"RACE-LOWER-{tag}" if atcud else None)
    upper = base._invoice("FT A/5", "2.30", f"RACE-UPPER-{tag}" if atcud else None)
    edited_id = account.pull(lower).created[0]

    in_match = threading.Event()
    release = threading.Event()
    original = efatura._match_documents

    def held_match(*args, **kwargs):
        if not in_match.is_set():
            in_match.set()
            release.wait(HOLD_SECONDS)
        return original(*args, **kwargs)

    errors: list[BaseException] = []

    def pull() -> None:
        try:
            account.pull(upper)
        except BaseException as exc:  # surfaced below
            errors.append(exc)

    efatura._match_documents = held_match
    try:
        puller = threading.Thread(target=pull)
        puller.start()
        assert in_match.wait(10), "the pull never reached its match step"
        response = account.patch(edited_id, invoice_number="FT A/5")
        release.set()
        puller.join(30)
    finally:
        efatura._match_documents = original
    assert not errors, errors

    assert account.vat() == base.EXPECTED, (response.status_code, account.rows())
    assert response.status_code == 409, response.text
    for _ in range(3):
        account.pull(upper, lower)
        assert account.vat() == base.EXPECTED, account.rows()
    label = "atcud" if atcud else "doc-key"
    print(f"PATCH during a pull ({label}): waited for the pull, 409, 4.60 + 2.30 = 6.90 over 3 more pulls")


def main() -> None:
    import os

    name = f"editpull_{uuid.uuid4().hex[:8]}"
    try:
        url = base._recreate(name)
        os.environ["DATABASE_URL"] = url
        os.environ.setdefault("AUTH_MOCK_MODE", "true")
        os.environ.setdefault("MOCK_AUTH", "1")
        os.environ.setdefault("STORAGE_MOCK_MODE", "true")
        os.environ.setdefault("OCR_MOCK_MODE", "true")
        os.environ.setdefault("APP_DEBUG", "true")
        sys.path.insert(0, str(base.BACKEND))
        base._migrate(url)
        from fastapi.testclient import TestClient

        from app.main import app

        with TestClient(app) as client:
            for atcud in (False, True):
                check_race(base.Account(url, client), atcud)
        print("PATCH during a pull passed")
    finally:
        from app.core.database import engine

        engine.dispose()
        base._drop(name)


if __name__ == "__main__":
    main()

"""GIL-207. Follow-ups from the QA gate on PR #38 (GATE-209aff7).

L-1 (a PATCH landing inside a pull) needs two Postgres connections and is
checked by scripts/check_edit_during_pull.py.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.efatura import EfaturaLink
from app.services.efatura import _source_key
from tests.test_gil160_linked_delete import _purchase, _user
from tests.test_gil205_series_case import NIF, _at, _pull, _scan_numbered
from tests.test_gil206_edited_rows import EXPECTED, LOWER, UPPER, _patch, _vat
from tests.test_migration_014_identity import load_migration_014
from tests.test_migration_014_split import LOWERCASED_DOC_KEY, _at_row, _link, _run, _snapshot

NOT_IMPORTED = "efatura_not_imported"
CONFLICT = "efatura_identity_conflict"


def _warnings(client: TestClient, headers, code: str) -> dict[str, list[str]]:
    listed = client.get("/api/documents", headers=headers)
    assert listed.status_code == 200, listed.text
    found = {}
    for row in listed.json()["documents"]:
        messages = [w["message"] for w in row["validation_warnings"] if w["code"] == code]
        if messages:
            found[row["id"]] = messages
    return found


def _summary_warnings(client: TestClient, headers) -> list[str]:
    response = client.get("/api/summary?period_type=quarter&year=2026&quarter=2", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["warnings"]


def _pair(atcud: bool):
    if atcud:
        return _at("FT A/5", "L-UPPER"), _at("FT a/5", "L-LOWER", vat="4.60")
    return _purchase("FT A/5"), _purchase("FT a/5", vat="4.60")


# L-2: an invoice held back as ambiguous_duplicate stays visible until the user resolves it.


def _blocked_by_an_edited_row(client, db: Session):
    """The QA's AMB1: an edited 'FT a/5' row renamed 'FT A/5', and a second live row holds ft a/5."""
    user, headers = _user(db)
    edited_id = _pull(db, user, _at("FT a/5", "AMB-LOWER", vat="4.60")).created[0]
    _patch(client, headers, edited_id, invoice_number="FT A/5")
    duplicate = _at_row(db, user, "FT a/5", LOWER)
    duplicate.vat_amount, duplicate.gross_amount = Decimal("4.60"), Decimal("14.60")
    db.commit()
    result = _pull(db, user, _at("FT A/5", "AMB-UPPER"))
    assert [skip.outcome for skip in result.skipped] == ["ambiguous_duplicate"]
    return user, headers, edited_id, duplicate.id


def test_l2_a_held_back_invoice_is_shown_on_the_row_after_every_pull(client, db: Session):
    user, headers, edited_id, _duplicate_id = _blocked_by_an_edited_row(client, db)

    for _ in range(3):
        shown = _warnings(client, headers, NOT_IMPORTED)
        assert list(shown) == [edited_id]
        assert "A fatura n.º FT A/5 do e-Fatura não foi importada" in shown[edited_id][0]
        single = client.get(f"/api/documents/{edited_id}", headers=headers).json()
        assert NOT_IMPORTED in [w["code"] for w in single["validation_warnings"]]
        assert any("fatura do e-Fatura por importar" in line for line in _summary_warnings(client, headers))
        result = _pull(db, user, _at("FT A/5", "AMB-UPPER"), _at("FT a/5", "AMB-LOWER", vat="4.60"))
        assert result.skipped == () and result.warnings == ()


def test_l2_deleting_the_duplicate_lets_the_next_pull_store_the_invoice(client, db: Session):
    user, headers, edited_id, duplicate_id = _blocked_by_an_edited_row(client, db)
    assert client.delete(f"/api/documents/{duplicate_id}", headers=headers).status_code == 204

    result = _pull(db, user, _at("FT A/5", "AMB-UPPER"), _at("FT a/5", "AMB-LOWER", vat="4.60"))

    assert len(result.created) == 1
    stored = db.get(Document, result.created[0])
    assert (stored.invoice_number, stored.vat_amount) == ("FT A/5", Decimal("2.30"))
    assert _vat(db, user) == EXPECTED
    assert _warnings(client, headers, NOT_IMPORTED) == {}
    assert not any("por importar" in line for line in _summary_warnings(client, headers))
    before = _snapshot(db)
    _pull(db, user, _at("FT A/5", "AMB-UPPER"), _at("FT a/5", "AMB-LOWER", vat="4.60"))
    assert [row[:4] for row in _snapshot(db)[1]] == [row[:4] for row in before[1]]


def test_l2_two_matching_scans_show_the_held_invoice_until_one_is_deleted(client, db: Session):
    user, headers = _user(db)
    first = _scan_numbered(db, user, "FT A/5")
    second = _scan_numbered(db, user, "FT A/5")

    result = _pull(db, user, _purchase("FT A/5"))
    assert [skip.outcome for skip in result.skipped] == ["ambiguous_duplicate"]
    _pull(db, user, _purchase("FT A/5"))
    shown = _warnings(client, headers, NOT_IMPORTED)
    assert sorted(shown) == sorted([first.id, second.id])
    assert "corresponde a este recibo e a outro" in shown[first.id][0]

    assert client.delete(f"/api/documents/{second.id}", headers=headers).status_code == 204
    result = _pull(db, user, _purchase("FT A/5"))

    assert result.linked_existing == (first.id,)
    link = db.query(EfaturaLink).filter(EfaturaLink.user_id == user.id).one()
    assert (link.outcome, link.document_id) == ("linked_existing", first.id)
    assert _warnings(client, headers, NOT_IMPORTED) == {}


# L-3: rows main's old relink left wrong are shown for review, not silently changed.


def _g1_relinked(client, db: Session, atcud: bool):
    """The QA's G-1 after a pull under main: FT a/5's figures on two rows, FT A/5 on none."""
    user, headers = _user(db)
    upper, lower = _pair(atcud)
    edited_id = _pull(db, user, lower).created[0]
    _patch(client, headers, edited_id, invoice_number="FT A/5")
    edited = db.get(Document, edited_id)
    duplicate = _at_row(db, user, "FT a/5", LOWER)
    duplicate.vat_amount, duplicate.gross_amount = Decimal("4.60"), Decimal("14.60")
    lower_link = db.query(EfaturaLink).filter(EfaturaLink.document_id == edited_id).one()
    lower_link.document_id = duplicate.id
    db.commit()
    upper_key = _source_key(upper) if atcud else f"doc:{NIF}:FT:FT A/5"
    _link(db, user, edited, "FT A/5", upper_key, outcome="linked_existing")
    return user, headers, edited_id, duplicate.id, upper, lower


@pytest.mark.parametrize("atcud", [False, True], ids=["doc-key", "atcud"])
def test_l3_g1_left_by_main_is_flagged_on_both_rows_and_not_changed(client, db: Session, atcud):
    user, headers, edited_id, duplicate_id, upper, lower = _g1_relinked(client, db, atcud)
    assert sum(_vat(db, user)) == Decimal("9.20")

    for _ in range(2):
        _pull(db, user, upper, lower)
        assert sum(_vat(db, user)) == Decimal("9.20")
        shown = _warnings(client, headers, CONFLICT)
        assert sorted(shown) == sorted([edited_id, duplicate_id])
        assert "a fatura de origem (n.º FT a/5)" in shown[edited_id][0]
        assert "O IVA pode estar a contar duas vezes" in shown[duplicate_id][0]
        assert any("mesma fatura" in line for line in _summary_warnings(client, headers))


@pytest.mark.parametrize("atcud", [False, True], ids=["doc-key", "atcud"])
def test_l3_deleting_the_flagged_duplicate_restores_both_invoices(client, db: Session, atcud):
    user, headers, edited_id, duplicate_id, upper, lower = _g1_relinked(client, db, atcud)
    assert client.delete(f"/api/documents/{duplicate_id}", headers=headers).status_code == 204

    _pull(db, user, upper, lower)

    assert _vat(db, user) == EXPECTED
    assert _warnings(client, headers, CONFLICT) == {}
    edited = db.get(Document, edited_id)
    assert (edited.invoice_number, edited.vat_amount, edited.at_invoice_identity) == (
        "FT A/5",
        Decimal("4.60"),
        LOWER,
    )
    before = _snapshot(db)
    _pull(db, user, upper, lower)
    assert [row[:4] for row in _snapshot(db)[1]] == [row[:4] for row in before[1]]


def test_l3_g2_left_by_main_is_flagged_and_repaired_by_deleting_the_duplicate(client, db: Session):
    user, headers = _user(db)
    edited = _at_row(db, user, "FT A/5", f"{NIF}|FT|ft a/5")
    _link(db, user, edited, "FT a/5", LOWERCASED_DOC_KEY, vat="4.60")
    _patch(client, headers, edited.id, invoice_number="FT a/5")
    # Migration 014 as main shipped it gave the row its typed number's identity.
    assert db.get(Document, edited.id).at_invoice_identity == LOWER
    duplicate = _at_row(db, user, "FT A/5", UPPER)
    _link(db, user, duplicate, "FT A/5", f"doc:{NIF}:FT:FT A/5")
    upper, lower = _pair(atcud=False)

    _pull(db, user, upper, lower)
    assert sum(_vat(db, user)) == Decimal("4.60")
    assert sorted(_warnings(client, headers, CONFLICT)) == sorted([edited.id, duplicate.id])

    assert client.delete(f"/api/documents/{duplicate.id}", headers=headers).status_code == 204
    _pull(db, user, upper, lower)
    assert _vat(db, user) == EXPECTED
    assert _warnings(client, headers, CONFLICT) == {}


def test_l3_an_edited_row_the_app_did_not_pair_shows_nothing(client, db: Session):
    user, headers = _user(db)
    upper, lower = _pair(atcud=False)
    edited_id = _pull(db, user, lower).created[0]
    _patch(client, headers, edited_id, invoice_number="FT A/5")
    _pull(db, user, upper, lower)
    assert _vat(db, user) == EXPECTED
    assert _warnings(client, headers, CONFLICT) == {}
    assert _warnings(client, headers, NOT_IMPORTED) == {}


@pytest.mark.parametrize("atcud", [False, True], ids=["doc-key", "atcud"])
def test_l3_migration_014_runs_again_after_the_app_realigned_an_edited_row(client, db: Session, atcud):
    user, headers = _user(db)
    upper, lower = _pair(atcud)
    edited_id = _pull(db, user, lower).created[0]
    _patch(client, headers, edited_id, invoice_number="FT A/5")
    _pull(db, user, upper, lower)
    assert db.get(Document, edited_id).at_invoice_identity == LOWER
    before = _snapshot(db)

    migration = load_migration_014()
    assert _run(db, migration) == (0, 0, 0)
    assert _snapshot(db) == before
    assert _run(db, migration) == (0, 0, 0)
    _pull(db, user, upper, lower)
    assert _vat(db, user) == EXPECTED


def test_l3_migration_014_runs_again_after_a_swap(client, db: Session):
    user, headers = _user(db)
    upper_id, lower_id = _pull(db, user, *_pair(atcud=True)).created
    _patch(client, headers, upper_id, invoice_number="FT X/5")
    _patch(client, headers, lower_id, invoice_number="FT A/5")
    _patch(client, headers, upper_id, invoice_number="FT a/5")
    _pull(db, user, *_pair(atcud=True))
    before = _snapshot(db)

    assert _run(db, load_migration_014()) == (0, 0, 0)
    assert _snapshot(db) == before


def test_l3_migration_014_first_run_gives_an_edited_row_its_invoice_identity(db: Session):
    from tests.test_migration_014_split import _audit

    user, _headers = _user(db)
    row = _at_row(db, user, "FT A/5", f"{NIF}|FT|ft a/5")
    row.vat_amount, row.gross_amount = Decimal("4.60"), Decimal("14.60")
    _link(db, user, row, "FT a/5", LOWERCASED_DOC_KEY, vat="4.60")
    from datetime import datetime

    _audit(
        db,
        user,
        row,
        "update",
        "user",
        {"invoice_number": {"old": "FT a/5", "new": "FT A/5"}},
        datetime(2026, 5, 1),
    )
    _run(db, load_migration_014())
    assert db.get(Document, row.id).at_invoice_identity == LOWER

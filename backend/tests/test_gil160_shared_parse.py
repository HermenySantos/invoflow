"""GIL-160 F-1. The e-Fatura identity is built from the series check's parse."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.document import Document
from app.schemas.document import invoice_series_prefix, parse_document_number
from app.services.efatura import at_invoice_identity, import_purchases, normalise_invoice_number
from tests import (
    test_gil160_series_separators,
    test_migration_013_identity,
    test_pr32_v7,
    test_pr32_v8,
    test_pr32_v9,
    test_pr32_v10,
    test_pr32_v11,
)
from tests.test_efatura_import import TAXPAYER
from tests.test_gil160_linked_delete import _counted_vat, _purchase, _scan, _user, _visible


def _parametrized_numbers(function) -> list[str]:
    numbers = []
    for mark in getattr(function, "pytestmark", []):
        if mark.name != "parametrize":
            continue
        for case in mark.args[1]:
            value = case[0] if isinstance(case, tuple) else case
            if isinstance(value, str):
                numbers.append(value)
    return numbers


def _corpus() -> list[str]:
    numbers: list[str] = []
    for module in (
        test_pr32_v7,
        test_pr32_v8,
        test_pr32_v9,
        test_pr32_v10,
        test_pr32_v11,
        test_gil160_series_separators,
    ):
        for name in dir(module):
            if name.startswith("test_"):
                numbers += _parametrized_numbers(getattr(module, name))
    numbers += [number for _nif, _kind, number in test_migration_013_identity._CORPUS if number]
    numbers += ["FTA/5", "ftA/5", "FSA/7", "FRB/3", "FTX/1", "FTFT/1", "FTA/12", "FT A/12"]
    numbers += ["FTA 2026/5", "FT A 2026/5", "FSA 2026/7", "FS A 2026/7", "FRB 2026/3", "FR B 2026/3"]
    return sorted(set(numbers))


CORPUS = _corpus()


def _identity_parts(number: str) -> tuple:
    identity = normalise_invoice_number(number)
    head, _, tail = identity.partition(" ")
    parsed = parse_document_number(number)
    if parsed.code is None:
        series, _, seq = identity.rpartition("/") if parsed.seq is not None else (identity, "", None)
        return None, series, seq or None
    assert head == parsed.code.lower(), number
    if parsed.seq is None:
        return parsed.code, tail, None
    series, _, seq = tail.rpartition("/")
    return parsed.code, series, seq


def test_corpus_covers_the_separator_and_identity_cases():
    assert len(CORPUS) > 100


@pytest.mark.parametrize("number", CORPUS)
def test_identity_parts_equal_the_series_check_parse(number):
    parsed = parse_document_number(number)
    assert _identity_parts(number) == (parsed.code, parsed.series, parsed.seq)
    series_code = invoice_series_prefix(number)
    if series_code is not None:
        assert parsed.code == series_code
        assert parsed.is_series


def test_strings_that_share_an_identity_share_code_and_sequence():
    by_identity: dict[str, set] = {}
    for number in CORPUS:
        parsed = parse_document_number(number)
        by_identity.setdefault(normalise_invoice_number(number), set()).add((parsed.code, parsed.seq))
    clashes = {identity: parts for identity, parts in by_identity.items() if len(parts) > 1}
    assert clashes == {}
    assert len(by_identity) > 50


@pytest.mark.parametrize(
    ("scan_type", "scan_number", "at_number"),
    [
        ("FT", "FTA/5", "FT A/5"),
        ("FT", "ftA/5", "FT A/5"),
        ("FS", "FSA/7", "FS A/7"),
        ("FR", "FRB/3", "FR B/3"),
        ("FT", "FTX/1", "FT X/1"),
        ("FT", "FTFT/1", "FT FT/1"),
    ],
)
def test_glued_series_letter_links_to_its_at_invoice(db: Session, scan_type, scan_number, at_number):
    user, _headers = _user(db)
    scan = _scan(db, user)
    scan.vendor_nif = "296123456"
    scan.document_type = scan_type
    scan.invoice_number = scan_number
    scan.net_amount = Decimal("10.00")
    scan.vat_amount = Decimal("2.30")
    scan.gross_amount = Decimal("12.30")
    db.commit()
    invoice = replace(_purchase(at_number), document_type=scan_type)
    result = import_purchases(db, user_id=user.id, taxpayer_nif=TAXPAYER, invoices=[invoice])
    db.commit()
    assert result.linked_existing == (scan.id,)
    assert result.created == ()
    assert [row.id for row in _visible(db, user)] == [scan.id]
    assert _counted_vat(db, user) == [Decimal("2.30")]


def test_deleted_spaced_series_stays_deleted_when_the_glued_form_arrives(
    client: TestClient, db: Session
):
    user, headers = _user(db)
    created = import_purchases(
        db, user_id=user.id, taxpayer_nif=TAXPAYER, invoices=[_purchase("FT A/5")]
    )
    db.commit()
    at_id = created.created[0]
    assert client.delete(f"/api/documents/{at_id}", headers=headers).status_code == 204
    db.expire_all()

    glued = replace(_purchase("FTA/5"), atcud="GLUED-A5")
    again = import_purchases(db, user_id=user.id, taxpayer_nif=TAXPAYER, invoices=[glued])
    db.commit()
    assert again.created == ()
    assert again.linked_existing == ()
    assert _visible(db, user) == []
    assert _counted_vat(db, user) == []


def test_glued_row_with_a_012_identity_does_not_split_on_the_next_pull(db: Session):
    user, _headers = _user(db)
    created = import_purchases(
        db, user_id=user.id, taxpayer_nif=TAXPAYER, invoices=[_purchase("FTA/12")]
    )
    db.commit()
    row = db.get(Document, created.created[0])
    merged_by_012 = "296123456|FT|ft a/12"
    assert row.at_invoice_identity == merged_by_012
    assert at_invoice_identity("296123456", "FT", "FT A/12") == merged_by_012

    spaced = replace(_purchase("FT A/12"), atcud="SPACED-A12")
    again = import_purchases(db, user_id=user.id, taxpayer_nif=TAXPAYER, invoices=[spaced])
    db.commit()
    assert again.created == ()
    assert [document.id for document in _visible(db, user)] == [row.id]
    assert _counted_vat(db, user) == [Decimal("2.30")]

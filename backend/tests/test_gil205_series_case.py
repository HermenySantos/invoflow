"""GIL-205. The series keeps its letter case, and ambiguous scans are not auto-linked."""

from __future__ import annotations

import random
from dataclasses import replace
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.models.efatura import EfaturaLink
from app.services.efatura import at_invoice_identity, import_purchases, review_receipt_id
from tests.test_efatura_import import TAXPAYER
from tests.test_gil160_linked_delete import _counted_vat, _purchase, _scan, _user, _visible
from tests.test_migration_013_identity import _frozen as _identity_013

NIF = "296123456"


def _pull(db: Session, user, *invoices):
    result = import_purchases(db, user_id=user.id, taxpayer_nif=TAXPAYER, invoices=list(invoices))
    db.commit()
    return result


def _at(number: str, atcud: str, *, kind: str = "FT", vat: str = "2.30"):
    return replace(_purchase(number, vat=vat), atcud=atcud, document_type=kind)


def _scan_numbered(db: Session, user, number: str, *, kind: str = "FT"):
    scan = _scan(db, user)
    scan.vendor_nif = NIF
    scan.document_type = kind
    scan.invoice_number = number
    scan.net_amount = Decimal("10.00")
    scan.vat_amount = Decimal("2.30")
    scan.gross_amount = Decimal("12.30")
    db.commit()
    return scan


# U-1: identity


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("FT A/5", "FT a/5"),
        ("FTA/5", "FTa/5"),
        ("FT AB/5", "FT Ab/5"),
        ("FT A 2026/5", "FT a 2026/5"),
        ("FTA 2026/5", "fta 2026/5"),
        ("FT -A/5", "FT A/5"),
        ("FT _A/5", "FT A/5"),
        ("FT .A/5", "FT A/5"),
    ],
)
def test_series_that_differ_in_case_or_a_leading_mark_are_different_invoices(left, right):
    assert at_invoice_identity(NIF, "FT", left) != at_invoice_identity(NIF, "FT", right)


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("FT A/5", "ft A/5"),
        ("FT A/5", "Ft A/5"),
        ("FTA/5", "FT A/5"),
        ("ftA/5", "FT A/5"),
        ("FTA 2026/5", "FT A 2026/5"),
        ("FT A/005", "FT A/5"),
        ("FT  A / 5", "FT A/5"),
        ("FT\u00a0A/5", "FT A/5"),
        ("FT-A/5", "FT A/5"),
        ("FT - A/5", "FT A/5"),
    ],
)
def test_type_code_case_glued_letter_zeros_and_spacing_still_match(left, right):
    assert at_invoice_identity(NIF, "FT", left) == at_invoice_identity(NIF, "FT", right)


def test_two_at_invoices_that_differ_only_in_series_case_stay_two_rows(db: Session):
    user, _headers = _user(db)
    first = _pull(db, user, _at("FT A/5", "CASE-UPPER"))
    second = _pull(db, user, _at("FT a/5", "CASE-LOWER"))
    assert len(first.created) == 1
    assert len(second.created) == 1
    assert second.linked_existing == ()
    assert sorted(row.invoice_number for row in _visible(db, user)) == ["FT A/5", "FT a/5"]
    assert _counted_vat(db, user) == [Decimal("2.30"), Decimal("2.30")]

    again = _pull(db, user, _at("FT A/5", "CASE-UPPER"), _at("FT a/5", "CASE-LOWER"))
    assert again.created == ()
    assert len(again.unchanged) == 2
    assert len(_visible(db, user)) == 2


def test_series_case_pair_in_one_pull_stays_two_rows(db: Session):
    user, _headers = _user(db)
    result = _pull(db, user, _at("FT a/5", "ONE-LOWER"), _at("FT A/5", "ONE-UPPER"))
    assert len(result.created) == 2
    assert _counted_vat(db, user) == [Decimal("2.30"), Decimal("2.30")]


def test_series_case_pair_without_atcud_stays_two_rows(db: Session):
    user, _headers = _user(db)
    result = _pull(db, user, _purchase("FT A/5"), _purchase("FT a/5"))
    assert len(result.created) == 2
    assert len({row.at_invoice_identity for row in _visible(db, user)}) == 2
    keys = {link.source_key for link in db.query(EfaturaLink).filter(EfaturaLink.user_id == user.id)}
    assert keys == {f"doc:{NIF}:FT:ft a/5", f"doc:{NIF}:FT:FT a/5"}

    for order in ((_purchase("FT A/5"), _purchase("FT a/5")), (_purchase("FT a/5"), _purchase("FT A/5"))):
        again = _pull(db, user, *order)
        assert again.created == ()
        assert again.linked_existing == ()
        assert len(again.unchanged) == 2
    assert _counted_vat(db, user) == [Decimal("2.30"), Decimal("2.30")]


def test_leading_mark_series_is_not_merged_with_the_plain_series(db: Session):
    user, _headers = _user(db)
    result = _pull(db, user, _at("FT A/5", "PLAIN"), _at("FT -A/5", "MARKED"))
    assert len(result.created) == 2
    assert _counted_vat(db, user) == [Decimal("2.30"), Decimal("2.30")]


# U-1: scans


@pytest.mark.parametrize("scan_number", ["ft a/5", "FT a/5", "FTa/5", "FT -A/5"])
def test_scan_that_differs_only_in_case_or_mark_links_when_it_is_the_only_reading(
    db: Session, scan_number
):
    user, _headers = _user(db)
    scan = _scan_numbered(db, user, scan_number)
    result = _pull(db, user, _at("FT A/5", "ONLY-A"))
    assert result.linked_existing == (scan.id,)
    assert [row.id for row in _visible(db, user)] == [scan.id]


def test_lowercase_scan_with_both_case_series_known_links_only_its_exact_invoice(db: Session):
    user, _headers = _user(db)
    scan = _scan_numbered(db, user, "FT a/5")
    result = _pull(db, user, _at("FT A/5", "BOTH-UPPER"), _at("FT a/5", "BOTH-LOWER"))
    assert result.linked_existing == (scan.id,)
    assert len(result.created) == 1
    assert any(scan.id in warning and "Review both" in warning for warning in result.warnings)
    scan_links = db.query(EfaturaLink).filter(EfaturaLink.document_id == scan.id).all()
    assert [link.source_key for link in scan_links] == ["atcud:BOTH-LOWER"]
    assert _counted_vat(db, user) == [Decimal("2.30"), Decimal("2.30")]


def test_lowercase_ocr_scan_is_held_for_review_when_both_case_series_are_known(db: Session):
    user, _headers = _user(db)
    scan = _scan_numbered(db, user, "ft a/5")
    result = _pull(db, user, _at("FT A/5", "OCR-UPPER"), _at("FT a/5", "OCR-LOWER"))
    assert result.linked_existing == ()
    assert len(result.created) == 2
    assert len([warning for warning in result.warnings if scan.id in warning]) == 2
    assert db.query(EfaturaLink).filter(EfaturaLink.document_id == scan.id).count() == 0


def test_loose_scan_link_moves_off_when_the_exact_invoice_arrives(db: Session):
    user, _headers = _user(db)
    scan = _scan_numbered(db, user, "FT A/5")
    first = _pull(db, user, _at("FT a/5", "LOOSE-LOWER", vat="4.60"))
    assert first.linked_existing == (scan.id,)

    second = _pull(db, user, _at("FT A/5", "EXACT-UPPER"))
    assert second.linked_existing == (scan.id,)
    scan_links = db.query(EfaturaLink).filter(EfaturaLink.document_id == scan.id).all()
    assert [link.source_key for link in scan_links] == ["atcud:EXACT-UPPER"]
    moved = db.query(EfaturaLink).filter(EfaturaLink.source_key == "atcud:LOOSE-LOWER").one()
    lower = next(row for row in _visible(db, user) if row.id == moved.document_id)
    assert (lower.invoice_number, lower.status) == ("FT a/5", "needs_review")
    assert review_receipt_id(moved.warning) == scan.id
    assert sorted(_counted_vat(db, user)) == [Decimal("2.30"), Decimal("4.60")]

    again = _pull(db, user, _at("FT a/5", "LOOSE-LOWER", vat="4.60"), _at("FT A/5", "EXACT-UPPER"))
    assert again.created == ()
    assert len(_visible(db, user)) == 2


def test_scan_linked_to_one_type_is_not_linked_again_to_the_other_type(db: Session):
    user, _headers = _user(db)
    scan = _scan_numbered(db, user, "A/5")
    first = _pull(db, user, _at("A/5", "TYPE-FT"))
    assert first.linked_existing == (scan.id,)
    second = _pull(db, user, _at("A/5", "TYPE-FS", kind="FS", vat="4.60"))
    assert second.linked_existing == ()
    assert sorted(_counted_vat(db, user)) == [Decimal("2.30"), Decimal("4.60")]


def test_scan_linked_to_one_series_is_not_linked_again_to_the_other_case(db: Session):
    user, _headers = _user(db)
    scan = _scan_numbered(db, user, "FT A/5")
    first = _pull(db, user, _at("FT A/5", "LATER-UPPER"))
    assert first.linked_existing == (scan.id,)
    second = _pull(db, user, _at("FT a/5", "LATER-LOWER"))
    assert second.linked_existing == ()
    assert len(second.created) == 1
    assert any(scan.id in warning for warning in second.warnings)
    assert _counted_vat(db, user) == [Decimal("2.30"), Decimal("2.30")]


# U-7: a scan that lost the space after a vendor code


def test_glued_scan_is_not_auto_linked_when_two_invoices_read_the_same(db: Session):
    user, _headers = _user(db)
    scan = _scan_numbered(db, user, "FRA2026/12", kind="FR")
    result = _pull(
        db,
        user,
        _at("FR A2026/12", "PLAIN-CODE", kind="FR"),
        _at("FRA 2026/12", "VENDOR-CODE", kind="FR"),
    )
    assert result.linked_existing == ()
    assert len(result.created) == 2
    assert any(scan.id in warning for warning in result.warnings)
    assert db.query(EfaturaLink).filter(EfaturaLink.document_id == scan.id).count() == 0


def test_glued_scan_links_when_it_has_one_reading(db: Session):
    user, _headers = _user(db)
    scan = _scan_numbered(db, user, "FRA2026/12", kind="FR")
    result = _pull(db, user, _at("FR A2026/12", "SOLE", kind="FR"))
    assert result.linked_existing == (scan.id,)


def test_glued_scan_linked_earlier_flags_the_other_reading_when_it_arrives(db: Session):
    user, _headers = _user(db)
    scan = _scan_numbered(db, user, "FRA2026/12", kind="FR")
    first = _pull(db, user, _at("FR A2026/12", "EARLY", kind="FR"))
    assert first.linked_existing == (scan.id,)
    second = _pull(db, user, _at("FRA 2026/12", "LATE", kind="FR"))
    assert len(second.created) == 1
    assert any(scan.id in warning and "Review both" in warning for warning in second.warnings)


@pytest.mark.parametrize(
    ("scan_number", "at_number"),
    [("FTA/5", "FT A/5"), ("FTA 2026/5", "FT A 2026/5"), ("FTFT/1", "FT FT/1"), ("FT2026/12", "FT 2026/12")],
)
def test_glued_scans_from_main_still_link(db: Session, scan_number, at_number):
    user, _headers = _user(db)
    scan = _scan_numbered(db, user, scan_number)
    result = _pull(db, user, _at(at_number, "MAIN"))
    assert result.linked_existing == (scan.id,)
    assert _counted_vat(db, user) == [Decimal("2.30")]


def test_one_glued_letter_still_links_when_the_vendor_has_a_longer_code(db: Session):
    user, _headers = _user(db)
    scan = _scan_numbered(db, user, "FTA/5")
    result = _pull(db, user, _at("FT A/5", "SHORT"), _at("FTA X/5", "LONG"))
    assert result.linked_existing == (scan.id,)


# U-5: no false merge, against an independent canonical invoice

_CODES = ("FT", "FS", "FR", "NC", "ND")
_SERIES_CHARS = "ABCLOSXZabclosxz0123456789"


def _canonical_invoices(rng: random.Random, count: int) -> set[tuple[str, str, int]]:
    """(code, series, sequence) per AT's shape: no space in the series.

    Each base series also brings its case-flipped, zero-led and
    space-split neighbours, which are different invoices.
    """
    invoices: set[tuple[str, str, int]] = set()
    while len(invoices) < count:
        code = rng.choice(_CODES)
        series = "".join(rng.choice(_SERIES_CHARS) for _ in range(rng.randint(1, 5)))
        seq = rng.randint(1, 999)
        invoices.add((code, series, seq))
        invoices.add((code, series.swapcase(), seq))
        invoices.add((code, f"0{series}", seq))
        invoices.add((code, series, seq + 1))
        invoices.add((rng.choice(_CODES), series, seq))
    return invoices


def _renders(code: str, series: str, seq: int) -> list[str]:
    """How one invoice can be written, by AT or on a scan."""
    out = [
        f"{code} {series}/{seq}",
        f"{code.lower()} {series}/{seq}",
        f"{code.title()} {series}/{seq}",
        f"{code}  {series} / {seq}",
        f"{code}\u00a0{series}/{seq}",
        f" {code} {series}/{seq:06d} ",
        f"{code} {series}/{seq:03d}",
        f"{code}-{series}/{seq}",
    ]
    if series[0].isalpha() and len(series) == 1:
        out.append(f"{code}{series}/{seq}")
    return out


def _false_merges(identity, invoices) -> dict[str, set]:
    seen: dict[str, set] = {}
    for invoice in invoices:
        for number in _renders(*invoice):
            seen.setdefault(identity(NIF, invoice[0], number), set()).add(invoice)
    return {key: owners for key, owners in seen.items() if len(owners) > 1}


def test_equal_identity_implies_the_same_canonical_invoice():
    invoices = _canonical_invoices(random.Random(20501), 3000)
    assert _false_merges(at_invoice_identity, invoices) == {}


def test_every_render_of_one_invoice_shares_one_identity():
    for invoice in _canonical_invoices(random.Random(20502), 500):
        identities = {at_invoice_identity(NIF, invoice[0], number) for number in _renders(*invoice)}
        assert len(identities) == 1, (invoice, identities)


def test_the_no_false_merge_check_catches_the_casefolded_identity():
    invoices = _canonical_invoices(random.Random(20501), 3000)
    merges = _false_merges(_identity_013(), invoices)
    assert merges
    for owners in merges.values():
        assert len({(code, series.casefold(), seq) for code, series, seq in owners}) == 1


def test_glued_scans_are_never_auto_linked_to_the_other_reading(db: Session):
    """A scan that dropped the space after a vendor code ('FRA 2026/12' as
    'FRA2026/12') shares its identity with 'FR A2026/12'. The identity
    cannot tell them apart, so the importer must not link it when both are known."""
    rng = random.Random(20503)
    user, _headers = _user(db)
    for index in range(25):
        code = rng.choice(("FT", "FS", "FR"))
        extra = rng.choice("ABCLMSX")
        series = "".join(rng.choice("0123456789ABL") for _ in range(rng.randint(1, 4)))
        seq = rng.randint(1, 999)
        nif = f"5{index:08d}"
        scan = _scan_numbered(db, user, f"{code}{extra}{series}/{seq}", kind=code)
        scan.vendor_nif = nif
        db.commit()
        plain = replace(_at(f"{code} {extra}{series}/{seq}", f"P{index}", kind=code), issuer_nif=nif)
        vendor = replace(_at(f"{code}{extra} {series}/{seq}", f"V{index}", kind=code), issuer_nif=nif)
        result = _pull(db, user, *rng.sample([plain, vendor], 2))
        assert result.linked_existing == (), (scan.invoice_number, result)
        assert len(result.created) == 2


# U-B: a row held for review names the receipt it relates to


def test_held_row_names_its_receipt_in_the_list_until_it_is_confirmed(client, db: Session):
    user, headers = _user(db)
    scan = _scan_numbered(db, user, "ft a/5")
    scan.vendor_name = "Loja do Bairro"
    db.commit()
    _pull(db, user, _at("FT A/5", "LIST-UPPER"), _at("FT a/5", "LIST-LOWER"))

    listed = client.get("/api/documents", headers=headers)
    assert listed.status_code == 200, listed.text
    reviews = {row["invoice_number"]: row["efatura_review"] for row in listed.json()["documents"]}
    expected = {
        "related_document_id": scan.id,
        "related_invoice_number": "ft a/5",
        "related_vendor_name": "Loja do Bairro",
    }
    assert reviews == {"ft a/5": None, "FT A/5": expected, "FT a/5": expected}

    held = next(row for row in _visible(db, user) if row.invoice_number == "FT A/5")
    held.status = "ready"
    db.commit()
    listed = client.get("/api/documents", headers=headers)
    reviews = {row["invoice_number"]: row["efatura_review"] for row in listed.json()["documents"]}
    assert reviews["FT A/5"] is None
    assert reviews["FT a/5"] == expected


def test_held_row_does_not_name_a_deleted_receipt(client, db: Session):
    user, headers = _user(db)
    scan = _scan_numbered(db, user, "ft a/5")
    _pull(db, user, _at("FT A/5", "GONE-UPPER"), _at("FT a/5", "GONE-LOWER"))
    assert client.delete(f"/api/documents/{scan.id}", headers=headers).status_code == 204
    listed = client.get("/api/documents", headers=headers).json()["documents"]
    assert len(listed) == 2
    assert [row["efatura_review"] for row in listed] == [None, None]

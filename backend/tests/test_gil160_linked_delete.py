"""GIL-160. Deleting a linked scan must not drop the e-Fatura invoice."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.audit_log import AuditLog
from app.models.document import Document
from app.models.efatura import EfaturaLink
from app.models.user import User
from app.services.categorization import deductible_vat_split
from app.services import efatura as efatura_service
from app.services.efatura import EFaturaInvoice, VatLine, at_invoice_identity, import_purchases
from app.services.iva_adjust import contributions
from tests.test_efatura_import import TAXPAYER, _fixture


def _continente():
    return next(invoice for invoice in _fixture() if invoice.invoice_number == "FT A/123")


def _user(db: Session) -> tuple[User, dict]:
    clerk_id = f"test-user-{uuid.uuid4().hex[:8]}"
    user = User(clerk_id=clerk_id, email="gil160@example.com")
    db.add(user)
    db.commit()
    return user, {"X-Mock-User-Id": clerk_id}


def _scan(db: Session, user: User) -> Document:
    document = Document(
        user_id=user.id,
        status="ready",
        storage_key=f"{user.clerk_id}/scan.jpg",
        original_filename="scan.jpg",
        mime_type="image/jpeg",
        vendor_name="Continente",
        vendor_nif="500100144",
        invoice_number="FT A/123",
        document_type="FT",
        document_date=date(2026, 1, 20),
        net_amount=Decimal("8.00"),
        vat_amount=Decimal("1.84"),
        gross_amount=Decimal("9.84"),
        expense_category="food",
        ocr_raw_response=json.dumps({"text": "scanned receipt"}),
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


def _visible(db: Session, user: User) -> list[Document]:
    return (
        db.query(Document)
        .filter(Document.user_id == user.id, Document.deleted_at.is_(None))
        .all()
    )


def _counted_vat(db: Session, user: User) -> list[Decimal]:
    return [row.vat for row in contributions(_visible(db, user))]


def test_delete_linked_scan_keeps_the_at_invoice_once(client: TestClient, db: Session):
    user, headers = _user(db)
    scan = _scan(db, user)
    invoice = _continente()
    linked = import_purchases(db, user_id=user.id, taxpayer_nif=TAXPAYER, invoices=[invoice])
    db.commit()
    assert linked.linked_existing == (scan.id,)
    assert _counted_vat(db, user) == [Decimal("1.84")]

    deleted = client.delete(f"/api/documents/{scan.id}", headers=headers)
    assert deleted.status_code == 204, deleted.text
    db.expire_all()

    scan = db.get(Document, scan.id)
    assert scan.deleted_at is not None
    visible = _visible(db, user)
    assert len(visible) == 1
    at_row = visible[0]
    assert at_row.id != scan.id
    assert at_row.mime_type == "application/vnd.invoflow.efatura+json"
    assert at_row.document_type == "FT"
    assert at_row.invoice_number == "FT A/123"
    assert at_row.vat_amount == Decimal("2.30")
    assert at_row.gross_amount == Decimal("12.30")
    assert json.loads(at_row.ocr_raw_response) == {"source": "efatura"}
    assert _counted_vat(db, user) == [Decimal("2.30")]

    link = db.query(EfaturaLink).filter(EfaturaLink.user_id == user.id).one()
    assert link.document_id == at_row.id
    assert link.outcome == "created"
    audit = (
        db.query(AuditLog)
        .filter(AuditLog.entity_id == scan.id, AuditLog.action == "efatura_unlink")
        .one()
    )
    assert audit.source == "user"
    assert audit.user_id == user.id
    changes = json.loads(audit.changes_json)
    assert changes["efatura_document_id"] == {"old": scan.id, "new": at_row.id}
    assert changes["source_key"]["new"] == link.source_key

    again = import_purchases(db, user_id=user.id, taxpayer_nif=TAXPAYER, invoices=[invoice])
    db.commit()
    db.expire_all()
    assert again.created == ()
    assert again.unchanged == (link.source_key,)
    assert [row.id for row in _visible(db, user)] == [at_row.id]
    assert _counted_vat(db, user) == [Decimal("2.30")]
    assert db.query(Document).filter(Document.user_id == user.id).count() == 2


def test_reimport_restores_an_orphaned_link_once(db: Session):
    user, _headers = _user(db)
    scan = _scan(db, user)
    invoice = _continente()
    import_purchases(db, user_id=user.id, taxpayer_nif=TAXPAYER, invoices=[invoice])
    db.commit()
    scan.deleted_at = datetime.utcnow()
    db.commit()
    assert _counted_vat(db, user) == []

    restored = import_purchases(db, user_id=user.id, taxpayer_nif=TAXPAYER, invoices=[invoice])
    db.commit()
    visible = _visible(db, user)
    assert len(restored.created) == 1
    assert visible[0].id == restored.created[0]
    assert visible[0].vat_amount == Decimal("2.30")
    assert _counted_vat(db, user) == [Decimal("2.30")]
    assert (
        db.query(AuditLog)
        .filter(AuditLog.entity_id == scan.id, AuditLog.action == "efatura_unlink")
        .count()
        == 1
    )

    second = import_purchases(db, user_id=user.id, taxpayer_nif=TAXPAYER, invoices=[invoice])
    db.commit()
    assert second.created == ()
    assert second.unchanged
    assert [row.id for row in _visible(db, user)] == [visible[0].id]
    assert db.query(Document).filter(Document.user_id == user.id).count() == 2


def test_delete_unlinked_scan_does_not_invent_an_at_row(client: TestClient, db: Session):
    user, headers = _user(db)
    scan = _scan(db, user)
    assert _counted_vat(db, user) == [Decimal("1.84")]

    deleted = client.delete(f"/api/documents/{scan.id}", headers=headers)
    assert deleted.status_code == 204, deleted.text
    db.expire_all()

    assert db.get(Document, scan.id).deleted_at is not None
    assert _visible(db, user) == []
    assert _counted_vat(db, user) == []
    assert db.query(EfaturaLink).count() == 0
    assert (
        db.query(AuditLog)
        .filter(AuditLog.entity_id == scan.id, AuditLog.action == "efatura_unlink")
        .count()
        == 0
    )
    assert (
        db.query(AuditLog)
        .filter(AuditLog.entity_id == scan.id, AuditLog.action == "delete")
        .count()
        == 1
    )


def test_two_links_for_one_invoice_restore_one_row(client: TestClient, db: Session):
    user, headers = _user(db)
    scan = _scan(db, user)
    invoice = _continente()
    with_atcud = replace(invoice, atcud="X-1")
    import_purchases(db, user_id=user.id, taxpayer_nif=TAXPAYER, invoices=[invoice, with_atcud])
    db.commit()
    assert db.query(EfaturaLink).filter(EfaturaLink.document_id == scan.id).count() == 2

    deleted = client.delete(f"/api/documents/{scan.id}", headers=headers)
    assert deleted.status_code == 204, deleted.text
    db.expire_all()

    visible = _visible(db, user)
    assert len(visible) == 1
    assert visible[0].vat_amount == Decimal("2.30")
    assert _counted_vat(db, user) == [Decimal("2.30")]
    targets = {link.document_id for link in db.query(EfaturaLink).filter(EfaturaLink.user_id == user.id)}
    assert targets == {visible[0].id}
    assert (
        db.query(AuditLog)
        .filter(AuditLog.entity_id == scan.id, AuditLog.action == "efatura_unlink")
        .count()
        == 1
    )


def test_reimport_of_two_links_does_not_double_the_invoice(db: Session):
    user, _headers = _user(db)
    scan = _scan(db, user)
    invoice = _continente()
    with_atcud = replace(invoice, atcud="X-1")
    import_purchases(db, user_id=user.id, taxpayer_nif=TAXPAYER, invoices=[invoice, with_atcud])
    db.commit()
    scan.deleted_at = datetime.utcnow()
    db.commit()

    restored = import_purchases(
        db, user_id=user.id, taxpayer_nif=TAXPAYER, invoices=[invoice, with_atcud]
    )
    db.commit()
    assert len(restored.created) == 1
    visible = _visible(db, user)
    assert [row.id for row in visible] == [restored.created[0]]
    assert _counted_vat(db, user) == [Decimal("2.30")]
    targets = {link.document_id for link in db.query(EfaturaLink).filter(EfaturaLink.user_id == user.id)}
    assert targets == {visible[0].id}
    assert (
        db.query(AuditLog)
        .filter(AuditLog.entity_id == scan.id, AuditLog.action == "efatura_unlink")
        .count()
        == 1
    )


def test_deleted_at_row_stays_deleted_across_three_pulls(client: TestClient, db: Session):
    user, headers = _user(db)
    invoice = _continente()
    created = import_purchases(db, user_id=user.id, taxpayer_nif=TAXPAYER, invoices=[invoice])
    db.commit()
    at_id = created.created[0]
    assert db.query(Document).filter(Document.user_id == user.id).count() == 1

    for cycle in range(3):
        status = client.delete(f"/api/documents/{at_id}", headers=headers)
        assert status.status_code == (204 if cycle == 0 else 404), (cycle, status.status_code, status.text)
        again = import_purchases(db, user_id=user.id, taxpayer_nif=TAXPAYER, invoices=[invoice])
        db.commit()
        db.expire_all()
        assert again.created == ()
        assert again.unchanged
        assert _visible(db, user) == []
        assert _counted_vat(db, user) == []
        rows = db.query(Document).filter(Document.user_id == user.id).all()
        assert [row.id for row in rows] == [at_id]
        assert rows[0].deleted_at is not None
        assert (
            db.query(AuditLog)
            .filter(AuditLog.entity_id == at_id, AuditLog.action == "efatura_unlink")
            .count()
            == 0
        )


def test_restored_row_keeps_a_confirmed_office_review(client: TestClient, db: Session):
    user, headers = _user(db)
    scan = _scan(db, user)
    scan.expense_category = "office"
    scan.irs_sector = "geral"
    scan.deductible_pct_override = None
    scan.status = "ready"
    db.commit()
    import_purchases(db, user_id=user.id, taxpayer_nif=TAXPAYER, invoices=[_continente()])
    db.commit()

    assert client.delete(f"/api/documents/{scan.id}", headers=headers).status_code == 204
    db.expire_all()
    at_row = _visible(db, user)[0]
    assert at_row.status == "ready"
    assert at_row.expense_category == "office"
    assert at_row.irs_sector == "geral"
    confirmed, pending = deductible_vat_split([at_row])
    assert confirmed == Decimal("2.30")
    assert pending == Decimal("0.00")


def test_unreadable_link_payload_is_logged_and_skipped(db: Session, caplog):
    user, _headers = _user(db)
    scan = _scan(db, user)
    link = EfaturaLink(
        id=str(uuid.uuid4()),
        user_id=user.id,
        source_key="atcud:BAD",
        role="acquirer",
        outcome="linked_existing",
        document_id=scan.id,
        fiscal_status="normal",
        warning=None,
        payload_json="{",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(link)
    scan.deleted_at = datetime.utcnow()
    db.commit()

    from app.services.efatura import detach_deleted_scan

    with caplog.at_level(logging.WARNING):
        detach_deleted_scan(db, scan)
    db.commit()
    assert scan.id in caplog.text or link.id in caplog.text
    assert "not readable" in caplog.text
    assert _visible(db, user) == []
    assert db.get(EfaturaLink, link.id).document_id == scan.id


def test_cancelled_link_is_logged_as_cancelled(db: Session, caplog):
    user, _headers = _user(db)
    scan = _scan(db, user)
    invoice = _continente()
    import_purchases(db, user_id=user.id, taxpayer_nif=TAXPAYER, invoices=[invoice])
    db.commit()
    link = db.query(EfaturaLink).filter(EfaturaLink.document_id == scan.id).one()
    payload = json.loads(link.payload_json)
    payload["fiscal_status"] = "cancelled"
    link.payload_json = json.dumps(payload)
    scan.deleted_at = datetime.utcnow()
    db.commit()

    from app.services.efatura import detach_deleted_scan

    with caplog.at_level(logging.WARNING):
        detach_deleted_scan(db, scan)
    assert "invoice is cancelled" in caplog.text
    assert "not readable" not in caplog.text
    assert _visible(db, user) == []


def test_unconfirmed_scan_restores_without_a_category(client: TestClient, db: Session):
    user, headers = _user(db)
    scan = _scan(db, user)
    scan.status = "needs_review"
    scan.expense_category = "food"
    db.commit()
    import_purchases(db, user_id=user.id, taxpayer_nif=TAXPAYER, invoices=[_continente()])
    db.commit()
    assert client.delete(f"/api/documents/{scan.id}", headers=headers).status_code == 204
    db.expire_all()
    at_row = _visible(db, user)[0]
    assert at_row.status == "needs_review"
    assert at_row.expense_category is None
    assert at_row.irs_sector is None


def test_editing_an_at_row_recomputes_its_identity(client: TestClient, db: Session):
    user, headers = _user(db)
    created = import_purchases(db, user_id=user.id, taxpayer_nif=TAXPAYER, invoices=[_continente()])
    db.commit()
    at_id = created.created[0]
    before = at_invoice_identity("500100144", "FT", "FT A/123")
    assert db.get(Document, at_id).at_invoice_identity == before

    updated = client.patch(
        f"/api/documents/{at_id}",
        headers=headers,
        json={"invoice_number": "FT A/124"},
    )
    assert updated.status_code == 200, updated.text
    db.expire_all()
    assert db.get(Document, at_id).at_invoice_identity == at_invoice_identity(
        "500100144", "FT", "FT A/124"
    )


def test_identity_ignores_spacing_prefix_and_leading_zeros():
    spaced = at_invoice_identity("PT 500100144", "FT", "FT  2026/012")
    plain = at_invoice_identity("500100144", "ft", "FT\u00a02026/12")
    assert spaced == plain
    assert spaced == "500100144|FT|ft 2026/12"
    assert at_invoice_identity("PT296123456", "FT", "FT A/1") == at_invoice_identity(
        "296123456", "FT", "FT A/1"
    )
    assert at_invoice_identity("PTX1", "FT", "FT A/1") != at_invoice_identity(
        "X1", "FT", "FT A/1"
    )


def test_identity_keeps_series_digits_and_inner_spaces():
    nif = "296123456"
    assert at_invoice_identity(nif, "FT", "FT A01/5") != at_invoice_identity(nif, "FT", "FT A1/5")
    assert at_invoice_identity(nif, "FT", "FT 007/1") != at_invoice_identity(nif, "FT", "FT 7/1")
    assert at_invoice_identity(nif, "FT", "FT 2026A01/5") != at_invoice_identity(
        nif, "FT", "FT 2026A1/5"
    )
    assert at_invoice_identity(nif, "FT", "FT 1 23/4") != at_invoice_identity(
        nif, "FT", "FT 12 3/4"
    )
    assert at_invoice_identity(nif, "FT", "FT A1/005") == at_invoice_identity(nif, "FT", "FT A1/5")
    assert at_invoice_identity(nif, "FT", "FT  1   23/4") == at_invoice_identity(
        nif, "FT", "FT 1 23/4"
    )
    assert "ft a01/5" in at_invoice_identity(nif, "FT", "FT A01/5")
    assert at_invoice_identity(nif, "FT", "FT 1 23/4").endswith("|ft 1 23/4")


def _purchase(number: str, *, nif: str = "296123456", vat: str = "2.30") -> EFaturaInvoice:
    vat_amount = Decimal(vat)
    net = Decimal("10.00")
    return EFaturaInvoice(
        document_type="FT",
        invoice_number=number,
        issue_date=date(2026, 4, 1),
        issuer_nif=nif,
        acquirer_nif=TAXPAYER,
        acquirer_country="PT",
        fiscal_status="normal",
        lines=(VatLine("IVA", "PT", "NOR", Decimal("23.00"), net, vat_amount, None),),
        tax_payable=vat_amount,
        net_total=net,
        gross_total=net + vat_amount,
        issuer_name="Loja",
    )


_DISTINCT_PAIRS = (
    ("FT A01/5", "2.30", "FT A1/5", "4.60"),
    ("FT 007/1", "2.30", "FT 7/1", "4.60"),
    ("FT 2026A01/5", "2.30", "FT 2026A1/5", "4.60"),
    ("FT 1 23/4", "3.00", "FT 12 3/4", "1.00"),
)


def test_distinct_invoice_numbers_are_stored_not_linked(db: Session):
    user, _headers = _user(db)
    invoices = [
        _purchase(number, vat=vat)
        for left, left_vat, right, right_vat in _DISTINCT_PAIRS
        for number, vat in ((left, left_vat), (right, right_vat))
    ]
    result = import_purchases(db, user_id=user.id, taxpayer_nif=TAXPAYER, invoices=invoices)
    db.commit()
    assert result.linked_existing == ()
    assert len(result.created) == len(invoices)
    stored = {
        row.invoice_number: row.vat_amount
        for row in db.query(Document).filter(Document.user_id == user.id)
    }
    assert stored["FT A01/5"] == Decimal("2.30")
    assert stored["FT A1/5"] == Decimal("4.60")
    assert stored["FT 1 23/4"] == Decimal("3.00")
    assert stored["FT 12 3/4"] == Decimal("1.00")
    assert len(stored) == 8


def test_a_different_invoice_is_not_linked_to_a_scan_of_its_neighbour(db: Session):
    user, _headers = _user(db)
    scan = _scan(db, user)
    scan.vendor_nif = "296123456"
    scan.invoice_number = "FT A1/5"
    scan.vat_amount = Decimal("1.87")
    db.commit()
    result = import_purchases(
        db,
        user_id=user.id,
        taxpayer_nif=TAXPAYER,
        invoices=[_purchase("FT A01/5", vat="2.30"), _purchase("FT A1/5", vat="4.60")],
    )
    db.commit()
    assert result.linked_existing == (scan.id,)
    assert len(result.created) == 1
    created = db.get(Document, result.created[0])
    assert created.invoice_number == "FT A01/5"
    assert created.vat_amount == Decimal("2.30")
    links = {link.source_key: link.document_id for link in db.query(EfaturaLink)}
    assert links["doc:296123456:FT:ft a01/5"] == created.id
    assert links["doc:296123456:FT:ft a1/5"] == scan.id


def test_sequence_leading_zeros_and_a_pt_nif_are_the_same_invoice(db: Session):
    user, _headers = _user(db)
    first = import_purchases(
        db, user_id=user.id, taxpayer_nif=TAXPAYER, invoices=[_purchase("FT A1/5", nif="296123456")]
    )
    db.commit()
    second = import_purchases(
        db,
        user_id=user.id,
        taxpayer_nif=TAXPAYER,
        invoices=[_purchase("FT A1/005", nif="PT296123456")],
    )
    db.commit()
    assert second.linked_existing == (first.created[0],)
    assert second.created == ()
    assert db.query(Document).filter(Document.user_id == user.id).count() == 1


def test_import_does_not_commit_the_caller(db: Session):
    user, _headers = _user(db)
    user.email = "uncommitted@example.com"
    db.flush()
    import_purchases(
        db, user_id=user.id, taxpayer_nif=TAXPAYER, invoices=[_purchase("FT Z/1")]
    )
    db.rollback()
    db.expire_all()
    assert db.get(User, user.id).email == "gil160@example.com"
    assert db.query(Document).filter(Document.user_id == user.id).count() == 0
    assert db.query(EfaturaLink).filter(EfaturaLink.user_id == user.id).count() == 0


class _Deadlock(Exception):
    pgcode = "40P01"


def _deadlock() -> OperationalError:
    return OperationalError("INSERT", {}, _Deadlock("deadlock detected"))


def test_second_deadlock_is_skipped_and_later_invoices_continue(db: Session, caplog, monkeypatch):
    user, _headers = _user(db)
    real = efatura_service._import_one

    def wrapped(*args, **kwargs):
        invoice = kwargs.get("invoice")
        if invoice is not None and invoice.invoice_number == "FT 9/1":
            raise _deadlock()
        return real(*args, **kwargs)

    monkeypatch.setattr(efatura_service, "_import_one", wrapped)
    with caplog.at_level(logging.WARNING):
        result = import_purchases(
            db,
            user_id=user.id,
            taxpayer_nif=TAXPAYER,
            invoices=[_purchase("FT 9/0"), _purchase("FT 9/1"), _purchase("FT 9/2")],
        )
        db.commit()
    assert [item.outcome for item in result.skipped] == ["deadlock"]
    assert result.skipped[0].source_key == "doc:296123456:FT:ft 9/1"
    assert result.skipped[0].warning
    assert any("recorded as failed" in record.message for record in caplog.records)
    numbers = {
        row.invoice_number
        for row in db.query(Document).filter(Document.user_id == user.id, Document.deleted_at.is_(None))
    }
    assert numbers == {"FT 9/0", "FT 9/2"}


@pytest.fixture
def efatura_pull_on(monkeypatch):
    """Turn the pull route on, and drop the cached flag after the client closes."""
    monkeypatch.setenv("EFATURA_PULL_ENABLED", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_pull_reports_a_deadlocked_invoice_and_continues(
    efatura_pull_on, client: TestClient, db: Session, monkeypatch
):
    real = efatura_service._import_one

    def wrapped(*args, **kwargs):
        invoice = kwargs.get("invoice")
        if invoice is not None and invoice.invoice_number == "FT 9/1":
            raise _deadlock()
        return real(*args, **kwargs)

    monkeypatch.setattr(efatura_service, "_import_one", wrapped)

    class _Client:
        def fetch(self, _query):
            return (_purchase("FT 9/0"), _purchase("FT 9/1"), _purchase("FT 9/2"))

    monkeypatch.setattr("app.api.efatura.build_efatura_client", lambda _settings: _Client())
    response = client.post(
        "/api/efatura/pull",
        headers={"X-Mock-User-Id": f"pull-{uuid.uuid4().hex[:8]}", "X-Mock-User-Email": "pull@example.com"},
        json={"taxpayer_nif": TAXPAYER, "period_start": "2026-04-01", "period_end": "2026-04-30"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert [item["outcome"] for item in body["skipped"]] == ["deadlock"]
    assert "ft 9/1" in body["skipped"][0]["source_key"]
    assert body["warnings"]
    db.expire_all()
    numbers = {row.invoice_number for row in db.query(Document).filter(Document.deleted_at.is_(None))}
    assert numbers == {"FT 9/0", "FT 9/2"}


def test_import_pause_is_not_read_from_the_environment():
    source = Path("app/services/efatura.py").read_text(encoding="utf-8")
    assert "EFATURA_IMPORT_PAUSE_S" not in source
    assert "after_invoice" in source


def test_patch_identity_collision_is_409_and_a_deleted_row_does_not_block(
    client: TestClient, db: Session
):
    user, headers = _user(db)
    first = import_purchases(
        db, user_id=user.id, taxpayer_nif=TAXPAYER, invoices=[_purchase("FT 2026/50", nif="123456002")]
    )
    second = import_purchases(
        db, user_id=user.id, taxpayer_nif=TAXPAYER, invoices=[_purchase("FT 2026/51", nif="123456002")]
    )
    third = import_purchases(
        db, user_id=user.id, taxpayer_nif=TAXPAYER, invoices=[_purchase("FT 2026/52", nif="999999999")]
    )
    db.commit()
    kept_id, other_id, nif_id = first.created[0], second.created[0], third.created[0]

    collided = client.patch(
        f"/api/documents/{other_id}",
        headers=headers,
        json={"invoice_number": "FT 2026/050"},
    )
    assert collided.status_code == 409, collided.text
    assert "FT 2026/50" in collided.json()["detail"]
    db.expire_all()
    assert db.get(Document, other_id).invoice_number == "FT 2026/51"

    nif_hit = client.patch(
        f"/api/documents/{nif_id}",
        headers=headers,
        json={"vendor_nif": "PT 123456002", "invoice_number": "FT 2026/50"},
    )
    assert nif_hit.status_code == 409, nif_hit.text
    assert "FT 2026/50" in nif_hit.json()["detail"]

    deleted = client.delete(f"/api/documents/{kept_id}", headers=headers)
    assert deleted.status_code == 204, deleted.text
    moved = client.patch(
        f"/api/documents/{other_id}",
        headers=headers,
        json={"invoice_number": "FT 2026/50"},
    )
    assert moved.status_code == 200, moved.text
    db.expire_all()
    assert db.get(Document, other_id).invoice_number == "FT 2026/50"
    assert db.get(Document, kept_id).deleted_at is not None

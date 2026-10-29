"""GIL-160. Deleting a linked scan must not drop the e-Fatura invoice."""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.document import Document
from app.models.efatura import EfaturaLink
from app.models.user import User
from app.services.efatura import import_purchases
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

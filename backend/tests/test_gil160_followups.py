"""GIL-160 items 3 and 4. Clearing an accepted pair is audited. The list shows a linked AT pair."""

from __future__ import annotations

import asyncio
import json

from app.models.audit_log import AuditLog
from app.services import processing
from app.services.audit import log_series_mismatch_accepted
from app.services.efatura import import_purchases
from app.services.ocr import OCRResult, _apply_invoice_qr
from tests.conftest import TestingSessionLocal
from tests.test_pr32_v8 import _efatura, _qr
from tests.test_qa_gate_ocr import _stored_receipt


def _accepted_row(db, *, status="needs_review"):
    stored = _stored_receipt(
        db,
        status=status,
        document_type="FR",
        invoice_number="FT 2026/12",
        vendor_nif="500829993",
        series_mismatch_accepted=True,
        at_document_type=None,
        ocr_raw_response='{"ocr":"scan"}',
    )
    log_series_mismatch_accepted(
        db,
        document_id=stored.id,
        user_id=stored.user_id,
        document_type="FR",
        invoice_number="FT 2026/12",
        previous_accepted=False,
        previous_type=None,
        previous_number=None,
    )
    db.commit()
    return stored


def _cleared(db, document_id):
    return (
        db.query(AuditLog)
        .filter(AuditLog.entity_id == document_id, AuditLog.action == "series_mismatch_cleared")
        .all()
    )


def test_user_edit_that_clears_the_pair_writes_one_cleared_entry(client, db, mock_user_headers):
    stored = _accepted_row(db)
    response = client.patch(
        f"/api/documents/{stored.id}",
        headers=mock_user_headers,
        json={"document_type": "FT"},
    )
    assert response.status_code == 200, response.json()
    assert response.json()["series_mismatch_accepted"] is False
    entries = _cleared(db, stored.id)
    assert len(entries) == 1
    assert entries[0].source == "user"
    assert entries[0].user_id == stored.user_id
    changes = json.loads(entries[0].changes_json)
    assert changes["series_mismatch_accepted"] == {"old": True, "new": False}
    assert changes["document_type"]["new"] == "FT"
    assert changes["invoice_number"]["new"] == "FT 2026/12"
    assert changes["cleared_at"]["new"].endswith("Z")

    again = client.patch(
        f"/api/documents/{stored.id}",
        headers=mock_user_headers,
        json={"invoice_number": "FT 2026/13"},
    )
    assert again.status_code == 200, again.json()
    assert len(_cleared(db, stored.id)) == 1


def test_an_edit_that_keeps_the_pair_writes_no_cleared_entry(client, db, mock_user_headers):
    stored = _accepted_row(db)
    response = client.patch(
        f"/api/documents/{stored.id}",
        headers=mock_user_headers,
        json={"review_notes": "visto"},
    )
    assert response.status_code == 200, response.json()
    assert response.json()["series_mismatch_accepted"] is True
    assert _cleared(db, stored.id) == []


def test_efatura_link_that_clears_the_pair_writes_one_cleared_entry(db):
    stored = _accepted_row(db, status="ready")
    outcomes = []
    for _pull in range(2):
        imported = import_purchases(
            db,
            user_id=stored.user_id,
            taxpayer_nif="555555555",
            invoices=[_efatura("FT", "FT 2026/12", "GIL160CLR")],
        )
        db.commit()
        outcomes.append((imported.linked_existing, imported.unchanged))
    assert outcomes == [((stored.id,), ()), ((), ("atcud:GIL160CLR",))]
    db.refresh(stored)
    assert stored.series_mismatch_accepted is False
    entries = _cleared(db, stored.id)
    assert [entry.source for entry in entries] == ["efatura"]
    assert (
        db.query(AuditLog)
        .filter(AuditLog.entity_id == stored.id, AuditLog.action == "series_mismatch_accepted")
        .count()
        == 1
    )


def test_qr_read_that_clears_the_pair_writes_one_cleared_entry(db, monkeypatch):
    stored = _accepted_row(db, status="processing")

    class _Reader:
        backend = "tesseract"

        async def process_document(self, content, mime):
            return _apply_invoice_qr(
                OCRResult(vendor_name="Oficina do Bairro", backend="tesseract", confidence=90),
                _qr("FT", "FT A/1"),
            )

    monkeypatch.setattr(processing, "get_ocr_service", lambda: _Reader())
    monkeypatch.setattr(
        processing,
        "get_storage_service",
        lambda: type("S", (), {"get_file": lambda self, key: b"bytes"})(),
    )
    asyncio.run(processing.read_receipt(TestingSessionLocal, stored.id))
    db.expire_all()
    entries = _cleared(db, stored.id)
    assert [entry.source for entry in entries] == ["qr"]
    assert json.loads(entries[0].changes_json)["invoice_number"]["new"] == "FT A/1"


def test_linking_a_row_that_was_never_accepted_writes_no_cleared_entry(db):
    stored = _stored_receipt(
        db,
        status="ready",
        document_type="FT",
        invoice_number="FT 2026/14",
        vendor_nif="500829993",
        at_document_type=None,
        ocr_raw_response='{"ocr":"scan"}',
    )
    db.commit()
    imported = import_purchases(
        db,
        user_id=stored.user_id,
        taxpayer_nif="555555555",
        invoices=[_efatura("FT", "FT 2026/14", "GIL160NOCLR")],
    )
    db.commit()
    assert stored.id in imported.linked_existing
    assert _cleared(db, stored.id) == []

"""GIL-160 items 3 to 5. Clearing an accepted pair is audited, the list shows a linked AT pair, and the linked-row lock is documented."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.models.audit_log import AuditLog
from app.schemas.document import SERIES_MISMATCH_DETAIL
from app.services import processing
from app.services.audit import log_series_mismatch_accepted
from app.services.efatura import import_purchases
from app.services.ocr import OCRResult, _apply_invoice_qr
from tests.conftest import TestingSessionLocal
from tests.test_pr32_v8 import _efatura, _qr
from tests.test_qa_gate_ocr import _stored_receipt

_REPO = Path(__file__).resolve().parents[2]


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


def test_list_shows_the_linked_at_pair_only_on_linked_scans(client, db, mock_user_headers):
    linked = _stored_receipt(
        db,
        status="ready",
        document_type="FT",
        invoice_number="FT2026/15",
        vendor_nif="500829993",
        at_document_type=None,
        ocr_raw_response='{"ocr":"scan"}',
    )
    db.commit()
    imported = import_purchases(
        db,
        user_id=linked.user_id,
        taxpayer_nif="555555555",
        invoices=[
            _efatura("FT", "FT 2026/15", "GIL160LIST"),
            _efatura("FT", "FT 2026/16", "GIL160NEW"),
        ],
    )
    db.commit()
    assert imported.linked_existing == (linked.id,)
    assert len(imported.created) == 1

    listed = client.get("/api/documents", headers=mock_user_headers)
    assert listed.status_code == 200
    by_id = {row["id"]: row for row in listed.json()["documents"]}
    assert by_id[linked.id]["linked_at_pair"] == {
        "document_type": "FT",
        "invoice_number": "FT 2026/15",
    }
    assert by_id[imported.created[0]]["linked_at_pair"] is None

    detail = client.get(f"/api/documents/{linked.id}", headers=mock_user_headers)
    assert detail.json()["linked_at_pair"] == by_id[linked.id]["linked_at_pair"]


def _linked_scan(db, number="FT 2026/12"):
    stored = _stored_receipt(
        db,
        status="needs_review",
        document_type="FT",
        invoice_number=number,
        vendor_nif="500829993",
        at_document_type=None,
        ocr_raw_response='{"ocr":"scan"}',
    )
    db.commit()
    imported = import_purchases(
        db,
        user_id=stored.user_id,
        taxpayer_nif="555555555",
        invoices=[_efatura("FT", number, "GIL160LOCK")],
    )
    db.commit()
    assert imported.linked_existing == (stored.id,)
    return stored


def test_linked_row_retypes_match_the_documented_lock(client, db, mock_user_headers):
    stored = _linked_scan(db)
    refused = [
        {"document_type": "FS"},
        {"document_type": "FR", "accept_series_mismatch": True},
        {"document_type": "NC", "invoice_number": "2026/12"},
        {"document_type": "ND", "invoice_number": "ND 2026/12", "accept_series_mismatch": True},
    ]
    for body in refused:
        response = client.patch(f"/api/documents/{stored.id}", headers=mock_user_headers, json=body)
        assert response.status_code == 422, body
        assert response.json()["detail"] == SERIES_MISMATCH_DETAIL
    db.refresh(stored)
    assert (stored.document_type, stored.invoice_number) == ("FT", "FT 2026/12")

    gap = client.patch(
        f"/api/documents/{stored.id}",
        headers=mock_user_headers,
        json={"document_type": "FS", "invoice_number": "FS 2026/12"},
    )
    assert gap.status_code == 200, gap.json()
    assert gap.json()["linked_at_pair"]["invoice_number"] == "FT 2026/12"


def test_linked_row_lock_is_documented():
    limits = (_REPO / "docs/known-limitations.md").read_text()
    assert "## Retypes on linked rows" in limits
    assert "series_mismatch_cleared" in limits
    assert "## Migration 013" in limits

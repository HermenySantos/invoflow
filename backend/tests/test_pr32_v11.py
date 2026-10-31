"""QA gate 11. Dot-then-digit series, linked scans, and a stale accepted flag."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from app.models.audit_log import AuditLog
from app.schemas.document import SERIES_MISMATCH_DETAIL, invoice_series_prefix
from app.services import processing
from app.services.audit import log_series_mismatch_accepted
from app.services.efatura import import_purchases
from app.services.ocr import OCRResult, _apply_invoice_qr
from tests.conftest import TestingSessionLocal
from tests.test_pr32_v8 import _efatura, _qr
from tests.test_qa_gate_ocr import _stored_receipt

_REPO = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("number", "prefix"),
    [
        ("NC.2026/5", "NC"),
        ("NC.1", "NC"),
        ("ND.5/1", "ND"),
        ("NC2026", "NC"),
        ("NC001", "NC"),
        ("NC1 2026", "NC"),
        ("ND2026", "ND"),
        ("FT.2026/12", "FT"),
        ("FT.12", "FT"),
        ("FR.1", "FR"),
        ("FS.2026/1", "FS"),
        ("Fr.12", None),
        ("Fs.12", None),
        ("Nc.12", None),
        ("nd.2026", None),
        ("NC1", None),
        ("frete 12", None),
        ("NC 1", "NC"),
        ("NC1/2026", "NC"),
        ("NC-1", "NC"),
        ("NC 2026", "NC"),
    ],
)
def test_uppercase_dot_digit_and_glued_years_are_series(number, prefix):
    assert invoice_series_prefix(number) == prefix


def test_cross_credit_numbers_are_refused_both_ways(client, db, mock_user_headers):
    stored = _stored_receipt(
        db,
        document_type="FT",
        invoice_number="FT A/1",
        status="needs_review",
        ocr_raw_response=None,
        at_document_type=None,
    )
    on_ft = ("NC.2026/5", "NC.1", "ND.5/1", "NC2026", "NC001", "NC1 2026", "ND2026")
    for number in on_ft:
        for flag in (False, True):
            rejected = client.patch(
                f"/api/documents/{stored.id}",
                headers=mock_user_headers,
                json={
                    "document_type": "FT",
                    "invoice_number": number,
                    "accept_series_mismatch": flag,
                },
            )
            assert rejected.status_code == 422, (number, flag)
            assert rejected.json()["detail"] == SERIES_MISMATCH_DETAIL

    on_nc = ("FT.2026/12", "FT.12", "FR.1", "FS.2026/1")
    for number in on_nc:
        rejected = client.patch(
            f"/api/documents/{stored.id}",
            headers=mock_user_headers,
            json={
                "document_type": "NC",
                "invoice_number": number,
                "accept_series_mismatch": True,
            },
        )
        assert rejected.status_code == 422, number
        assert rejected.json()["detail"] == SERIES_MISMATCH_DETAIL
    db.refresh(stored)
    assert stored.document_type == "FT"
    assert stored.invoice_number == "FT A/1"
    assert stored.series_mismatch_accepted is False


def test_abbreviations_stay_allowed_and_an_uppercase_pair_can_be_accepted(client, db, mock_user_headers):
    stored = _stored_receipt(
        db,
        document_type="FT",
        invoice_number="FT A/1",
        status="needs_review",
        ocr_raw_response=None,
    )
    for document_type in ("FT", "NC"):
        for number in ("Fr.12", "Fs.12", "Nc.12", "frete 12", "NC1", "nd.2026"):
            saved = client.patch(
                f"/api/documents/{stored.id}",
                headers=mock_user_headers,
                json={"document_type": document_type, "invoice_number": number},
            )
            assert saved.status_code == 200, (document_type, number)

    # Uppercase FT.12 on an FR is inside the invoice family, so the flag can accept it.
    accepted = client.patch(
        f"/api/documents/{stored.id}",
        headers=mock_user_headers,
        json={
            "document_type": "FR",
            "invoice_number": "FT.12",
            "accept_series_mismatch": True,
        },
    )
    assert accepted.status_code == 200, accepted.json()
    assert accepted.json()["series_mismatch_accepted"] is True


def test_a_linked_scan_is_an_at_pair(client, db, mock_user_headers):
    stored = _stored_receipt(
        db,
        status="ready",
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
        previous_type="FR",
        previous_number="FT A/1",
    )
    db.commit()
    imported = import_purchases(
        db,
        user_id=stored.user_id,
        taxpayer_nif="555555555",
        invoices=[_efatura("FT", "FT 2026/12", "V11LINK")],
    )
    db.commit()
    assert stored.id in imported.linked_existing
    db.refresh(stored)
    assert stored.series_mismatch_accepted is False
    assert (
        db.query(AuditLog)
        .filter(AuditLog.entity_id == stored.id, AuditLog.action == "series_mismatch_accepted")
        .count()
        == 1
    )

    notes = client.patch(
        f"/api/documents/{stored.id}",
        headers=mock_user_headers,
        json={"review_notes": "ligado"},
    )
    assert notes.status_code == 200, notes.json()
    assert notes.json()["at_document_type"] == "FT"
    assert notes.json()["at_invoice_number"] == "FT 2026/12"
    assert notes.json()["series_mismatch_accepted"] is False

    retyped = client.patch(
        f"/api/documents/{stored.id}",
        headers=mock_user_headers,
        json={
            "document_type": "NC",
            "invoice_number": "2026/12",
            "status": "ready",
            "accept_series_mismatch": True,
        },
    )
    assert retyped.status_code == 422
    assert retyped.json()["detail"] == SERIES_MISMATCH_DETAIL
    db.refresh(stored)
    assert stored.document_type == "FR"
    assert stored.invoice_number == "FT 2026/12"
    assert stored.series_mismatch_accepted is False


def test_legacy_at_type_without_a_payload_refuses_the_flag(client, db, mock_user_headers):
    stored = _stored_receipt(
        db,
        status="needs_review",
        document_type="FR",
        invoice_number="FT 2026/12",
        at_document_type="FR",
        ocr_raw_response='{"ocr":"legacy"}',
    )
    rejected = client.patch(
        f"/api/documents/{stored.id}",
        headers=mock_user_headers,
        json={"status": "ready", "accept_series_mismatch": True},
    )
    assert rejected.status_code == 422
    assert rejected.json()["detail"] == SERIES_MISMATCH_DETAIL
    body = rejected.json()
    assert body["detail"] == SERIES_MISMATCH_DETAIL
    db.refresh(stored)
    assert stored.series_mismatch_accepted is False

    notes = client.patch(
        f"/api/documents/{stored.id}",
        headers=mock_user_headers,
        json={"review_notes": "sem qr"},
    )
    assert notes.status_code == 200, notes.json()
    assert notes.json()["at_document_type"] == "FR"
    assert notes.json()["at_invoice_number"] is None

    crossed = client.patch(
        f"/api/documents/{stored.id}",
        headers=mock_user_headers,
        json={
            "document_type": "NC",
            "invoice_number": "2026/12",
            "accept_series_mismatch": True,
        },
    )
    assert crossed.status_code == 422
    assert crossed.json()["detail"] == SERIES_MISMATCH_DETAIL


def test_qr_arrival_clears_the_accepted_flag_and_keeps_the_audit(db, monkeypatch):
    stored = _stored_receipt(
        db,
        status="processing",
        document_type="FR",
        invoice_number="FT 2026/12",
        series_mismatch_accepted=True,
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
    row = db.get(type(stored), stored.id)
    assert row.series_mismatch_accepted is False
    assert row.document_type == "FT"
    assert row.at_document_type == "FT"
    assert json.loads(row.ocr_raw_response)["qr"]["payload"]
    assert (
        db.query(AuditLog)
        .filter(AuditLog.entity_id == stored.id, AuditLog.action == "series_mismatch_accepted")
        .count()
        == 1
    )


def test_downgrade_and_keyword_limits_are_documented():
    migration = (_REPO / "backend/alembic/versions/010_series_mismatch_accepted.py").read_text()
    assert "Downgrade drops series_mismatch_accepted" in migration
    assert "audit" in migration.lower()
    limits = (_REPO / "docs/known-limitations.md").read_text()
    assert "N.C." in limits
    assert "IVA N/C" in limits
    assert "Coptic" in limits
    assert "Fr.12" in limits
    assert "Downgrading migration 010" in limits

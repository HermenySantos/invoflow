"""QA re-gate #4. OCR text never decides NC or ND."""

from __future__ import annotations

import json
import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.user import User
from app.schemas.document import AMOUNT_MISMATCH_DETAIL, TYPE_REQUIRED_DETAIL
from app.services.iva_adjust import contributions
from app.services.legacy_amounts import repair_legacy_negative_amounts
from app.services.ocr import OCRResult, _apply_invoice_qr
from app.services.ocr_extract import extract_fields
from app.services.pt_qr import InvoiceQR
from tests.test_qa_gate_ocr import SYNTHETIC_NIF, _stored_receipt

NIF = SYNTHETIC_NIF


def _fatura(*extra: str) -> str:
    return "\n".join(
        [
            "Fatura FT A/12",
            "Ana Exemplo",
            f"NIF: {NIF}",
            "Data: 15/06/2026",
            "Data de emissão: 15/06/2026",
            "IVA 23% 2,30",
            "Total 12,30",
            *extra,
        ]
    )


def test_nd_number_is_not_retyped_as_a_credit_note():
    fields = extract_fields(
        "ND A/3\n"
        "Ana Exemplo\n"
        f"NIF: {NIF}\n"
        "Data: 15/06/2026\n"
        "Data de emissão: 15/06/2026\n"
        "IVA 23% 2,30\n"
        "Total 12,30"
    )
    assert fields.invoice_number is None
    assert fields.suggested_invoice_number == "ND A/3"
    assert fields.suggested_type is None
    assert fields.document_type == "unclassified"
    assert fields.needs_review is True


def test_qr_nd_stays_nd_and_nets_positive():
    document = SimpleNamespace(
        id="nd-qr",
        status="ready",
        document_type="ND",
        net_amount=Decimal("8.13"),
        vat_amount=Decimal("1.87"),
        gross_amount=Decimal("10.00"),
        ocr_raw_response=json.dumps({"qr": {"document_type": "ND", "fiscal_status": "N"}}),
        expense_category="utilities",
        deductible_pct_override=None,
        created_at=None,
        document_date=date(2026, 6, 15),
        vendor_nif=NIF,
        vendor_name="Ana Exemplo",
        invoice_number="ND A/3",
    )
    counted = contributions([document])[0]
    assert counted.vat == Decimal("1.87")
    assert counted.gross == Decimal("10.00")


def test_loose_nc_tokens_do_not_change_the_fatura():
    for line in (
        "Cabo NC 3m",
        "Plano nc 2026",
        "Ref NC",
        "Retifica",
        "Doc. origem:",
        "Saldo apos NC",
    ):
        fields = extract_fields(_fatura(line))
        assert fields.invoice_number is None, line
        assert fields.suggested_invoice_number == "FT A/12", line
        assert fields.suggested_type == "FT", line
        assert fields.document_type == "unclassified", line
        assert fields.needs_review is True, line
    cancelled = extract_fields(_fatura("Anulação da"))
    assert cancelled.suggested_type is None
    assert cancelled.suggested_invoice_number is None
    assert cancelled.document_type == "unclassified"


def test_a_real_credit_or_debit_signal_stays_unclassified():
    samples = (
        "sera emitida NC A/5",
        "Nota de credito emitida em 30 dias",
        "Nota de cred1to",
        "Nota de\ncrédito",
        "Ref. NC A/9",
    )
    for extra in samples:
        fields = extract_fields(_fatura(extra))
        assert fields.invoice_number is None, extra
        assert fields.suggested_type not in {"FT", "FS", "FR"}, extra
        assert fields.suggested_invoice_number != "FT A/12", extra
        assert fields.document_type == "unclassified", extra
        assert fields.needs_review is True, extra


def test_ready_amount_patch_without_status_rechecks_the_sum(
    client: TestClient, db: Session, mock_user_headers: dict
):
    stored = _stored_receipt(
        db,
        status="ready",
        document_type="FT",
        net_amount=Decimal("10.00"),
        vat_amount=Decimal("2.30"),
        gross_amount=Decimal("12.30"),
    )
    patched = client.patch(
        f"/api/documents/{stored.id}",
        headers=mock_user_headers,
        json={"vat_amount": "9.99"},
    )
    assert patched.status_code == 422
    assert patched.json()["detail"] == AMOUNT_MISMATCH_DETAIL
    db.refresh(stored)
    assert stored.vat_amount == Decimal("2.30")
    assert stored.status == "ready"


def test_more_than_two_decimals_are_rounded_then_checked(
    client: TestClient, db: Session, mock_user_headers: dict
):
    stored = _stored_receipt(db, status="ready", document_type="FT")
    patched = client.patch(
        f"/api/documents/{stored.id}",
        headers=mock_user_headers,
        json={"net_amount": "10.005", "vat_amount": "2.305", "gross_amount": "12.30"},
    )
    assert patched.status_code == 422
    assert AMOUNT_MISMATCH_DETAIL in patched.text
    db.refresh(stored)
    assert stored.net_amount == Decimal("10.00")


def test_iva_above_gross_without_a_net_is_rejected(
    client: TestClient, db: Session, mock_user_headers: dict
):
    stored = _stored_receipt(
        db,
        status="ready",
        document_type="FT",
        net_amount=None,
        vat_amount=Decimal("2.30"),
        gross_amount=Decimal("12.30"),
    )
    patched = client.patch(
        f"/api/documents/{stored.id}",
        headers=mock_user_headers,
        json={"vat_amount": "3.00", "gross_amount": "2.00"},
    )
    assert patched.status_code == 422
    assert AMOUNT_MISMATCH_DETAIL in patched.text
    db.refresh(stored)
    assert stored.gross_amount == Decimal("12.30")


def test_ready_requires_a_concrete_type(
    client: TestClient, db: Session, mock_user_headers: dict
):
    stored = _stored_receipt(db, document_type="unclassified")
    patched = client.patch(
        f"/api/documents/{stored.id}",
        headers=mock_user_headers,
        json={"status": "ready", "document_type": "unclassified"},
    )
    assert patched.status_code == 422
    assert patched.json()["detail"] == TYPE_REQUIRED_DETAIL


def test_qr_without_base_and_a_bad_ocr_net_needs_review():
    qr = InvoiceQR(
        vendor_nif=NIF,
        document_date=date(2026, 6, 15),
        invoice_number="FT A/12",
        atcud=None,
        net_amount=None,
        vat_amount=Decimal("2.30"),
        gross_amount=Decimal("15.00"),
        vat_rate=None,
        document_type="FT",
        fiscal_status="N",
        breakdown=[],
        payload="O:15.00",
    )
    result = OCRResult(
        vendor_name="Ana Exemplo",
        net_amount=Decimal("10.00"),
        vat_amount=Decimal("2.30"),
        gross_amount=Decimal("12.30"),
        document_type="unclassified",
        backend="tesseract",
    )
    applied = _apply_invoice_qr(result, qr)
    assert applied.document_type == "FT"
    assert applied.net_amount == Decimal("10.00")
    assert applied.needs_review is True


def _legacy(db: Session, user: User, **fields) -> Document:
    document = Document(
        user_id=user.id,
        status=fields.pop("status", "ready"),
        storage_key=f"{user.clerk_id}/{uuid.uuid4().hex[:8]}.jpg",
        original_filename="old.jpg",
        mime_type="image/jpeg",
        vendor_nif=NIF,
        expense_category="utilities",
        document_date=date(2026, 4, 15),
        document_type=fields.pop("document_type", " "),
        **fields,
    )
    db.add(document)
    db.commit()
    return document


def test_migration_does_not_infer_nc_from_a_minus(db: Session):
    user = User(clerk_id=f"legacy-{uuid.uuid4().hex[:8]}", email="")
    db.add(user)
    db.commit()
    negative = _legacy(
        db,
        user,
        net_amount=Decimal("-8.13"),
        vat_amount=Decimal("1.87"),
        gross_amount=Decimal("-10.00"),
    )
    from_qr = _legacy(
        db,
        user,
        net_amount=Decimal("-8.13"),
        vat_amount=Decimal("-1.87"),
        gross_amount=Decimal("-10.00"),
        ocr_raw_response=json.dumps({"qr": {"document_type": "NC"}}),
    )
    positive = _legacy(db, user, net_amount=Decimal("10.00"), vat_amount=Decimal("2.30"), gross_amount=Decimal("12.30"))
    simplified = _legacy(
        db,
        user,
        net_amount=Decimal("10.00"),
        vat_amount=Decimal("2.30"),
        gross_amount=Decimal("12.30"),
        ocr_raw_response=json.dumps({"qr": {"document_type": "FS"}}),
    )

    repair_legacy_negative_amounts(db.connection())
    db.commit()
    for document in (negative, from_qr, positive, simplified):
        db.refresh(document)

    assert negative.document_type == "unclassified"
    assert negative.status == "needs_review"
    assert negative.gross_amount == Decimal("10.00")
    assert contributions([negative]) == []

    assert from_qr.document_type == "NC"
    assert from_qr.status == "ready"
    assert from_qr.net_amount == Decimal("8.13")
    assert contributions([from_qr])[0].vat == Decimal("-1.87")

    assert positive.document_type == "FT"
    assert positive.status == "ready"
    assert simplified.document_type == "FS"

    repair_legacy_negative_amounts(db.connection())
    db.commit()
    db.refresh(negative)
    assert negative.gross_amount == Decimal("10.00")
    assert negative.document_type == "unclassified"
    # Downgrade writes a NULL type. Head's column is NOT NULL, so that
    # round-trip is the Postgres check in scripts/check_migration_008.py.


def test_summary_lists_rows_excluded_from_iva(client: TestClient, db: Session):
    clerk_id = f"excluded-{uuid.uuid4().hex[:8]}"
    user = User(clerk_id=clerk_id, email="")
    db.add(user)
    db.commit()

    def add(**fields) -> None:
        db.add(
            Document(
                user_id=user.id,
                storage_key=f"{clerk_id}/{uuid.uuid4().hex[:8]}.jpg",
                original_filename="r.jpg",
                mime_type="image/jpeg",
                document_date=date(2026, 9, 15),
                expense_category="utilities",
                **fields,
            )
        )

    add(
        status="ready",
        document_type="FT",
        vendor_name="Contada",
        invoice_number="FT A/1",
        net_amount=Decimal("10.00"),
        vat_amount=Decimal("2.30"),
        gross_amount=Decimal("12.30"),
    )
    add(
        status="needs_review",
        document_type="unclassified",
        vendor_name="Por classificar",
        invoice_number="FT A/2",
        net_amount=Decimal("10.00"),
        vat_amount=Decimal("2.30"),
        gross_amount=Decimal("12.30"),
    )
    add(
        status="ready",
        document_type="FT",
        vendor_name="Partida",
        invoice_number="FT A/3",
        net_amount=Decimal("1.00"),
        vat_amount=Decimal("1.00"),
        gross_amount=Decimal("12.30"),
    )
    db.commit()

    summary = client.get(
        "/api/summary",
        params={"period_type": "month", "year": 2026, "month": 9},
        headers={"X-Mock-User-Id": clerk_id},
    ).json()
    assert summary["ready_count"] == 1
    assert summary["excluded_count"] == 2
    reasons = {item["vendor_name"]: item["reason"] for item in summary["excluded_documents"]}
    assert reasons == {
        "Por classificar": "por classificar",
        "Partida": "valores inconsistentes",
    }
    assert summary["deductible_vat"] == "2.30"

import io
import uuid
from decimal import Decimal

from fastapi.testclient import TestClient
from pypdf import PdfReader

from app.services.storage import get_storage_service
from tests.test_invoice_qr import fatura_photo

# Report figures: NC 23.00, cancelled 11.50, a duplicate of the 23.00 purchase,
# and the purchase that remains after those are taken out (6.73).
# 23 + 23 + 11.50 + 23 + 6.73 = 87.23.
PURCHASE = (
    "A:501111111*B:999999990*C:PT*D:FT*E:N*F:20260115*G:FT A/1*H:ATCUD-PURCHASE*"
    "I1:PT*I7:100.00*I8:23.00*N:23.00*O:123.00*Q:abcd*R:1"
)
CANCELLED = (
    "A:502222222*B:999999990*C:PT*D:FT*E:A*F:20260201*G:FT B/2*H:ATCUD-CANCELLED*"
    "I1:PT*I7:50.00*I8:11.50*N:11.50*O:61.50*Q:abcd*R:1"
)
CREDIT_NOTE = (
    "A:501111111*B:999999990*C:PT*D:NC*E:N*F:20260210*G:NC A/1*H:ATCUD-CREDIT*"
    "I1:PT*I7:100.00*I8:23.00*N:23.00*O:123.00*Q:abcd*R:1"
)
REMAINDER = (
    "A:503333333*B:999999990*C:PT*D:FT*E:N*F:20260301*G:FT C/3*H:ATCUD-REST*"
    "I1:PT*I7:29.26*I8:6.73*N:6.73*O:35.99*Q:abcd*R:1"
)


def _png(payload: str) -> bytes:
    buffer = io.BytesIO()
    fatura_photo(payload).save(buffer, format="PNG")
    return buffer.getvalue()


def _upload(client: TestClient, headers: dict, name: str, payload: str, body: bytes | None = None) -> dict:
    content = body if body is not None else _png(payload)
    key = f"{headers['X-Mock-User-Id']}/2026/01/{uuid.uuid4().hex[:8]}_{name}.png"
    client.put(get_storage_service().get_upload_url(key, "image/png"), content=content)
    created = client.post(
        "/api/documents",
        json={
            "storage_key": key,
            "original_filename": f"{name}.png",
            "file_size": len(content),
            "mime_type": "image/png",
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    document_id = created.json()["id"]
    patched = client.patch(
        f"/api/documents/{document_id}",
        json={"status": "ready", "expense_category": "utilities", "deductible_pct_override": 100},
        headers=headers,
    )
    assert patched.status_code == 200, patched.text
    return client.get(f"/api/documents/{document_id}", headers=headers).json()


def test_q1_credit_note_and_cancelled_invoice_do_not_inflate_iva(client: TestClient):
    headers = {"X-Mock-User-Id": f"q1-{uuid.uuid4().hex[:8]}", "X-Mock-User-Email": "q1@example.com"}
    purchase_png = _png(PURCHASE)
    documents = [
        _upload(client, headers, "purchase", PURCHASE, purchase_png),
        _upload(client, headers, "purchase-dup", PURCHASE, purchase_png),
        _upload(client, headers, "cancelled", CANCELLED),
        _upload(client, headers, "credit-note", CREDIT_NOTE),
        _upload(client, headers, "remainder", REMAINDER),
    ]

    stored_vat = sum((Decimal(document["vat_amount"]) for document in documents), Decimal("0"))
    assert stored_vat == Decimal("87.23")
    assert all(Decimal(document["vat_amount"]) >= 0 for document in documents)

    summary = client.get(
        "/api/summary",
        params={"period_type": "quarter", "year": 2026, "quarter": 1},
        headers=headers,
    ).json()
    assert summary["deductible_vat"] == "6.73"
    assert Decimal(summary["total_vat"]) >= 0
    assert Decimal(summary["deductible_vat"]) >= 0

    projection = client.get(
        "/api/summary/projection",
        params={"year": 2026, "quarter": 1, "as_of": "2026-03-31"},
        headers=headers,
    ).json()
    assert projection["confirmed_deductible_to_date"] == "6.73"

    export = client.get(
        "/api/export",
        params={"period_type": "quarter", "year": 2026, "quarter": 1},
        headers=headers,
    )
    assert export.status_code == 200
    import zipfile

    archive = zipfile.ZipFile(io.BytesIO(export.content))
    csv_text = archive.read("summary.csv").decode("utf-8-sig")
    assert "87,23" not in csv_text
    assert "6,73" in csv_text
    pdf_text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(archive.read("summary.pdf"))).pages)
    assert "6,73" in pdf_text
    assert "87,23" not in pdf_text

    listed = client.get("/api/documents", headers=headers).json()["documents"]
    assert all(Decimal(document["vat_amount"]) >= 0 for document in listed)

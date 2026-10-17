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
    data_rows = [
        line
        for line in csv_text.splitlines()
        if line
        and not line.startswith("Avisos")
        and not line.startswith("\ufeffAvisos")
        and not line.startswith("Total")
    ]
    assert data_rows[0].startswith("ID;") or "ID" in data_rows[0]
    assert len(data_rows) - 1 == 3
    assert "-23,00" in csv_text
    assert "Total de documentos: 3" in pdf_text
    assert "Prazo de entrega" in pdf_text
    assert "20 de maio de 2026" in pdf_text


SMALL = (
    "A:501111111*B:999999990*C:PT*D:FT*E:N*F:20260115*G:FT SMALL*H:ATCUD-SMALL*"
    "I1:PT*I7:56.52*I8:13.00*N:13.00*O:69.52*Q:abcd*R:1"
)
OTHER = (
    "A:504444444*B:999999990*C:PT*D:FT*E:N*F:20260118*G:FT OTHER*H:ATCUD-OTHER*"
    "I1:PT*I7:100.00*I8:23.00*N:23.00*O:123.00*Q:abcd*R:1"
)
BIG_CREDIT = (
    "A:501111111*B:999999990*C:PT*D:NC*E:N*F:20260120*G:NC BIG*H:ATCUD-BIG*"
    "I1:PT*I7:113.04*I8:26.00*N:26.00*O:139.04*Q:abcd*R:1"
)
Q1_INVOICE = (
    "A:501111111*B:999999990*C:PT*D:FT*E:N*F:20260115*G:FT Q1*H:ATCUD-Q1*"
    "I1:PT*I7:100.00*I8:23.00*N:23.00*O:123.00*Q:abcd*R:1"
)
Q2_CREDIT = (
    "A:501111111*B:999999990*C:PT*D:NC*E:N*F:20260415*G:NC Q2*H:ATCUD-Q2*"
    "I1:PT*I7:43.48*I8:10.00*N:10.00*O:53.48*Q:abcd*R:1"
)
ORPHAN_CREDIT = (
    "A:509999999*B:999999990*C:PT*D:NC*E:N*F:20260202*G:NC ORPHAN*H:ATCUD-ORPHAN*"
    "I1:PT*I7:21.74*I8:5.00*N:5.00*O:26.74*Q:abcd*R:1"
)


def _period(client, headers, **params):
    response = client.get("/api/summary", params=params, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _export_texts(client, headers, **params):
    import zipfile

    export = client.get("/api/export", params=params, headers=headers)
    assert export.status_code == 200, export.text
    archive = zipfile.ZipFile(io.BytesIO(export.content))
    csv_text = archive.read("summary.csv").decode("utf-8-sig")
    pdf_text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(archive.read("summary.pdf"))).pages)
    return csv_text, pdf_text, archive.namelist()


def test_credit_larger_than_its_invoice_is_fully_netted(client: TestClient):
    headers = {"X-Mock-User-Id": f"big-{uuid.uuid4().hex[:8]}", "X-Mock-User-Email": "big@example.com"}
    for name, payload in (("small", SMALL), ("other", OTHER), ("credit", BIG_CREDIT)):
        _upload(client, headers, name, payload)

    summary = _period(client, headers, period_type="quarter", year=2026, quarter=1)
    assert summary["deductible_vat"] == "10.00"
    assert summary["total_vat"] == "10.00"
    projection = client.get(
        "/api/summary/projection",
        params={"year": 2026, "quarter": 1, "as_of": "2026-03-31"},
        headers=headers,
    ).json()
    assert projection["confirmed_deductible_to_date"] == "10.00"
    csv_text, pdf_text, _names = _export_texts(
        client, headers, period_type="quarter", year=2026, quarter=1
    )
    assert "10,00" in csv_text
    assert "-26,00" in csv_text
    assert "10,00" in pdf_text
    assert "-26,00" in pdf_text


def test_q2_credit_for_a_q1_invoice_counts_in_q2_with_a_warning(client: TestClient):
    headers = {"X-Mock-User-Id": f"cross-{uuid.uuid4().hex[:8]}", "X-Mock-User-Email": "cross@example.com"}
    _upload(client, headers, "q1", Q1_INVOICE)
    _upload(client, headers, "q2-credit", Q2_CREDIT)

    q1 = _period(client, headers, period_type="quarter", year=2026, quarter=1)
    q2 = _period(client, headers, period_type="quarter", year=2026, quarter=2)
    assert q1["deductible_vat"] == "23.00"
    assert q2["deductible_vat"] == "-10.00"
    assert any(
        "outro período" in warning and "NC Q2" in warning and "2026-04-15" in warning
        for warning in q2["warnings"]
    )
    projection = client.get(
        "/api/summary/projection",
        params={"year": 2026, "quarter": 2, "as_of": "2026-06-30"},
        headers=headers,
    ).json()
    assert projection["confirmed_deductible_to_date"] == "-10.00"
    assert any(
        "outro período" in warning and "NC Q2" in warning and "2026-04-15" in warning
        for warning in projection["warnings"]
    )
    csv_text, pdf_text, _names = _export_texts(
        client, headers, period_type="quarter", year=2026, quarter=2
    )
    assert "-10,00" in csv_text
    assert "outro período" in csv_text
    assert "NC Q2" in csv_text
    assert "2026-04-15" in csv_text
    assert "-10,00" in pdf_text
    assert "outro período" in pdf_text
    assert "NC Q2" in pdf_text
    assert "2026-04-15" in pdf_text
    assert "21 de setembro de 2026" in pdf_text


def test_credit_note_without_an_invoice_is_counted_and_warned(client: TestClient):
    headers = {"X-Mock-User-Id": f"orphan-{uuid.uuid4().hex[:8]}", "X-Mock-User-Email": "orphan@example.com"}
    _upload(client, headers, "orphan", ORPHAN_CREDIT)
    summary = _period(client, headers, period_type="quarter", year=2026, quarter=1)
    assert summary["deductible_vat"] == "-5.00"
    assert any(
        "nota de crédito sem fatura associada" in warning and "NC ORPHAN" in warning and "2026-02-02" in warning
        for warning in summary["warnings"]
    )
    projection = client.get(
        "/api/summary/projection",
        params={"year": 2026, "quarter": 1, "as_of": "2026-03-31"},
        headers=headers,
    ).json()
    assert any(
        "nota de crédito sem fatura associada" in warning and "NC ORPHAN" in warning and "2026-02-02" in warning
        for warning in projection["warnings"]
    )
    csv_text, pdf_text, _names = _export_texts(
        client, headers, period_type="quarter", year=2026, quarter=1
    )
    assert "nota de crédito sem fatura associada" in csv_text
    assert "NC ORPHAN" in csv_text
    assert "2026-02-02" in csv_text
    assert "nota de crédito sem fatura associada" in pdf_text
    assert "NC ORPHAN" in pdf_text
    assert "2026-02-02" in pdf_text
    assert "-5,00" in csv_text


def test_duplicate_file_keeps_the_reviewed_copy(client: TestClient):
    headers = {"X-Mock-User-Id": f"dup-{uuid.uuid4().hex[:8]}", "X-Mock-User-Email": "dup@example.com"}
    content = _png(PURCHASE)
    key = f"{headers['X-Mock-User-Id']}/2026/01/{uuid.uuid4().hex[:8]}_first.png"
    client.put(get_storage_service().get_upload_url(key, "image/png"), content=content)
    first = client.post(
        "/api/documents",
        json={
            "storage_key": key,
            "original_filename": "first.png",
            "file_size": len(content),
            "mime_type": "image/png",
        },
        headers=headers,
    )
    assert first.status_code == 201, first.text
    second = _upload(client, headers, "second", PURCHASE, content)
    assert second["status"] == "ready"
    stored = client.get(f"/api/documents/{first.json()['id']}", headers=headers)
    assert stored.status_code == 200, stored.text
    assert stored.json()["status"] == "needs_review"
    summary = _period(client, headers, period_type="quarter", year=2026, quarter=1)
    assert summary["deductible_vat"] == "23.00"


def test_zip_entry_names_drop_path_parts(client: TestClient):
    headers = {"X-Mock-User-Id": f"zip-{uuid.uuid4().hex[:8]}", "X-Mock-User-Email": "zip@example.com"}
    content = _png(PURCHASE)
    key = f"{headers['X-Mock-User-Id']}/2026/01/{uuid.uuid4().hex[:8]}_ok.png"
    client.put(get_storage_service().get_upload_url(key, "image/png"), content=content)
    created = client.post(
        "/api/documents",
        json={
            "storage_key": key,
            "original_filename": "..\\..\\evil.exe",
            "file_size": len(content),
            "mime_type": "image/png",
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    client.patch(
        f"/api/documents/{created.json()['id']}",
        json={"status": "ready", "expense_category": "utilities", "deductible_pct_override": 100},
        headers=headers,
    )
    _csv, _pdf, names = _export_texts(client, headers, period_type="quarter", year=2026, quarter=1)
    receipt_names = [name for name in names if name.startswith("receipts/")]
    assert receipt_names
    assert all("\\" not in name and ".." not in name for name in receipt_names)
    assert all(name.rsplit(".", 1)[-1] in {"jpg", "jpeg", "png", "gif", "webp", "pdf", "bmp", "tif", "tiff", "heic", "heif", "bin"} for name in receipt_names)


def test_same_file_moved_to_another_quarter_is_not_counted_twice(client: TestClient):
    headers = {"X-Mock-User-Id": f"move-{uuid.uuid4().hex[:8]}", "X-Mock-User-Email": "move@example.com"}
    content = _png(PURCHASE)
    _upload(client, headers, "original", PURCHASE, content)
    copy = _upload(client, headers, "moved", PURCHASE, content)
    moved = client.patch(
        f"/api/documents/{copy['id']}",
        json={"document_date": "2026-04-15"},
        headers=headers,
    )
    assert moved.status_code == 200, moved.text
    q1 = _period(client, headers, period_type="quarter", year=2026, quarter=1)
    q2 = _period(client, headers, period_type="quarter", year=2026, quarter=2)
    assert Decimal(q1["deductible_vat"]) + Decimal(q2["deductible_vat"]) == Decimal("23.00")
    warnings = q1["warnings"] + q2["warnings"]
    assert any("duplicad" in warning for warning in warnings)

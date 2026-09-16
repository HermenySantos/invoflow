"""
OCR backends behind one interface.

Default is open-source:
  auto       → Tesseract if installed, otherwise mock (no keys)
  tesseract  → Tesseract + PT field extractor (optional local LLM polish)
  mock       → deterministic demo data, no system OCR
  azure      → optional paid Azure Document Intelligence

Azure is never required for a local demo.
"""

from __future__ import annotations

import asyncio
import json
import random
import shutil
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from io import BytesIO
from typing import Optional

import httpx
from PIL import Image

from app.core.config import get_settings
from app.services.ocr_extract import ExtractedFields, extract_fields, extracted_to_json

settings = get_settings()


@dataclass
class OCRResult:
    """Extracted data from OCR processing."""

    vendor_name: Optional[str] = None
    vendor_nif: Optional[str] = None
    invoice_number: Optional[str] = None
    document_date: Optional[date] = None
    net_amount: Optional[Decimal] = None
    vat_amount: Optional[Decimal] = None
    gross_amount: Optional[Decimal] = None
    vat_rate: Optional[Decimal] = None
    confidence: float = 0.0
    raw_response: Optional[str] = None
    needs_review: bool = False
    error: Optional[str] = None
    backend: str = "mock"


def tesseract_available() -> bool:
    if shutil.which("tesseract") is None:
        return False
    try:
        import pytesseract  # noqa: F401
    except ImportError:
        return False
    return True


def resolve_ocr_backend() -> str:
    """Pick a runnable backend. Azure is opt-in only."""
    requested = (settings.ocr_backend or "auto").strip().lower()
    if requested in {"mock", "tesseract", "azure", "auto"}:
        backend = requested
    elif settings.ocr_mock_mode:
        backend = "mock"
    else:
        backend = "auto"

    if backend == "auto":
        backend = "tesseract" if tesseract_available() else "mock"
    if backend == "tesseract" and not tesseract_available():
        backend = "mock"
    if backend == "azure" and (not settings.azure_doc_endpoint or not settings.azure_doc_key):
        backend = "tesseract" if tesseract_available() else "mock"
    return backend


class OCRService:
    """Process receipts/invoices through the configured OCR backend."""

    def __init__(self):
        self.backend = resolve_ocr_backend()
        self.endpoint = settings.azure_doc_endpoint
        self.api_key = settings.azure_doc_key

    async def process_document(self, file_content: bytes, mime_type: str) -> OCRResult:
        backend = resolve_ocr_backend()
        self.backend = backend
        if backend == "mock":
            return self._generate_mock_result(mime_type)
        if backend == "azure":
            return await self._process_with_azure(file_content, mime_type)
        return await self._process_with_tesseract(file_content, mime_type)

    def _generate_mock_result(self, mime_type: str) -> OCRResult:
        vendors = [
            ("Continente", "500100144"),
            ("Pingo Doce", "500829993"),
            ("Worten", "502428880"),
            ("GALP Energia", "504499777"),
            ("NOS Comunicações", "504448064"),
            ("EDP Comercial", "503504564"),
            ("Uber Portugal", "514111111"),
            ("Bolt Technology", None),
            ("Restaurante O Manel", "123456789"),
            ("Papelaria Central", "507442013"),
        ]
        vendor_name, vendor_nif = random.choice(vendors)
        gross = Decimal(str(round(random.uniform(5.0, 250.0), 2)))
        vat_rate = Decimal(random.choice(["6.00", "13.00", "23.00"]))
        vat = (gross * vat_rate / (100 + vat_rate)).quantize(Decimal("0.01"))
        net = gross - vat
        days_ago = random.randint(0, 30)
        doc_date = date.today() - timedelta(days=days_ago)
        confidence = random.uniform(0.7, 0.99)
        needs_review = confidence < 0.85 or random.random() < 0.15
        if random.random() < 0.1:
            vendor_nif = None
        if random.random() < 0.05:
            doc_date = None
            needs_review = True

        return OCRResult(
            vendor_name=vendor_name,
            vendor_nif=vendor_nif,
            invoice_number=f"FT {datetime.now().year}/{random.randint(1000, 9999)}",
            document_date=doc_date,
            net_amount=net,
            vat_amount=vat,
            gross_amount=gross,
            vat_rate=vat_rate,
            confidence=confidence * 100,
            raw_response=json.dumps({"mock": True, "vendor": vendor_name, "mime": mime_type}),
            needs_review=needs_review,
            backend="mock",
        )

    async def _process_with_tesseract(self, file_content: bytes, mime_type: str) -> OCRResult:
        try:
            text = await asyncio.to_thread(self._read_document_text, file_content, mime_type)
        except Exception as exc:
            return OCRResult(
                error=f"Tesseract read error: {exc}",
                confidence=0,
                needs_review=True,
                backend="tesseract",
            )

        if not text.strip():
            return OCRResult(
                error="No text found in document",
                confidence=0,
                needs_review=True,
                raw_response=json.dumps({"backend": "tesseract", "text": ""}),
                backend="tesseract",
            )

        fields = extract_fields(text)
        if settings.ollama_base_url:
            llm_fields = await self._extract_with_ollama(text)
            if llm_fields:
                fields = _merge_fields(fields, llm_fields)

        return _fields_to_result(fields, text, backend="tesseract")

    def _read_document_text(self, file_content: bytes, mime_type: str) -> str:
        mime = (mime_type or "").lower()
        if mime == "application/pdf" or (file_content[:4] == b"%PDF"):
            pdf_text = _extract_pdf_text(file_content)
            if pdf_text.strip():
                return pdf_text
            image = _pdf_first_page_image(file_content)
            if image is None:
                return pdf_text
            return _image_to_text(image)
        image = Image.open(BytesIO(file_content))
        return _image_to_text(image)

    async def _extract_with_ollama(self, text: str) -> Optional[ExtractedFields]:
        """Optional local LLM polish (Ollama). Never required."""
        prompt = (
            "Extract fields from this Portuguese receipt or invoice. "
            "Return JSON only with keys: vendor_name, vendor_nif, invoice_number, "
            "document_date (YYYY-MM-DD), net_amount, vat_amount, gross_amount, vat_rate. "
            "Use null when unknown. Do not invent values.\n\n"
            f"{text[:4000]}"
        )
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{settings.ollama_base_url.rstrip('/')}/api/generate",
                    json={
                        "model": settings.ollama_model,
                        "prompt": prompt,
                        "stream": False,
                        "format": "json",
                    },
                )
                response.raise_for_status()
                raw = response.json().get("response", "")
                data = json.loads(raw) if isinstance(raw, str) else raw
                return _fields_from_mapping(data)
        except Exception:
            return None

    async def _process_with_azure(self, file_content: bytes, mime_type: str) -> OCRResult:
        try:
            model_id = "prebuilt-receipt"
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.endpoint}/documentintelligence/documentModels/{model_id}:analyze?api-version=2024-02-29-preview",
                    headers={
                        "Ocp-Apim-Subscription-Key": self.api_key,
                        "Content-Type": mime_type,
                    },
                    content=file_content,
                )
                if response.status_code != 202:
                    return OCRResult(
                        error=f"Azure API error: {response.status_code} - {response.text}",
                        confidence=0,
                        needs_review=True,
                        backend="azure",
                    )
                operation_location = response.headers.get("Operation-Location")
                if not operation_location:
                    return OCRResult(
                        error="Azure API did not return operation location",
                        confidence=0,
                        needs_review=True,
                        backend="azure",
                    )
                for _ in range(30):
                    await asyncio.sleep(1)
                    result_response = await client.get(
                        operation_location,
                        headers={"Ocp-Apim-Subscription-Key": self.api_key},
                    )
                    result_data = result_response.json()
                    status = result_data.get("status")
                    if status == "succeeded":
                        parsed = self._parse_azure_result(result_data)
                        parsed.backend = "azure"
                        return parsed
                    if status == "failed":
                        return OCRResult(
                            error="Azure processing failed",
                            confidence=0,
                            needs_review=True,
                            raw_response=json.dumps(result_data),
                            backend="azure",
                        )
                return OCRResult(
                    error="Azure processing timeout",
                    confidence=0,
                    needs_review=True,
                    backend="azure",
                )
        except Exception as exc:
            return OCRResult(
                error=f"OCR processing error: {exc}",
                confidence=0,
                needs_review=True,
                backend="azure",
            )

    def _parse_azure_result(self, result_data: dict) -> OCRResult:
        try:
            analyze_result = result_data.get("analyzeResult", {})
            documents = analyze_result.get("documents", [])
            if not documents:
                return OCRResult(
                    error="No document found in response",
                    confidence=0,
                    needs_review=True,
                    raw_response=json.dumps(result_data),
                    backend="azure",
                )
            doc = documents[0]
            fields = doc.get("fields", {})
            confidence = doc.get("confidence", 0) * 100
            vendor_name = self._get_field_value(fields, "MerchantName")
            invoice_number = self._get_field_value(fields, "TransactionId")
            vendor_nif = None
            merchant_address = self._get_field_value(fields, "MerchantAddress")
            if merchant_address:
                vendor_nif = extract_fields(merchant_address).vendor_nif
            content = analyze_result.get("content", "")
            if not vendor_nif:
                vendor_nif = extract_fields(content).vendor_nif
            doc_date = None
            date_str = self._get_field_value(fields, "TransactionDate")
            if date_str:
                try:
                    doc_date = datetime.fromisoformat(date_str.replace("Z", "")).date()
                except ValueError:
                    pass
            gross_amount = self._get_currency_value(fields, "Total")
            vat_amount = self._get_currency_value(fields, "TotalTax")
            net_amount = None
            if gross_amount and vat_amount:
                net_amount = gross_amount - vat_amount
            vat_rate = None
            if net_amount and vat_amount and net_amount > 0:
                vat_rate = (vat_amount / net_amount * 100).quantize(Decimal("0.01"))
            needs_review = confidence < 85 or not vendor_name or not gross_amount
            return OCRResult(
                vendor_name=vendor_name,
                vendor_nif=vendor_nif,
                invoice_number=invoice_number,
                document_date=doc_date,
                net_amount=net_amount,
                vat_amount=vat_amount,
                gross_amount=gross_amount,
                vat_rate=vat_rate,
                confidence=confidence,
                raw_response=json.dumps(result_data),
                needs_review=needs_review,
                backend="azure",
            )
        except Exception as exc:
            return OCRResult(
                error=f"Error parsing Azure response: {exc}",
                confidence=0,
                needs_review=True,
                raw_response=json.dumps(result_data),
                backend="azure",
            )

    def _get_field_value(self, fields: dict, field_name: str) -> Optional[str]:
        field = fields.get(field_name, {})
        return field.get("valueString") or field.get("content")

    def _get_currency_value(self, fields: dict, field_name: str) -> Optional[Decimal]:
        field = fields.get(field_name, {})
        value = field.get("valueCurrency", {}).get("amount")
        if value is not None:
            return Decimal(str(value))
        content = field.get("content", "")
        if content:
            from app.services.ocr_extract import parse_pt_amount

            return parse_pt_amount(content)
        return None


def _image_to_text(image: Image.Image) -> str:
    import pytesseract

    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    langs = settings.tesseract_lang or "por+eng"
    return pytesseract.image_to_string(image, lang=langs)


def _extract_pdf_text(file_content: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        return ""
    reader = PdfReader(BytesIO(file_content))
    pages = []
    for page in reader.pages[:3]:
        pages.append(page.extract_text() or "")
    return "\n".join(pages)


def _pdf_first_page_image(file_content: bytes) -> Optional[Image.Image]:
    """Best-effort rasterization; returns None if pdf2image/poppler are missing."""
    try:
        from pdf2image import convert_from_bytes
    except ImportError:
        return None
    try:
        images = convert_from_bytes(file_content, first_page=1, last_page=1)
        return images[0] if images else None
    except Exception:
        return None


def _fields_to_result(fields: ExtractedFields, text: str, backend: str) -> OCRResult:
    return OCRResult(
        vendor_name=fields.vendor_name,
        vendor_nif=fields.vendor_nif,
        invoice_number=fields.invoice_number,
        document_date=fields.document_date,
        net_amount=fields.net_amount,
        vat_amount=fields.vat_amount,
        gross_amount=fields.gross_amount,
        vat_rate=fields.vat_rate,
        confidence=fields.confidence,
        raw_response=extracted_to_json(fields, extra={"backend": backend, "text": text[:4000]}),
        needs_review=fields.needs_review,
        backend=backend,
    )


def _fields_from_mapping(data: dict) -> ExtractedFields:
    from app.services.ocr_extract import parse_pt_amount

    doc_date = None
    raw_date = data.get("document_date")
    if raw_date:
        try:
            doc_date = date.fromisoformat(str(raw_date)[:10])
        except ValueError:
            doc_date = None
    return ExtractedFields(
        vendor_name=data.get("vendor_name") or None,
        vendor_nif=data.get("vendor_nif") or None,
        invoice_number=data.get("invoice_number") or None,
        document_date=doc_date,
        net_amount=parse_pt_amount(str(data["net_amount"])) if data.get("net_amount") else None,
        vat_amount=parse_pt_amount(str(data["vat_amount"])) if data.get("vat_amount") else None,
        gross_amount=parse_pt_amount(str(data["gross_amount"])) if data.get("gross_amount") else None,
        vat_rate=parse_pt_amount(str(data["vat_rate"])) if data.get("vat_rate") else None,
    )


def _merge_fields(base: ExtractedFields, overlay: ExtractedFields) -> ExtractedFields:
    merged = ExtractedFields()
    for field in (
        "vendor_name",
        "vendor_nif",
        "invoice_number",
        "document_date",
        "net_amount",
        "vat_amount",
        "gross_amount",
        "vat_rate",
    ):
        value = getattr(overlay, field) or getattr(base, field)
        setattr(merged, field, value)
    filled = sum(
        1
        for value in (
            merged.vendor_name,
            merged.vendor_nif,
            merged.document_date,
            merged.gross_amount,
            merged.vat_amount,
        )
        if value is not None
    )
    merged.confidence = min(95.0, max(base.confidence, 20.0 * filled))
    merged.needs_review = merged.confidence < 85 or not merged.vendor_name or not merged.gross_amount
    return merged


_ocr_service: Optional[OCRService] = None


def get_ocr_service() -> OCRService:
    global _ocr_service
    if _ocr_service is None:
        _ocr_service = OCRService()
    return _ocr_service

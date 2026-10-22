"""
OCR backends behind one interface.

Default is open-source:
  auto       → Tesseract if installed, otherwise mock (no keys).
               APP_ENV=production refuses auto and mock at startup.
  tesseract  → Tesseract + PT field extractor (optional local LLM polish)
  mock       → deterministic demo data, no system OCR
  azure      → optional paid Azure Document Intelligence

Azure is never required for a local demo.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import shutil
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from io import BytesIO
from typing import Optional

import httpx
from PIL import Image, ImageFilter, ImageOps

from app.core.config import get_settings
from app.services.ocr_extract import ExtractedFields, extract_fields, extracted_to_json
from app.services.pt_qr import InvoiceQR, read_invoice_qr, read_invoice_qr_from_file

logger = logging.getLogger(__name__)

settings = get_settings()

AZURE_SUPPORTED_FORMATS = {
    "image/jpeg",
    "image/png",
    "image/bmp",
    "image/tiff",
    "application/pdf",
}

CONVERTIBLE_FORMATS = {
    "image/webp",
    "image/heic",
    "image/heif",
    "image/gif",
}


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


class TesseractProbeError(Exception):
    """The tesseract binary crashed, or a language pack did not load."""

    def __init__(self, kind: str):
        self.kind = kind
        super().__init__(kind)


_tesseract_languages: Optional[frozenset[str]] = None
_tesseract_packs_loaded: Optional[bool] = None
_tesseract_pack_failures: list[str] = []
_tesseract_fallback_logged = False
_unknown_backend_logged = False
_KNOWN_OCR_BACKENDS = {"mock", "tesseract", "azure", "auto"}


def tesseract_languages() -> frozenset[str]:
    """Language codes Tesseract reports. Empty when the binary is missing.

    A binary that exits while listing languages raises TesseractProbeError('crash')
    instead of looking like a missing language pack.
    """
    global _tesseract_languages
    if _tesseract_languages is not None:
        return _tesseract_languages
    if not tesseract_available():
        return frozenset()
    try:
        import pytesseract

        listed = pytesseract.get_languages(config="")
    except Exception:
        logger.warning("Tesseract binary failed while listing languages.", exc_info=True)
        raise TesseractProbeError("crash") from None
    _tesseract_languages = frozenset(listed)
    return _tesseract_languages


def probe_tesseract_language(lang: str, tessdata_dir: Optional[str] = None) -> Optional[str]:
    """None when this one pack loads. Otherwise a short reason.

    por and eng are probed separately. Stderr containing
    'Failed loading language' is a failure even when Tesseract exits 0
    after falling back to another pack.
    """
    if not tesseract_available():
        return "the tesseract binary is not installed"
    with tempfile.NamedTemporaryFile(suffix=".png") as image_file:
        Image.new("L", (16, 16), 255).save(image_file.name)
        command = ["tesseract", image_file.name, "stdout", "-l", lang, "--psm", "7"]
        if tessdata_dir:
            command.extend(["--tessdata-dir", tessdata_dir])
        try:
            completed = subprocess.run(command, capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired):
            return f"language pack failed to load (tesseract-ocr-{lang})"
    stderr = completed.stderr or ""
    if "Failed loading language" in stderr or completed.returncode != 0:
        return f"language pack failed to load (tesseract-ocr-{lang})"
    return None


def tesseract_packs_load() -> bool:
    """True when por and eng each load. A fallback from one to the other is a failure."""
    global _tesseract_packs_loaded, _tesseract_pack_failures
    if _tesseract_packs_loaded is not None:
        return _tesseract_packs_loaded
    failures = [lang for lang in ("por", "eng") if probe_tesseract_language(lang)]
    if failures:
        logger.warning(
            "Tesseract language packs failed to load: %s.",
            ", ".join(failures),
        )
    _tesseract_pack_failures = failures
    _tesseract_packs_loaded = not failures
    return _tesseract_packs_loaded


def tesseract_gap() -> Optional[str]:
    """None when por and eng can run. Otherwise a short reason."""
    if not tesseract_available():
        return "the tesseract binary is not installed"
    try:
        languages = tesseract_languages()
    except TesseractProbeError:
        return "the tesseract binary failed to run"
    missing = [lang for lang in ("por", "eng") if lang not in languages]
    if missing:
        packs = ", ".join(f"tesseract-ocr-{lang}" for lang in missing)
        return f"language packs are missing ({packs})"
    if not tesseract_packs_load():
        failed = _tesseract_pack_failures or ["por", "eng"]
        packs = ", ".join(f"tesseract-ocr-{lang}" for lang in failed)
        return f"language packs failed to load ({packs})"
    return None


def tesseract_fallback_message(requested: str) -> str:
    gap = tesseract_gap() or "Tesseract is not ready"
    return (
        f"OCR_BACKEND={requested} fell back to mock because {gap}. "
        "Install tesseract-ocr, tesseract-ocr-por, and tesseract-ocr-eng. "
        "Set OCR_BACKEND=mock to choose mock data on purpose."
    )


def _log_unknown_backend(requested: str) -> None:
    global _unknown_backend_logged
    if _unknown_backend_logged:
        return
    _unknown_backend_logged = True
    logger.error(
        "OCR_BACKEND=%s is not a known backend. Use auto, tesseract, mock, or azure.",
        requested,
    )


def _log_tesseract_fallback(requested: str) -> None:
    global _tesseract_fallback_logged
    if _tesseract_fallback_logged:
        return
    _tesseract_fallback_logged = True
    logger.warning(tesseract_fallback_message(requested))


def _tesseract_or_mock(requested: str) -> str:
    if tesseract_gap() is None:
        return "tesseract"
    _log_tesseract_fallback(requested)
    return "mock"


def resolve_ocr_backend() -> str:
    """Pick a runnable backend. Azure is opt-in only.

    auto uses mock when the binary or the por/eng packs are missing, and logs that once.
    OCR_BACKEND=mock is an explicit choice and does not log a fallback.
    """
    current = get_settings()
    requested = (current.ocr_backend or "auto").strip().lower()
    if requested not in _KNOWN_OCR_BACKENDS:
        _log_unknown_backend(requested)
        return requested
    backend = requested

    if backend == "auto":
        backend = _tesseract_or_mock(requested or "auto")
    if backend == "azure" and (not current.azure_doc_endpoint or not current.azure_doc_key):
        backend = _tesseract_or_mock("azure")
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
        result: Optional[OCRResult] = None
        try:
            if backend == "mock":
                result = self._generate_mock_result(mime_type)
            elif backend == "azure":
                result = await self._process_with_azure(file_content, mime_type)
            elif backend == "tesseract":
                result = await self._process_with_tesseract(file_content, mime_type)
            else:
                return OCRResult(
                    error=f"Unknown OCR backend {backend}",
                    confidence=0,
                    needs_review=True,
                    backend=backend,
                )
            qr = await asyncio.to_thread(_invoice_qr, file_content, mime_type)
        except PdfRasterLimited:
            if result is None:
                result = OCRResult(confidence=0, needs_review=True, backend=backend)
            result.needs_review = True
            result.error = None
            return result
        return _apply_invoice_qr(result, qr) if qr else result

    def _generate_mock_result(self, mime_type: str) -> OCRResult:
        vendors = [
            ("Continente", "500100144"),
            ("Pingo Doce", "500829993"),
            ("Worten", "502428880"),
            ("GALP Energia", "504499777"),
            ("NOS Comunicações", "504448064"),
            # 123456002 is a synthetic placeholder, not verified unissued.
            # Decreto-Lei n.º 14/2013, art. 4.º n.º 2: first digit 1-4 is a pessoa singular, not a company.
            ("Ana Exemplo", "123456002"),
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
        needs_review = True
        if random.random() < 0.1:
            vendor_nif = None
        if random.random() < 0.05:
            doc_date = None

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
        except PdfRasterLimited:
            raise
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
        if fields.gross_amount is None:
            # Crumpled or faded talões often lose the total on the first read.
            retry = await asyncio.to_thread(self._second_read, file_content, mime_type)
            if retry is not None:
                text, fields = retry
        if settings.ollama_base_url:
            llm_fields = await self._extract_with_ollama(text)
            if llm_fields:
                fields = _merge_fields(fields, llm_fields)

        return _fields_to_result(fields, text, backend="tesseract")

    def _second_read(
        self, file_content: bytes, mime_type: str
    ) -> Optional[tuple[str, ExtractedFields]]:
        """
        Re-read a photo that gave no total: boost contrast, binarise, and try
        it rotated. Returns the first read that finds a total, else None, so
        the receipt stays in review rather than getting an invented amount.
        """
        image = _document_image(file_content, mime_type)
        if image is None:
            return None
        for variant, config in _second_read_variants(image):
            text = _image_to_text(variant, config=config)
            fields = extract_fields(text)
            if fields.gross_amount is not None:
                return text, fields
        return None

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

    def _convert_image_to_jpeg(self, file_content: bytes, mime_type: str) -> tuple[bytes, str]:
        """Convert WebP, HEIC, and GIF to JPEG for Azure Document Intelligence."""
        if mime_type in AZURE_SUPPORTED_FORMATS or mime_type not in CONVERTIBLE_FORMATS:
            return file_content, mime_type

        try:
            img = Image.open(BytesIO(file_content))
            if img.mode in ("RGBA", "LA", "P"):
                background = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode == "P":
                    img = img.convert("RGBA")
                background.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
                img = background
            elif img.mode != "RGB":
                img = img.convert("RGB")
            output = BytesIO()
            img.save(output, format="JPEG", quality=95)
            return output.getvalue(), "image/jpeg"
        except Exception as exc:
            logger.warning(f"Image conversion failed: {exc}")
            return file_content, mime_type

    async def _process_with_azure(self, file_content: bytes, mime_type: str) -> OCRResult:
        try:
            file_content, mime_type = self._convert_image_to_jpeg(file_content, mime_type)
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


def _image_to_text(image: Image.Image, config: str = "") -> str:
    import pytesseract

    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    langs = settings.tesseract_lang or "por+eng"
    return pytesseract.image_to_string(image, lang=langs, config=config)


def _document_image(file_content: bytes, mime_type: str) -> Optional[Image.Image]:
    """The photo itself, or a PDF's first page; None for PDFs that can't be rasterised."""
    if (mime_type or "").lower() == "application/pdf" or file_content[:4] == b"%PDF":
        return _pdf_first_page_image(file_content)
    try:
        return Image.open(BytesIO(file_content))
    except Exception:
        return None


def enhance_for_ocr(image: Image.Image) -> Image.Image:
    """Grey, upright, big enough, with the faded ink stretched to full contrast."""
    image = ImageOps.exif_transpose(image).convert("L")
    if image.width < 1400:
        scale = 1400 / image.width
        image = image.resize((1400, int(image.height * scale)), Image.LANCZOS)
    image = ImageOps.autocontrast(image, cutoff=2)
    return image.filter(ImageFilter.MedianFilter(3))


def binarize(image: Image.Image) -> Image.Image:
    """Black ink on white paper, thresholded a little under the mean to keep thin strokes."""
    histogram = image.histogram()
    mean = sum(level * count for level, count in enumerate(histogram)) / max(1, sum(histogram))
    threshold = mean * 0.85
    return image.point(lambda level: 255 if level > threshold else 0)


def _second_read_variants(image: Image.Image):
    """(image, tesseract config) pairs to try, cheapest first."""
    enhanced = enhance_for_ocr(image)
    yield enhanced, ""
    yield enhanced, "--psm 6"  # one uniform block: suits narrow thermal rolls
    yield binarize(enhanced), "--psm 6"
    for angle in (90, 270, 180):
        yield enhanced.rotate(angle, expand=True, fillcolor=255), ""


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


class PdfRasterLimited(Exception):
    """Poppler timed out or the page is over the raster cap."""


_PDF_RASTER_DPI = 200
# Shorter side above this means the page is huge in both dimensions.
# A till roll may be longer than this on one side and still be rendered.
_PDF_RASTER_MAX_SIDE_PT = 2000
_PDF_RASTER_MAX_PIXELS = 25_000_000
_PDF_RASTER_PAGES = 1
_PDF_RASTER_TIMEOUT_SECONDS = 30
# Per process. N uvicorn workers allow 2*N poppler renders at once.
_PDF_RASTER_SLOTS = threading.Semaphore(2)


def _first_page_size_pt(file_content: bytes) -> Optional[tuple[float, float]]:
    try:
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(file_content))
        if not reader.pages:
            return None
        box = reader.pages[0].mediabox
        return abs(float(box.width)), abs(float(box.height))
    except Exception:
        return None


def _raster_dpi(width_pt: float, height_pt: float) -> int:
    width_px = width_pt / 72 * _PDF_RASTER_DPI
    height_px = height_pt / 72 * _PDF_RASTER_DPI
    pixels = width_px * height_px
    if pixels <= _PDF_RASTER_MAX_PIXELS:
        return _PDF_RASTER_DPI
    reduced = int(_PDF_RASTER_DPI * (_PDF_RASTER_MAX_PIXELS / pixels) ** 0.5)
    while reduced > 1:
        width_px = width_pt / 72 * reduced
        height_px = height_pt / 72 * reduced
        if width_px * height_px <= _PDF_RASTER_MAX_PIXELS:
            break
        reduced -= 1
    return max(reduced, 1)


def _pdf_first_page_image(file_content: bytes) -> Optional[Image.Image]:
    size = _first_page_size_pt(file_content)
    if size is not None and min(size) > _PDF_RASTER_MAX_SIDE_PT:
        raise PdfRasterLimited("page exceeds the raster cap")
    dpi = _raster_dpi(*size) if size is not None else _PDF_RASTER_DPI
    try:
        from pdf2image import convert_from_bytes
        from pdf2image.exceptions import PDFInfoNotInstalledError, PDFPopplerTimeoutError
    except ImportError:
        logger.warning(
            "PDF QR read skipped: pdf2image is not installed. "
            "Pin it in requirements.txt."
        )
        return None
    try:
        with _PDF_RASTER_SLOTS:
            images = convert_from_bytes(
                file_content,
                dpi=dpi,
                first_page=1,
                last_page=_PDF_RASTER_PAGES,
                timeout=_PDF_RASTER_TIMEOUT_SECONDS,
            )
        return images[0] if images else None
    except PDFPopplerTimeoutError as exc:
        raise PdfRasterLimited("poppler timed out") from exc
    except PDFInfoNotInstalledError:
        logger.warning(
            "PDF QR read skipped: poppler-utils is not installed. "
            "The backend image pins that package."
        )
        return None
    except Exception:
        return None


def _invoice_qr(file_content: bytes, mime_type: str) -> Optional[InvoiceQR]:
    if (mime_type or "").lower() == "application/pdf" or file_content[:4] == b"%PDF":
        image = _pdf_first_page_image(file_content)
        return read_invoice_qr(image) if image is not None else None
    return read_invoice_qr_from_file(file_content, mime_type, _pdf_first_page_image)


def _apply_invoice_qr(result: OCRResult, qr: InvoiceQR) -> OCRResult:
    """The AT QR's NIF, date, number and amounts replace what OCR read; OCR keeps the vendor name."""
    result.vendor_nif = qr.vendor_nif
    result.document_date = qr.document_date or result.document_date
    result.invoice_number = qr.invoice_number or result.invoice_number
    result.net_amount = qr.net_amount if qr.net_amount is not None else result.net_amount
    result.vat_amount = qr.vat_amount if qr.vat_amount is not None else result.vat_amount
    result.gross_amount = qr.gross_amount
    result.vat_rate = qr.vat_rate
    result.error = None
    result.confidence = max(result.confidence, 95.0)
    # Everything but the vendor name came from the issuer, so only a missing
    # name still needs a person.
    result.needs_review = not result.vendor_name
    if result.backend == "mock":
        result.needs_review = True

    try:
        raw = json.loads(result.raw_response) if result.raw_response else {}
        if not isinstance(raw, dict):
            raw = {"ocr": raw}
    except ValueError:
        raw = {"ocr": result.raw_response}
    if result.backend == "mock":
        raw["mock"] = True
    raw["qr"] = {
        "payload": qr.payload,
        "atcud": qr.atcud,
        "vat_breakdown": qr.breakdown,
        "document_type": qr.document_type,
        "fiscal_status": qr.fiscal_status,
    }
    result.raw_response = json.dumps(raw, ensure_ascii=False)
    return result


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
        raw_response=extracted_to_json(
            fields,
            extra={
                "backend": backend,
                "text": text[:4000],
                **({"document_type": fields.document_type} if fields.document_type else {}),
            },
        ),
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


def ocr_runtime_status() -> dict:
    from app.core.config import app_env_name

    current = get_settings()
    requested = (current.ocr_backend or "auto").strip().lower()
    ready = tesseract_gap() is None
    backend = resolve_ocr_backend()
    unknown = requested not in _KNOWN_OCR_BACKENDS
    production_mock = app_env_name(current.app_env) == "production" and backend == "mock"
    degraded = (requested == "tesseract" and not ready) or unknown or production_mock
    return {
        "status": "degraded" if degraded else "healthy",
        "ocr_backend": backend,
        "tesseract": ready,
    }


def get_ocr_service() -> OCRService:
    global _ocr_service
    if _ocr_service is None:
        _ocr_service = OCRService()
    return _ocr_service

"""
OCR service using Mindee for receipt/invoice processing.
Includes mock mode for development without API credentials.
"""

import io
import json
import random
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from dataclasses import dataclass
from app.core.config import get_settings

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


class OCRService:
    """
    Handles OCR processing for receipts and invoices.
    Uses Mindee in production, mock data in development.
    """
    
    def __init__(self):
        self.mock_mode = settings.ocr_mock_mode
        self.api_key = settings.mindee_api_key
        self._client = None
    
    def _get_client(self):
        """Lazy initialization of Mindee client."""
        if self._client is None and not self.mock_mode:
            from mindee import Client
            self._client = Client(api_key=self.api_key)
        return self._client
    
    async def process_document(self, file_content: bytes, mime_type: str) -> OCRResult:
        """
        Process a document and extract relevant fields.
        """
        if self.mock_mode:
            return self._generate_mock_result(mime_type)
        
        return await self._process_with_mindee(file_content, mime_type)
    
    def _generate_mock_result(self, mime_type: str) -> OCRResult:
        """Generate realistic mock OCR data for testing."""
        
        # Sample Portuguese vendors
        vendors = [
            ("Continente", "500100144"),
            ("Pingo Doce", "500829993"),
            ("Worten", "502428880"),
            ("GALP Energia", "504499777"),
            ("NOS Comunicações", "504448064"),
            ("EDP Comercial", "503504564"),
            ("Uber Portugal", "514aborado"),  # intentionally bad NIF for testing
            ("Bolt Technology", None),
            ("Restaurante O Manel", "123456789"),
            ("Papelaria Central", "987654321"),
        ]
        
        vendor_name, vendor_nif = random.choice(vendors)
        
        # Random amounts
        gross = Decimal(str(round(random.uniform(5.0, 250.0), 2)))
        vat_rate = Decimal(random.choice(["6.00", "13.00", "23.00"]))
        vat = (gross * vat_rate / (100 + vat_rate)).quantize(Decimal("0.01"))
        net = gross - vat
        
        # Random date in the last 30 days
        days_ago = random.randint(0, 30)
        doc_date = date.today() - __import__("datetime").timedelta(days=days_ago)
        
        # Simulate confidence (most are good, some need review)
        confidence = random.uniform(0.7, 0.99)
        needs_review = confidence < 0.85 or random.random() < 0.15
        
        # Sometimes simulate missing data
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
            raw_response=json.dumps({"mock": True, "vendor": vendor_name}),
            needs_review=needs_review,
        )
    
    async def _process_with_mindee(self, file_content: bytes, mime_type: str) -> OCRResult:
        """Process document using Mindee Receipt API."""
        
        try:
            from mindee import Client, product
            
            client = self._get_client()
            
            # Determine filename extension from mime type
            ext_map = {
                "image/jpeg": "receipt.jpg",
                "image/png": "receipt.png",
                "image/heic": "receipt.heic",
                "application/pdf": "receipt.pdf",
            }
            filename = ext_map.get(mime_type, "receipt.jpg")
            
            # Create input source from bytes using the new SDK API
            input_source = Client.source_from_bytes(file_content, filename)
            
            # Parse with Mindee Receipt API
            result = client.parse(product.ReceiptV5, input_source)
            
            return self._parse_mindee_result(result)
            
        except Exception as e:
            return OCRResult(
                error=f"OCR processing error: {str(e)}",
                confidence=0,
                needs_review=True,
            )
    
    def _parse_mindee_result(self, result) -> OCRResult:
        """Parse Mindee Receipt response."""
        
        try:
            prediction = result.document.inference.prediction
            
            # Extract vendor name
            vendor_name = None
            if prediction.supplier_name.value:
                vendor_name = prediction.supplier_name.value
            
            # Extract date
            doc_date = None
            if prediction.date.value:
                doc_date = prediction.date.value
            
            # Extract amounts
            gross_amount = None
            if prediction.total_amount.value is not None:
                gross_amount = Decimal(str(prediction.total_amount.value))
            
            net_amount = None
            if prediction.total_net.value is not None:
                net_amount = Decimal(str(prediction.total_net.value))
            
            vat_amount = None
            if prediction.total_tax.value is not None:
                vat_amount = Decimal(str(prediction.total_tax.value))
            
            # Calculate net if we have gross and VAT but no net
            if net_amount is None and gross_amount and vat_amount:
                net_amount = gross_amount - vat_amount
            
            # Extract VAT rate from taxes array
            vat_rate = None
            if prediction.taxes and len(prediction.taxes) > 0:
                first_tax = prediction.taxes[0]
                if hasattr(first_tax, 'rate') and first_tax.rate is not None:
                    vat_rate = Decimal(str(first_tax.rate))
            
            # Try to extract Portuguese NIF from raw text
            vendor_nif = self._extract_portuguese_nif(str(result.document))
            
            # Calculate confidence based on available fields
            confidence_factors = []
            if vendor_name:
                confidence_factors.append(0.9)
            if gross_amount:
                confidence_factors.append(0.95)
            if doc_date:
                confidence_factors.append(0.9)
            if vat_amount:
                confidence_factors.append(0.85)
            
            if confidence_factors:
                confidence = (sum(confidence_factors) / len(confidence_factors)) * 100
            else:
                confidence = 30.0
            
            # Determine if review is needed
            needs_review = (
                confidence < 75 or
                not vendor_name or
                not gross_amount or
                not doc_date
            )
            
            return OCRResult(
                vendor_name=vendor_name,
                vendor_nif=vendor_nif,
                invoice_number=None,  # Mindee Receipt doesn't extract invoice numbers
                document_date=doc_date,
                net_amount=net_amount,
                vat_amount=vat_amount,
                gross_amount=gross_amount,
                vat_rate=vat_rate,
                confidence=confidence,
                raw_response=str(result.document),
                needs_review=needs_review,
            )
            
        except Exception as e:
            return OCRResult(
                error=f"Error parsing Mindee response: {str(e)}",
                confidence=0,
                needs_review=True,
                raw_response=str(result) if result else None,
            )
    
    def _extract_portuguese_nif(self, text: str) -> Optional[str]:
        """
        Extract Portuguese NIF (Número de Identificação Fiscal) from text.
        NIFs are 9-digit numbers, often prefixed with 'NIF', 'NIPC', or 'Contribuinte'.
        """
        if not text:
            return None
        
        # Patterns to look for NIF
        patterns = [
            r'(?:NIF|NIPC|N\.I\.F\.|Contribuinte)[:\s]*(\d{9})',  # With label
            r'(?:PT)?(\d{9})(?:\s|$)',  # Just 9 digits (possibly with PT prefix)
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                nif = match.group(1)
                # Basic validation: Portuguese NIFs start with 1,2,3,5,6,7,8,9
                if nif[0] in '123456789':
                    return nif
        
        return None


# Singleton instance
_ocr_service: Optional[OCRService] = None


def get_ocr_service() -> OCRService:
    """Get the OCR service singleton."""
    global _ocr_service
    if _ocr_service is None:
        _ocr_service = OCRService()
    return _ocr_service

"""
OCR service using Azure Document Intelligence.
Includes mock mode for development without Azure credentials.
"""

import asyncio
import json
import random
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from dataclasses import dataclass
import httpx
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
    Uses Azure Document Intelligence in production, mock data in development.
    """
    
    def __init__(self):
        self.mock_mode = settings.ocr_mock_mode
        self.endpoint = settings.azure_doc_endpoint
        self.api_key = settings.azure_doc_key
    
    async def process_document(self, file_content: bytes, mime_type: str) -> OCRResult:
        """
        Process a document and extract relevant fields.
        """
        if self.mock_mode:
            return self._generate_mock_result(mime_type)
        
        return await self._process_with_azure(file_content, mime_type)
    
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
    
    async def _process_with_azure(self, file_content: bytes, mime_type: str) -> OCRResult:
        """Process document using Azure Document Intelligence."""
        
        try:
            # Use prebuilt-receipt model for receipts
            model_id = "prebuilt-receipt"
            
            # Call Azure Document Intelligence
            async with httpx.AsyncClient(timeout=60.0) as client:
                # Start analysis
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
                    )
                
                # Get the operation location for polling
                operation_location = response.headers.get("Operation-Location")
                
                if not operation_location:
                    return OCRResult(
                        error="Azure API did not return operation location",
                        confidence=0,
                        needs_review=True,
                    )
                
                # Poll for results
                for _ in range(30):  # Max 30 attempts
                    await asyncio.sleep(1)
                    
                    result_response = await client.get(
                        operation_location,
                        headers={"Ocp-Apim-Subscription-Key": self.api_key},
                    )
                    
                    result_data = result_response.json()
                    status = result_data.get("status")
                    
                    if status == "succeeded":
                        return self._parse_azure_result(result_data)
                    elif status == "failed":
                        return OCRResult(
                            error="Azure processing failed",
                            confidence=0,
                            needs_review=True,
                            raw_response=json.dumps(result_data),
                        )
                
                return OCRResult(
                    error="Azure processing timeout",
                    confidence=0,
                    needs_review=True,
                )
                
        except Exception as e:
            return OCRResult(
                error=f"OCR processing error: {str(e)}",
                confidence=0,
                needs_review=True,
            )
    
    def _parse_azure_result(self, result_data: dict) -> OCRResult:
        """Parse Azure Document Intelligence response."""
        
        try:
            analyze_result = result_data.get("analyzeResult", {})
            documents = analyze_result.get("documents", [])
            
            if not documents:
                return OCRResult(
                    error="No document found in response",
                    confidence=0,
                    needs_review=True,
                    raw_response=json.dumps(result_data),
                )
            
            doc = documents[0]
            fields = doc.get("fields", {})
            confidence = doc.get("confidence", 0) * 100
            
            # Extract fields
            vendor_name = self._get_field_value(fields, "MerchantName")
            invoice_number = self._get_field_value(fields, "TransactionId")
            
            # Try to extract NIF from merchant address or phone field
            vendor_nif = None
            merchant_address = self._get_field_value(fields, "MerchantAddress")
            if merchant_address:
                vendor_nif = self._extract_portuguese_nif(merchant_address)
            
            # Also check raw content for NIF
            if not vendor_nif:
                content = analyze_result.get("content", "")
                vendor_nif = self._extract_portuguese_nif(content)
            
            # Parse date
            doc_date = None
            date_str = self._get_field_value(fields, "TransactionDate")
            if date_str:
                try:
                    doc_date = datetime.fromisoformat(date_str.replace("Z", "")).date()
                except ValueError:
                    pass
            
            # Parse amounts
            gross_amount = self._get_currency_value(fields, "Total")
            vat_amount = self._get_currency_value(fields, "TotalTax")
            net_amount = None
            
            if gross_amount and vat_amount:
                net_amount = gross_amount - vat_amount
            
            # Calculate VAT rate if possible
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
            )
            
        except Exception as e:
            return OCRResult(
                error=f"Error parsing Azure response: {str(e)}",
                confidence=0,
                needs_review=True,
                raw_response=json.dumps(result_data),
            )
    
    def _get_field_value(self, fields: dict, field_name: str) -> Optional[str]:
        """Extract string value from Azure field."""
        field = fields.get(field_name, {})
        return field.get("valueString") or field.get("content")
    
    def _get_currency_value(self, fields: dict, field_name: str) -> Optional[Decimal]:
        """Extract currency value from Azure field."""
        field = fields.get(field_name, {})
        value = field.get("valueCurrency", {}).get("amount")
        if value is not None:
            return Decimal(str(value))
        # Try parsing from content
        content = field.get("content", "")
        if content:
            try:
                # Remove currency symbols and parse
                cleaned = "".join(c for c in content if c.isdigit() or c in ".,")
                cleaned = cleaned.replace(",", ".")
                return Decimal(cleaned)
            except Exception:
                pass
        return None
    
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

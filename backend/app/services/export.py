"""
Export service for generating accountant-ready packages.
Creates ZIP archives with original documents and summary files.
"""

import io
import csv
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional
from decimal import Decimal
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from sqlalchemy.orm import Session

from app.models.document import Document
from app.services.storage import get_storage_service
from app.services.categorization import (
    get_expense_category_label,
    get_irs_sector_label,
    get_deductible_pct,
    deductible_vat_split,
    effective_deductible_pct,
)


# A cell starting with one of these runs as a formula in Excel/LibreOffice.
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _csv_text(value: Optional[str]) -> str:
    """OCR'd text, neutralised so it can't run as a spreadsheet formula."""
    if not value:
        return ""
    return f"'{value}" if value.startswith(_FORMULA_PREFIXES) else value


def _csv_amount(value: Optional[Decimal]) -> str:
    """12.50 -> "12,50" so pt-PT spreadsheets read it as a number."""
    return "" if value is None else f"{value:.2f}".replace(".", ",")


STATUS_LABELS = {
    "ready": "Pronto",
    "needs_review": "Por rever",
    "accountant_review": "Contabilista",
    "processing": "A processar",
    "pending": "Pendente",
    "failed": "Falhou",
}


def _pdf_eur(value: Decimal) -> str:
    """1234.5 -> "1.234,50 €" (pt-PT)."""
    whole, cents = f"{value:,.2f}".split(".")
    return f"{whole.replace(',', '.')},{cents} €"


class ExportService:
    """
    Generates export packages for accountants.
    Includes original files, summary PDF, and CSV.
    """
    
    def __init__(self):
        self.storage = get_storage_service()
    
    def generate_export(
        self,
        db: Session,
        user_id: str,
        documents: list[Document],
        period: str,
    ) -> tuple[bytes, str]:
        """
        Generate a ZIP export package.
        Returns (zip_bytes, filename).
        """
        
        # Create ZIP in memory
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            # Add original files
            for doc in documents:
                file_content = self._get_file_content(doc.storage_key)
                if file_content:
                    # Organize by month
                    month_folder = doc.period_tag
                    safe_vendor = self._safe_filename(doc.vendor_name or "unknown")
                    doc_id_short = str(doc.id)[:8] if doc.id else "unknown"
                    filename = f"{doc.document_date or 'nodate'}_{safe_vendor}_{doc_id_short}"
                    ext = Path(doc.original_filename).suffix or ".jpg"
                    
                    zf.writestr(f"receipts/{month_folder}/{filename}{ext}", file_content)
            
            # Generate and add summary CSV
            csv_content = self._generate_csv(documents)
            zf.writestr("summary.csv", csv_content)
            
            # Generate and add summary PDF
            pdf_content = self._generate_pdf(documents, period)
            zf.writestr("summary.pdf", pdf_content)
        
        zip_buffer.seek(0)
        zip_bytes = zip_buffer.getvalue()
        
        # Generate filename
        safe_period = period.replace("-", "_")
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"FaturaFlow_Export_{safe_period}_{timestamp}.zip"
        
        return zip_bytes, filename
    
    def _get_file_content(self, storage_key: str) -> Optional[bytes]:
        """Get file content from storage (local files in mock mode, R2 otherwise)."""
        return self.storage.get_file(storage_key)
    
    def _safe_filename(self, name: str) -> str:
        """Convert string to safe filename."""
        return "".join(c if c.isalnum() or c in "-_" else "_" for c in name)[:50]
    
    def _generate_csv(self, documents: list[Document]) -> str:
        """CSV summary for Portuguese Excel: ';' separated, comma decimals, UTF-8 BOM."""
        output = io.StringIO()
        output.write("\ufeff")
        writer = csv.writer(output, delimiter=";")
        
        # Header
        writer.writerow([
            "ID",
            "Date",
            "Vendor",
            "NIF",
            "Invoice #",
            "Net (EUR)",
            "VAT (EUR)",
            "Gross (EUR)",
            "VAT %",
            "Category",
            "IRS Sector",
            "Deductible %",
            "Deductible VAT (EUR)",
            "Status",
            "Filename",
        ])
        
        # Data rows
        for doc in documents:
            cat = doc.expense_category or "other"
            pct = effective_deductible_pct(doc)
            vat = doc.vat_amount or Decimal(0)
            deductible = (vat * pct / 100).quantize(Decimal("0.01"))
            writer.writerow([
                str(doc.id),
                doc.document_date.isoformat() if doc.document_date else "",
                _csv_text(doc.vendor_name),
                _csv_text(doc.vendor_nif),
                _csv_text(doc.invoice_number),
                _csv_amount(doc.net_amount),
                _csv_amount(doc.vat_amount),
                _csv_amount(doc.gross_amount),
                _csv_amount(doc.vat_rate),
                get_expense_category_label(cat),
                get_irs_sector_label(doc.irs_sector or "geral"),
                f"{pct}%",
                _csv_amount(deductible),
                doc.status,
                _csv_text(doc.original_filename),
            ])
        
        return output.getvalue()
    
    def _generate_pdf(self, documents: list[Document], period: str) -> bytes:
        """Generate PDF summary."""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=2*cm, bottomMargin=2*cm)
        
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=18,
            spaceAfter=20,
        )
        
        elements = []
        
        # Title
        elements.append(Paragraph(f"FaturaFlow — pacote contabilista — {period}", title_style))
        elements.append(Spacer(1, 12))
        
        # Generation info
        elements.append(Paragraph(
            f"Gerado em: {datetime.utcnow().strftime('%d/%m/%Y %H:%M UTC')}",
            styles['Normal']
        ))
        elements.append(Paragraph(f"Total de documentos: {len(documents)}", styles['Normal']))
        elements.append(Spacer(1, 20))
        
        # Calculate totals with per-category deductible
        total_gross = sum(d.gross_amount or Decimal(0) for d in documents)
        total_vat = sum(d.vat_amount or Decimal(0) for d in documents)
        total_net = sum(d.net_amount or Decimal(0) for d in documents)
        deductible_vat, deductible_vat_pending = deductible_vat_split(documents)
        
        # Summary table
        elements.append(Paragraph("Resumo", styles['Heading2']))
        summary_data = [
            ["Descrição", "Valor (EUR)"],
            ["Total bruto", _pdf_eur(total_gross)],
            ["Total líquido", _pdf_eur(total_net)],
            ["IVA total", _pdf_eur(total_vat)],
            ["IVA dedutível (recibos revistos)", _pdf_eur(deductible_vat)],
            ["IVA dedutível (recibos por rever)", _pdf_eur(deductible_vat_pending)],
        ]
        
        summary_table = Table(summary_data, colWidths=[10*cm, 5*cm])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))
        elements.append(summary_table)
        elements.append(Spacer(1, 30))
        
        # Document list (truncated if too many)
        elements.append(Paragraph("Documentos", styles['Heading2']))
        
        doc_data = [["Data", "Fornecedor", "Categoria", "Bruto", "IVA", "Estado"]]
        for d in documents[:50]:  # Limit to 50 for PDF readability
            doc_data.append([
                d.document_date.strftime("%d/%m/%Y") if d.document_date else "-",
                (d.vendor_name or "Desconhecido")[:25],
                get_expense_category_label(d.expense_category or "other")[:15],
                _pdf_eur(d.gross_amount) if d.gross_amount else "-",
                _pdf_eur(d.vat_amount) if d.vat_amount else "-",
                STATUS_LABELS.get(d.status, d.status),
            ])
        
        if len(documents) > 50:
            doc_data.append(["...", f"+ {len(documents) - 50} mais", "", "", "", ""])
        
        doc_table = Table(doc_data, colWidths=[2*cm, 5*cm, 2.5*cm, 2*cm, 2*cm, 2*cm])
        doc_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('ALIGN', (2, 0), (3, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
        ]))
        elements.append(doc_table)
        
        # Build PDF
        doc.build(elements)
        buffer.seek(0)
        return buffer.getvalue()


# Singleton instance
_export_service: Optional[ExportService] = None


def get_export_service() -> ExportService:
    """Get the export service singleton."""
    global _export_service
    if _export_service is None:
        _export_service = ExportService()
    return _export_service

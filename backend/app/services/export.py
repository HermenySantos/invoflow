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
        filename = f"InvoFlow_Export_{safe_period}_{timestamp}.zip"
        
        return zip_bytes, filename
    
    def _get_file_content(self, storage_key: str) -> Optional[bytes]:
        """Get file content from storage."""
        if self.storage.mock_mode:
            return self.storage.get_file_mock(storage_key)
        
        # For R2, we'd need to download the file
        # This is a simplified version - in production you'd use boto3
        return None
    
    def _safe_filename(self, name: str) -> str:
        """Convert string to safe filename."""
        return "".join(c if c.isalnum() or c in "-_" else "_" for c in name)[:50]
    
    def _generate_csv(self, documents: list[Document]) -> str:
        """Generate CSV summary."""
        output = io.StringIO()
        writer = csv.writer(output)
        
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
            "Status",
            "Filename",
        ])
        
        # Data rows
        for doc in documents:
            writer.writerow([
                str(doc.id),
                doc.document_date.isoformat() if doc.document_date else "",
                doc.vendor_name or "",
                doc.vendor_nif or "",
                doc.invoice_number or "",
                str(doc.net_amount) if doc.net_amount else "",
                str(doc.vat_amount) if doc.vat_amount else "",
                str(doc.gross_amount) if doc.gross_amount else "",
                str(doc.vat_rate) if doc.vat_rate else "",
                doc.status,
                doc.original_filename,
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
        elements.append(Paragraph(f"InvoFlow Export - {period}", title_style))
        elements.append(Spacer(1, 12))
        
        # Generation info
        elements.append(Paragraph(
            f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
            styles['Normal']
        ))
        elements.append(Paragraph(f"Total documents: {len(documents)}", styles['Normal']))
        elements.append(Spacer(1, 20))
        
        # Calculate totals
        total_gross = sum(d.gross_amount or Decimal(0) for d in documents)
        total_vat = sum(d.vat_amount or Decimal(0) for d in documents)
        total_net = sum(d.net_amount or Decimal(0) for d in documents)
        
        # Summary table
        elements.append(Paragraph("Summary", styles['Heading2']))
        summary_data = [
            ["Description", "Amount (EUR)"],
            ["Total Gross", f"€{total_gross:,.2f}"],
            ["Total Net", f"€{total_net:,.2f}"],
            ["Total VAT", f"€{total_vat:,.2f}"],
            ["Deductible VAT (100%)", f"€{total_vat:,.2f}"],
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
        elements.append(Paragraph("Documents", styles['Heading2']))
        
        doc_data = [["Date", "Vendor", "Gross", "VAT", "Status"]]
        for d in documents[:50]:  # Limit to 50 for PDF readability
            doc_data.append([
                d.document_date.strftime("%Y-%m-%d") if d.document_date else "-",
                (d.vendor_name or "Unknown")[:30],
                f"€{d.gross_amount:,.2f}" if d.gross_amount else "-",
                f"€{d.vat_amount:,.2f}" if d.vat_amount else "-",
                d.status,
            ])
        
        if len(documents) > 50:
            doc_data.append(["...", f"+ {len(documents) - 50} more", "", "", ""])
        
        doc_table = Table(doc_data, colWidths=[2.5*cm, 6*cm, 2.5*cm, 2.5*cm, 2.5*cm])
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

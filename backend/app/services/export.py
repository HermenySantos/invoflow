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
from app.services.iva_adjust import contributions, credit_note_warnings


# A cell starting with one of these runs as a formula in Excel/LibreOffice.
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
_RECEIPT_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".pdf",
    ".bmp", ".tif", ".tiff", ".heic", ".heif",
}


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
        
        counted = contributions(documents)
        warnings = credit_note_warnings(documents, self._library(db, user_id, documents))
        counted_ids = {id(row.document) for row in counted}
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for doc in documents:
                if id(doc) not in counted_ids:
                    continue
                file_content = self._get_file_content(doc.storage_key)
                if file_content:
                    zf.writestr(self._receipt_entry(doc), file_content)
            
            # Generate and add summary CSV
            csv_content = self._generate_csv(documents, warnings)
            zf.writestr("summary.csv", csv_content)
            
            # Generate and add summary PDF
            pdf_content = self._generate_pdf(documents, period, warnings)
            zf.writestr("summary.pdf", pdf_content)
        
        zip_buffer.seek(0)
        zip_bytes = zip_buffer.getvalue()
        
        # Generate filename
        safe_period = period.replace("-", "_")
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"Invoflow_Export_{safe_period}_{timestamp}.zip"
        
        return zip_bytes, filename
    
    def _get_file_content(self, storage_key: str) -> Optional[bytes]:
        """Get file content from storage (local files in mock mode, R2 otherwise)."""
        return self.storage.get_file(storage_key)
    
    def _safe_filename(self, name: str) -> str:
        """Convert string to safe filename."""
        return "".join(c if c.isalnum() or c in "-_" else "_" for c in name)[:50]

    def _library(self, db: Optional[Session], user_id: str, documents: list[Document]) -> list[Document]:
        if db is None:
            return documents
        return (
            db.query(Document)
            .filter(Document.deleted_at.is_(None))
            .filter(Document.user_id == user_id)
            .filter(Document.status.in_(("ready", "needs_review", "accountant_review")))
            .all()
        )

    def _receipt_entry(self, doc: Document) -> str:
        """Zip path with no directory parts from the uploaded name, and a known extension."""
        raw_month = doc.period_tag if doc.document_date or doc.created_at else "undated"
        month = "".join(ch for ch in str(raw_month) if ch.isdigit() or ch == "-") or "undated"
        vendor = self._safe_filename(doc.vendor_name or "unknown")
        short = str(doc.id)[:8] if doc.id else "unknown"
        when = doc.document_date.isoformat() if doc.document_date else "nodate"
        uploaded = str(doc.original_filename or "").replace("\\", "/")
        suffix = Path(uploaded).suffix.lower()
        ext = suffix if suffix in _RECEIPT_EXTENSIONS else ".bin"
        leaf = f"{when}_{vendor}_{short}{ext}".replace("\\", "").replace("..", "")
        return f"receipts/{month}/{leaf}"

    def _generate_csv(self, documents: list[Document], warnings: Optional[list[str]] = None) -> str:
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
        
        counted = contributions(documents)
        for row in counted:
            doc = row.document
            cat = doc.expense_category or "other"
            pct = effective_deductible_pct(doc)
            vat = row.vat
            deductible = (vat * pct / 100).quantize(Decimal("0.01"))
            writer.writerow([
                str(doc.id),
                doc.document_date.isoformat() if doc.document_date else "",
                _csv_text(doc.vendor_name),
                _csv_text(doc.vendor_nif),
                _csv_text(doc.invoice_number),
                _csv_amount(row.net),
                _csv_amount(row.vat),
                _csv_amount(row.gross),
                _csv_amount(doc.vat_rate),
                get_expense_category_label(cat),
                get_irs_sector_label(doc.irs_sector or "geral"),
                f"{pct}%",
                _csv_amount(deductible),
                doc.status,
                _csv_text(doc.original_filename),
            ])

        if counted:
            writer.writerow([
                "Total",
                "",
                "",
                "",
                "",
                _csv_amount(sum((row.net for row in counted), Decimal(0))),
                _csv_amount(sum((row.vat for row in counted), Decimal(0))),
                _csv_amount(sum((row.gross for row in counted), Decimal(0))),
            ])

        for warning in warnings or []:
            writer.writerow(["Avisos", warning])
        
        return output.getvalue()
    
    def _generate_pdf(self, documents: list[Document], period: str, warnings: Optional[list[str]] = None) -> bytes:
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
        elements.append(Paragraph(f"Invoflow — pacote contabilista — {period}", title_style))
        elements.append(Spacer(1, 12))
        
        # Generation info
        elements.append(Paragraph(
            f"Gerado em: {datetime.utcnow().strftime('%d/%m/%Y %H:%M UTC')}",
            styles['Normal']
        ))
        counted = contributions(documents)
        elements.append(Paragraph(f"Total de documentos: {len(counted)}", styles['Normal']))
        elements.append(Spacer(1, 20))
        total_gross = sum((row.gross for row in counted), Decimal(0))
        total_vat = sum((row.vat for row in counted), Decimal(0))
        total_net = sum((row.net for row in counted), Decimal(0))
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
        for row in counted[:50]:
            d = row.document
            doc_data.append([
                d.document_date.strftime("%d/%m/%Y") if d.document_date else "-",
                (d.vendor_name or "Desconhecido")[:25],
                get_expense_category_label(d.expense_category or "other")[:15],
                _pdf_eur(row.gross),
                _pdf_eur(row.vat),
                STATUS_LABELS.get(d.status, d.status),
            ])
        
        if len(counted) > 50:
            doc_data.append(["...", f"+ {len(counted) - 50} mais", "", "", "", ""])
        
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
        if warnings:
            elements.append(Spacer(1, 16))
            elements.append(Paragraph("Avisos", styles["Heading2"]))
            for warning in warnings:
                safe = warning.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                elements.append(Paragraph(safe, styles["Normal"]))
        
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

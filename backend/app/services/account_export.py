"""
Whole-account data export: every document row, VAT-on-sales entry and stored
receipt file that belongs to one user, in a single ZIP.

Unlike the accountant pack (export.py) nothing is filtered by period, status or
IVA rules, and deleted receipts are included and marked as such.
"""

import csv
import io
import json
import zipfile
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.user import User
from app.models.vat_sales import VatSalesEntry
from app.services.export import _RECEIPT_EXTENSIONS, _csv_amount, _csv_text
from app.services.storage import get_storage_service

README = """Invoflow — exportação dos seus dados

Este arquivo contém os dados associados à sua conta Invoflow na data indicada em conta.json.

conta.json         Email da conta, data de criação e data desta exportação.
documentos.json    Todos os documentos (recibos e faturas), com todos os campos guardados.
documentos.csv     Os campos principais dos mesmos documentos, para abrir numa folha de cálculo.
iva_vendas.json    Os valores de IVA das vendas que introduziu, por período.
iva_vendas.csv     Os mesmos valores, para abrir numa folha de cálculo.
ficheiros/         Os ficheiros originais dos recibos que carregou, um por documento.

Os documentos que eliminou na aplicação também estão incluídos, com a data de eliminação preenchida.
Os ficheiros CSV usam ";" como separador e vírgula nas casas decimais.
"""

# Rows only keep the owner link and the storage location internally; the file itself is in ficheiros/.
_DOCUMENT_INTERNAL = {"user_id", "storage_key"}
_VAT_INTERNAL = {"user_id"}


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _row(obj, skip: set[str]) -> dict[str, Any]:
    return {
        column.key: _json_value(getattr(obj, column.key))
        for column in obj.__table__.columns
        if column.key not in skip
    }


def _iso(value: Optional[date]) -> str:
    return value.isoformat() if value else ""


class AccountExportService:
    def __init__(self):
        self.storage = get_storage_service()

    def build(self, db: Session, user: User) -> tuple[bytes, str]:
        documents = (
            db.query(Document)
            .filter(Document.user_id == user.id)
            .order_by(Document.created_at, Document.id)
            .all()
        )
        vat_entries = (
            db.query(VatSalesEntry)
            .filter(VatSalesEntry.user_id == user.id)
            .order_by(VatSalesEntry.year, VatSalesEntry.period_type, VatSalesEntry.period_value)
            .all()
        )
        now = datetime.utcnow()

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            files: dict[str, Optional[str]] = {}
            for doc in documents:
                entry = self._file_entry(doc)
                content = self._owned_file(doc, user)
                if content is None:
                    files[doc.id] = None
                    continue
                zf.writestr(entry, content)
                files[doc.id] = entry

            document_rows = [{**_row(doc, _DOCUMENT_INTERNAL), "ficheiro": files[doc.id]} for doc in documents]
            vat_rows = [_row(entry, _VAT_INTERNAL) for entry in vat_entries]
            account = {
                "email": user.email,
                "conta_criada_em": _json_value(user.created_at),
                "exportado_em": now.isoformat(timespec="seconds"),
                "documentos": len(document_rows),
                "ficheiros": sum(1 for path in files.values() if path),
                "registos_iva_vendas": len(vat_rows),
            }

            zf.writestr("LEIA-ME.txt", README)
            zf.writestr("conta.json", self._json(account))
            zf.writestr("documentos.json", self._json(document_rows))
            zf.writestr("documentos.csv", self._documents_csv(documents, files))
            zf.writestr("iva_vendas.json", self._json(vat_rows))
            zf.writestr("iva_vendas.csv", self._vat_csv(vat_entries))

        filename = f"Invoflow_meus_dados_{now.strftime('%Y%m%d_%H%M%S')}.zip"
        return buffer.getvalue(), filename

    def _owned_file(self, doc: Document, user: User) -> Optional[bytes]:
        # Upload keys are issued under the owner's folder. A row pointing anywhere
        # else must not pull another account's file into this archive.
        key = doc.storage_key or ""
        if not key.startswith(f"{user.clerk_id}/") or any(part == ".." for part in key.split("/")):
            return None
        return self.storage.get_file(key)

    @staticmethod
    def _file_entry(doc: Document) -> str:
        suffix = Path(str(doc.original_filename or "").replace("\\", "/")).suffix.lower()
        ext = suffix if suffix in _RECEIPT_EXTENSIONS else ".bin"
        return f"ficheiros/{doc.id}{ext}"

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, indent=2)

    @staticmethod
    def _documents_csv(documents: list[Document], files: dict[str, Optional[str]]) -> str:
        output = io.StringIO()
        output.write("\ufeff")
        writer = csv.writer(output, delimiter=";")
        writer.writerow([
            "ID",
            "Data",
            "Fornecedor",
            "NIF",
            "N.º da fatura",
            "Tipo",
            "Líquido (EUR)",
            "IVA (EUR)",
            "Bruto (EUR)",
            "IVA %",
            "Categoria",
            "Estado",
            "Notas",
            "Nome do ficheiro carregado",
            "Ficheiro no arquivo",
            "Criado em",
            "Eliminado em",
        ])
        for doc in documents:
            writer.writerow([
                doc.id,
                _iso(doc.document_date),
                _csv_text(doc.vendor_name),
                _csv_text(doc.vendor_nif),
                _csv_text(doc.invoice_number),
                doc.document_type or "",
                _csv_amount(doc.net_amount),
                _csv_amount(doc.vat_amount),
                _csv_amount(doc.gross_amount),
                _csv_amount(doc.vat_rate),
                _csv_text(doc.expense_category),
                doc.status,
                _csv_text(doc.review_notes),
                _csv_text(doc.original_filename),
                files.get(doc.id) or "",
                _iso(doc.created_at),
                _iso(doc.deleted_at),
            ])
        return output.getvalue()

    @staticmethod
    def _vat_csv(entries: list[VatSalesEntry]) -> str:
        output = io.StringIO()
        output.write("\ufeff")
        writer = csv.writer(output, delimiter=";")
        writer.writerow(["ID", "Tipo de período", "Ano", "Período", "IVA das vendas (EUR)", "Notas", "Atualizado em"])
        for entry in entries:
            writer.writerow([
                entry.id,
                "Trimestre" if entry.period_type == "quarter" else "Mês",
                entry.year,
                entry.period_value,
                _csv_amount(entry.vat_amount),
                _csv_text(entry.notes),
                _iso(entry.updated_at),
            ])
        return output.getvalue()


_service: Optional[AccountExportService] = None


def get_account_export_service() -> AccountExportService:
    global _service
    if _service is None:
        _service = AccountExportService()
    return _service

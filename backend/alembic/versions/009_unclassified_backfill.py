"""Widen document_type and backfill unclassified rows

Revision ID: 009_unclassified_backfill
Revises: 008_document_type
Create Date: 2026-10-24

A ready or accountant_review row that is not a concrete AT QR goes back to
needs_review. Nothing is deployed, so that only affects dev data.

Non-JSON OCR text and JSON values that are not objects are not rewritten.
A missing raw value still round-trips through ``_type_backup``.

Downgrade does not restore ``ready`` for a row whose raw value is not a JSON
object: there is no ``_type_backup`` to read, so the row stays unclassified
and needs_review. The raw text itself is preserved. Dev databases only.

Downgrade of a 2f8c720-era 008 (never merged, dev databases only) cannot
restore amount signs: that revision left no ``_amount_sign_backup``. This
revision does not change 008.

"""
from alembic import op
import sqlalchemy as sa

from app.services.document_type_backfill import (
    backfill_document_types,
    restore_document_types,
)


revision = "009_unclassified_backfill"
down_revision = "008_document_type"
branch_labels = None
depends_on = None


def _widen_document_type(bind) -> None:
    """varchar(8) cannot store 'unclassified'. Widen before the backfill writes it."""
    if bind.dialect.name != "postgresql":
        return
    length = bind.execute(
        sa.text(
            """
            SELECT character_maximum_length
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = 'documents'
              AND column_name = 'document_type'
            """
        )
    ).scalar()
    if length is not None and int(length) < 20:
        bind.execute(sa.text("ALTER TABLE documents ALTER COLUMN document_type TYPE VARCHAR(20)"))


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("documents")}
    if "document_type" not in columns:
        op.add_column("documents", sa.Column("document_type", sa.String(length=20), nullable=True))
    else:
        _widen_document_type(bind)
    for name, type_ in (
        ("suggested_type", sa.String(length=20)),
        ("suggested_invoice_number", sa.String(length=100)),
        ("at_document_type", sa.String(length=16)),
    ):
        if name not in columns:
            op.add_column("documents", sa.Column(name, type_, nullable=True))
    backfill_document_types(bind)
    op.alter_column(
        "documents",
        "document_type",
        existing_type=sa.String(length=20),
        nullable=False,
        server_default="unclassified",
    )


def downgrade() -> None:
    # Nullable first so a restored NULL type from revision 008 fits.
    # The column stays varchar(20): 'unclassified' has to round-trip.
    op.alter_column(
        "documents",
        "document_type",
        existing_type=sa.String(length=20),
        nullable=True,
        server_default=None,
    )
    restore_document_types(op.get_bind())
    for name in ("suggested_type", "suggested_invoice_number", "at_document_type"):
        op.drop_column("documents", name)

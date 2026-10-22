"""Document type column, and absolute amounts for legacy negatives

Revision ID: 008_document_type
Revises: 007_efatura_links
Create Date: 2026-10-22

"""
from alembic import op
import sqlalchemy as sa

from app.services.legacy_amounts import repair_legacy_negative_amounts


revision = "008_document_type"
down_revision = "007_efatura_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("documents")}
    if "document_type" not in columns:
        op.add_column("documents", sa.Column("document_type", sa.String(length=8), nullable=True))
    repair_legacy_negative_amounts(bind)


def downgrade() -> None:
    op.drop_column("documents", "document_type")

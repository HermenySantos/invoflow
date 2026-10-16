"""e-Fatura subject and link tables

Revision ID: 007_efatura_links
Revises: 006_deductible_override
Create Date: 2026-10-16

"""
from alembic import op
import sqlalchemy as sa


revision = "007_efatura_links"
down_revision = "006_deductible_override"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "efatura_subjects",
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("taxpayer_nif", sa.String(9), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "efatura_links",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_key", sa.String(200), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("document_id", sa.String(36), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=True),
        sa.Column("fiscal_status", sa.String(20), nullable=False),
        sa.Column("warning", sa.Text(), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("user_id", "source_key", name="uq_efatura_link_source"),
    )
    op.create_index("ix_efatura_links_user_id", "efatura_links", ["user_id"])
    op.create_index("ix_efatura_links_document_id", "efatura_links", ["document_id"])


def downgrade() -> None:
    op.drop_index("ix_efatura_links_document_id", table_name="efatura_links")
    op.drop_index("ix_efatura_links_user_id", table_name="efatura_links")
    op.drop_table("efatura_links")
    op.drop_table("efatura_subjects")

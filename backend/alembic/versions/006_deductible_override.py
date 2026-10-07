"""Per-receipt override of the VAT deductible percentage

Revision ID: 006_deductible_override
Revises: 005_soft_delete_documents
Create Date: 2026-10-07

"""
from alembic import op
import sqlalchemy as sa


revision = '006_deductible_override'
down_revision = '005_soft_delete_documents'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('documents', sa.Column('deductible_pct_override', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('documents', 'deductible_pct_override')

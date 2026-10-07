"""Soft-delete documents: deleted_at instead of removing rows and files

Revision ID: 005_soft_delete_documents
Revises: 004_categories_and_string_ids
Create Date: 2026-10-07

"""
from alembic import op
import sqlalchemy as sa


revision = '005_soft_delete_documents'
down_revision = '004_categories_and_string_ids'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('documents', sa.Column('deleted_at', sa.DateTime(), nullable=True))
    op.create_index('ix_documents_deleted_at', 'documents', ['deleted_at'])


def downgrade() -> None:
    op.drop_index('ix_documents_deleted_at', table_name='documents')
    op.drop_column('documents', 'deleted_at')

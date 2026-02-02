"""Initial migration - users and documents tables

Revision ID: 001_initial
Revises: 
Create Date: 2026-02-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create users table
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('clerk_id', sa.String(255), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_users_clerk_id', 'users', ['clerk_id'], unique=True)
    
    # Create documents table
    op.create_table(
        'documents',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('status', sa.String(50), nullable=False),
        sa.Column('storage_key', sa.String(500), nullable=False),
        sa.Column('original_filename', sa.String(255), nullable=False),
        sa.Column('mime_type', sa.String(100), nullable=False),
        sa.Column('file_size', sa.Integer(), nullable=True),
        sa.Column('vendor_name', sa.String(255), nullable=True),
        sa.Column('vendor_nif', sa.String(20), nullable=True),
        sa.Column('invoice_number', sa.String(100), nullable=True),
        sa.Column('document_date', sa.Date(), nullable=True),
        sa.Column('net_amount', sa.Numeric(12, 2), nullable=True),
        sa.Column('vat_amount', sa.Numeric(12, 2), nullable=True),
        sa.Column('gross_amount', sa.Numeric(12, 2), nullable=True),
        sa.Column('vat_rate', sa.Numeric(5, 2), nullable=True),
        sa.Column('ocr_confidence', sa.Numeric(5, 2), nullable=True),
        sa.Column('ocr_raw_response', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_documents_status', 'documents', ['status'])
    op.create_index('ix_documents_user_id', 'documents', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_documents_user_id', table_name='documents')
    op.drop_index('ix_documents_status', table_name='documents')
    op.drop_table('documents')
    op.drop_index('ix_users_clerk_id', table_name='users')
    op.drop_table('users')

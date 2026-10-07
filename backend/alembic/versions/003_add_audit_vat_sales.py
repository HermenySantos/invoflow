"""Add audit_logs and vat_sales_entries tables

Revision ID: 003_add_audit_vat_sales
Revises: 002_add_review_notes
Create Date: 2026-02-06

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '003_add_audit_vat_sales'
down_revision = '002_add_review_notes'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── audit_logs table ──
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('entity_type', sa.String(50), nullable=False),
        sa.Column('entity_id', sa.String(36), nullable=False),
        sa.Column('user_id', sa.String(36), nullable=False),
        sa.Column('action', sa.String(50), nullable=False),
        sa.Column('source', sa.String(50), nullable=False, server_default='user'),
        sa.Column('changes_json', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_audit_entity', 'audit_logs', ['entity_type', 'entity_id'])
    op.create_index('ix_audit_user', 'audit_logs', ['user_id'])

    # ── vat_sales_entries table ──
    op.create_table(
        'vat_sales_entries',
        sa.Column('id', sa.String(36), primary_key=True),
        # Must match users.id as created in 001 (UUID on Postgres).
        sa.Column('user_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('period_type', sa.String(10), nullable=False),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('period_value', sa.Integer(), nullable=False),
        sa.Column('vat_amount', sa.Numeric(12, 2), nullable=False, server_default='0'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('user_id', 'period_type', 'year', 'period_value', name='uq_vat_sales_period'),
    )


def downgrade() -> None:
    op.drop_table('vat_sales_entries')
    op.drop_index('ix_audit_user', table_name='audit_logs')
    op.drop_index('ix_audit_entity', table_name='audit_logs')
    op.drop_table('audit_logs')

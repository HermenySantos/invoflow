"""Add expense category / IRS sector, and store ids as strings like the models

Revision ID: 004_categories_and_string_ids
Revises: 003_add_audit_vat_sales
Create Date: 2026-10-07

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '004_categories_and_string_ids'
down_revision = '003_add_audit_vat_sales'
branch_labels = None
depends_on = None

# (table, column) pairs created as UUID in 001/003; the models use String(36).
UUID_COLUMNS = [
    ('users', 'id'),
    ('documents', 'id'),
    ('documents', 'user_id'),
    ('vat_sales_entries', 'user_id'),
]
USER_FOREIGN_KEYS = [
    ('documents', 'documents_user_id_fkey'),
    ('vat_sales_entries', 'vat_sales_entries_user_id_fkey'),
]


def upgrade() -> None:
    op.add_column('documents', sa.Column('expense_category', sa.String(50), nullable=True))
    op.add_column('documents', sa.Column('irs_sector', sa.String(50), nullable=True))
    op.create_index('ix_documents_expense_category', 'documents', ['expense_category'])
    op.create_index('ix_documents_irs_sector', 'documents', ['irs_sector'])

    if op.get_bind().dialect.name != 'postgresql':
        return
    for table, constraint in USER_FOREIGN_KEYS:
        op.drop_constraint(constraint, table, type_='foreignkey')
    for table, column in UUID_COLUMNS:
        op.alter_column(
            table, column,
            type_=sa.String(36),
            postgresql_using=f'{column}::text',
        )
    for table, constraint in USER_FOREIGN_KEYS:
        op.create_foreign_key(constraint, table, 'users', ['user_id'], ['id'], ondelete='CASCADE')


def downgrade() -> None:
    if op.get_bind().dialect.name == 'postgresql':
        for table, constraint in USER_FOREIGN_KEYS:
            op.drop_constraint(constraint, table, type_='foreignkey')
        for table, column in UUID_COLUMNS:
            op.alter_column(
                table, column,
                type_=postgresql.UUID(as_uuid=True),
                postgresql_using=f'{column}::uuid',
            )
        for table, constraint in USER_FOREIGN_KEYS:
            op.create_foreign_key(constraint, table, 'users', ['user_id'], ['id'], ondelete='CASCADE')

    op.drop_index('ix_documents_irs_sector', table_name='documents')
    op.drop_index('ix_documents_expense_category', table_name='documents')
    op.drop_column('documents', 'irs_sector')
    op.drop_column('documents', 'expense_category')

"""Add review_notes column to documents table

Revision ID: 002_add_review_notes
Revises: 001_initial
Create Date: 2026-02-01

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '002_add_review_notes'
down_revision = '001_initial'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add review_notes column to documents table
    op.add_column(
        'documents',
        sa.Column('review_notes', sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('documents', 'review_notes')

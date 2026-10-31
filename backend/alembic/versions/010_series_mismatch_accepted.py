"""Record a printed invoice-family pair the user accepted

Revision ID: 010_series_mismatch_accepted
Revises: 009_unclassified_backfill
Create Date: 2026-10-26

Does not edit 009. Existing rows are not an accepted mismatch.

"""
from alembic import op
import sqlalchemy as sa


revision = "010_series_mismatch_accepted"
down_revision = "009_unclassified_backfill"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("documents")}
    if "series_mismatch_accepted" in columns:
        return
    op.add_column(
        "documents",
        sa.Column(
            "series_mismatch_accepted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("documents")}
    if "series_mismatch_accepted" not in columns:
        return
    op.drop_column("documents", "series_mismatch_accepted")

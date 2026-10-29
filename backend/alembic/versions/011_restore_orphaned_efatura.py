"""Restore e-Fatura invoices whose linked scan was already deleted

Revision ID: 011_restore_orphaned_efatura
Revises: 010_series_mismatch_accepted
Create Date: 2026-10-29

A link that still points at a soft-deleted scan drops that AT invoice from
the totals. This stores a normal AT document and points the link at it.
The scan stays deleted. Running upgrade again changes nothing.

Downgrade does not remove the restored rows. The invoice has to keep
surviving a schema rollback, and the unlink audit is not in this revision.

"""
from alembic import op
from sqlalchemy.orm import Session


revision = "011_restore_orphaned_efatura"
down_revision = "010_series_mismatch_accepted"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from app.services.efatura import repair_orphaned_efatura_links

    session = Session(bind=op.get_bind())
    repair_orphaned_efatura_links(session)
    session.flush()


def downgrade() -> None:
    # Data repair only. The restored AT rows and their audit entries stay.
    return

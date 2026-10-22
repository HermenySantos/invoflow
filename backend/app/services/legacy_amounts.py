"""Repair rows from earlier draft heads that stored a minus in an amount.

The sign lives on document_type NC. Amounts are absolute. Running the
statement again changes nothing: the WHERE clause only matches a negative.
"""

from sqlalchemy import text

ABSOLUTE_CREDIT_SQL = """
UPDATE documents
SET document_type = COALESCE(NULLIF(document_type, ''), 'NC'),
    net_amount = CASE WHEN net_amount < 0 THEN -net_amount ELSE net_amount END,
    vat_amount = CASE WHEN vat_amount < 0 THEN -vat_amount ELSE vat_amount END,
    gross_amount = CASE WHEN gross_amount < 0 THEN -gross_amount ELSE gross_amount END
WHERE net_amount < 0 OR vat_amount < 0 OR gross_amount < 0
"""


def repair_legacy_negative_amounts(connection) -> None:
    connection.execute(text(ABSOLUTE_CREDIT_SQL))

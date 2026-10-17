"""Quarter-to-date projection. No database and no tax table."""

from datetime import date
from decimal import Decimal

import pytest

from app.services.iva_projection import (
    PROJECTION_DISCLAIMER,
    PROJECTION_LABEL,
    QuarterProjectionInput,
    project_quarter_to_date,
)


def _project(as_of: str, confirmed: str, sales: str | None):
    return project_quarter_to_date(
        QuarterProjectionInput(
            year=2026,
            quarter=1,
            as_of=date.fromisoformat(as_of),
            confirmed_deductible=Decimal(confirmed),
            vat_on_sales=None if sales is None else Decimal(sales),
        )
    )


def test_missing_sales_projects_deductible_and_leaves_payable_empty():
    projection = _project("2026-02-15", "46.00", None)
    assert projection.label == PROJECTION_LABEL
    assert projection.disclaimer == PROJECTION_DISCLAIMER
    assert "declaração fiscal" in projection.disclaimer
    assert "accountant-ready" not in projection.disclaimer
    assert projection.days_elapsed == 46
    assert projection.days_in_quarter == 90
    assert projection.projected_deductible == Decimal("90.00")
    assert projection.projected_iva_payable is None
    assert projection.sales_basis == "missing"


def test_entered_zero_sales_still_produces_a_payable():
    projection = _project("2026-02-15", "46.00", "0.00")
    assert projection.projected_deductible == Decimal("90.00")
    assert projection.projected_iva_payable == Decimal("-90.00")
    assert projection.sales_basis == "entered_period_lump"


def test_sales_lump_is_not_scaled():
    projection = _project("2026-02-15", "46.00", "100.00")
    assert projection.projected_deductible == Decimal("90.00")
    assert projection.projected_iva_payable == Decimal("10.00")
    assert projection.vat_on_sales == Decimal("100.00")


def test_partial_day_quantizes_half_up():
    projection = _project("2026-02-15", "10.00", None)
    assert projection.projected_deductible == Decimal("19.57")
    assert projection.projected_iva_payable is None


def test_day_after_the_quarter_does_not_scale_past_it():
    projection = _project("2026-04-01", "90.00", "100.00")
    assert projection.days_elapsed == 90
    assert projection.projected_deductible == Decimal("90.00")
    assert projection.projected_iva_payable == Decimal("10.00")


def test_day_before_the_quarter_projects_no_deductible():
    projection = _project("2025-12-31", "0.00", "100.00")
    assert projection.days_elapsed == 0
    assert projection.projected_deductible == Decimal("0.00")
    assert projection.projected_iva_payable == Decimal("100.00")


def test_quarter_outside_one_to_four_is_rejected():
    with pytest.raises(ValueError):
        project_quarter_to_date(
            QuarterProjectionInput(
                year=2026,
                quarter=0,
                as_of=date(2026, 2, 15),
                confirmed_deductible=Decimal("0"),
                vat_on_sales=None,
            )
        )

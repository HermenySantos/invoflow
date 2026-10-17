"""Filing day for the periodic IVA declaration.

CIVA art. 41.º n.º 1: the 20th of the second month after the period.
N.º 10 (Decreto-Lei n.º 49/2025): June and the second quarter are due on
20 September. CPPT art. 20.º n.º 1 and Código Civil art. 279.º alínea e)
move a term that ends on a day the tax services are closed (Saturday,
Sunday, or a national public holiday) to the next working day. The same
rule is implemented in frontend/lib/deadlines.ts.
"""

from __future__ import annotations

from datetime import date, timedelta

_MONTHS_PT = (
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
)


def _easter(year: int) -> date:
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    ell = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ell) // 451
    month = (h + ell - 7 * m + 114) // 31
    day = ((h + ell - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _holidays(year: int) -> set[date]:
    easter = _easter(year)
    return {
        date(year, 1, 1),
        easter - timedelta(days=2),
        date(year, 4, 25),
        date(year, 5, 1),
        easter + timedelta(days=60),
        date(year, 6, 10),
        date(year, 8, 15),
        date(year, 10, 5),
        date(year, 11, 1),
        date(year, 12, 1),
        date(year, 12, 8),
        date(year, 12, 25),
    }


def _closed(day: date) -> bool:
    return day.weekday() >= 5 or day in _holidays(day.year)


def _next_working_day(day: date) -> date:
    while _closed(day):
        day += timedelta(days=1)
    return day


def filing_deadline(period_type: str, year: int, period_value: int) -> date:
    if period_type == "quarter":
        months = (5, 9, 11, 2)
        deadline_year = year + 1 if period_value == 4 else year
        month = months[period_value - 1]
    elif period_value == 6:
        deadline_year = year
        month = 9
    else:
        # 0-based index of the second following month, then a calendar month.
        month_index = period_value + 1
        deadline_year = year + month_index // 12
        month = month_index % 12 + 1
    return _next_working_day(date(deadline_year, month, 20))


def deadline_line(period: str) -> str | None:
    """'2026-Q2' or '2026-09' -> the Portuguese filing line for that period."""
    try:
        if "-Q" in period:
            year_text, quarter_text = period.split("-Q", 1)
            day = filing_deadline("quarter", int(year_text), int(quarter_text))
        else:
            year_text, month_text = period.split("-", 1)
            day = filing_deadline("month", int(year_text), int(month_text))
    except (ValueError, IndexError):
        return None
    return f"Prazo de entrega: {day.day} de {_MONTHS_PT[day.month - 1]} de {day.year}"

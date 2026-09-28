"""Model period layout — pure, no IO.

Periods are calendar quarters ("2026Q3") and calendar years ("2029Y"). A
company's fiscal quarter maps to the calendar quarter whose end date is
nearest its period-end date (NVDA's quarter ending 2026-07-26 → 2026Q2), the
usual "calendarization" convention. FMP's /stable/ statements carry fiscalYear
and no calendarYear, so the statement `date` is the reliable key.

Layout: 8 historical quarters ending at the latest reported quarter, forecast
quarters through Q4 of the following calendar year (5–8 of them), then 5
forecast years — contiguous, so nothing falls between the last forecast
quarter and the first forecast year (the old layout could skip up to 3).
"""
from __future__ import annotations

from datetime import date

from backend.app.models.model_state import Period

N_HISTORICAL_QUARTERS = 8
N_FORECAST_YEARS = 5
_QUARTER_END = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}


def calendar_quarter_label(d: date | str) -> str:
    """'YYYYQn' for the calendar quarter whose end is nearest `d`."""
    if isinstance(d, str):
        d = date.fromisoformat(d[:10])
    best: tuple[int, str] | None = None
    for y in (d.year - 1, d.year, d.year + 1):
        for q, (m, day) in _QUARTER_END.items():
            dist = abs((date(y, m, day) - d).days)
            if best is None or dist < best[0]:
                best = (dist, f"{y}Q{q}")
    assert best is not None
    return best[1]


def parse_quarter(label: str) -> tuple[int, int]:
    year, q = label.split("Q")
    return int(year), int(q)


def shift_quarter(label: str, n: int) -> str:
    year, q = parse_quarter(label)
    idx = year * 4 + (q - 1) + n
    return f"{idx // 4}Q{idx % 4 + 1}"


def build_periods(last_historical_quarter: str) -> list[Period]:
    """8 historical quarters, forecast quarters through Q4 of next year, 5 years."""
    periods: list[Period] = []
    for i in range(N_HISTORICAL_QUARTERS - 1, -1, -1):
        label = shift_quarter(last_historical_quarter, -i)
        periods.append(Period(label=label, kind="Q", is_historical=True, quarter_index=parse_quarter(label)[1]))
    first_forecast = shift_quarter(last_historical_quarter, 1)
    last_forecast = f"{parse_quarter(first_forecast)[0] + 1}Q4"
    label = first_forecast
    while True:
        periods.append(Period(label=label, kind="Q", is_historical=False, quarter_index=parse_quarter(label)[1]))
        if label == last_forecast:
            break
        label = shift_quarter(label, 1)
    first_year = parse_quarter(last_forecast)[0] + 1
    for y in range(first_year, first_year + N_FORECAST_YEARS):
        periods.append(Period(label=f"{y}Y", kind="Y", is_historical=False))
    return periods


def period_fraction(p: Period) -> float:
    """Length of a period in years."""
    return 0.25 if p.kind == "Q" else 1.0


def days_in_period(p: Period) -> float:
    return 365.0 * period_fraction(p)


def period_year(p: Period) -> int:
    return parse_quarter(p.label)[0] if p.kind == "Q" else int(p.label.rstrip("Y"))

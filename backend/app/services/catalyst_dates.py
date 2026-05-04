"""Best-effort mapping of free-form catalyst timeframe strings to date windows.

Sonnet emits creative timeframes — "Q2 2026", "Next 1-3 mo", "H2 2027".
This module handles the common shapes and falls back to (None, None,
"untimed") for the rest. Untimed catalysts surface in a separate bucket
in the calendar UI rather than getting bogus parsed dates.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal

DateSource = Literal[
    "fmp_earnings",
    "parsed_quarter",
    "parsed_relative",
    "parsed_year",
    "parsed_half",
    "untimed",
]


@dataclass(frozen=True)
class ParsedDates:
    window_start: date | None
    window_end: date | None
    source: DateSource


_QUARTER = re.compile(r"\bQ([1-4])\s+(\d{4})\b", re.IGNORECASE)
_HALF = re.compile(r"\bH([12])\s+(\d{4})\b", re.IGNORECASE)
_YEAR = re.compile(r"^\s*(\d{4})\s*$")
_RELATIVE = re.compile(
    r"(?:next\s+|in\s+)?(\d+)\s*(?:[-–]\s*(\d+))?\s*(mo|month|months|wk|week|weeks|day|days)\b",
    re.IGNORECASE,
)
_UNTIMED_HINTS = {"pending", "eventually", "tbd", "tbd date", "n/a", "long-term", "long term"}


def parse_timeframe(timeframe: str, anchor: datetime) -> ParsedDates:
    """Parse a Sonnet-emitted timeframe string into a date window.

    Args:
        timeframe: free-form string like "Q2 2026", "Next 1-3 mo".
        anchor: reference datetime for relative timeframes (typically now).

    Returns:
        ParsedDates with window_start/window_end populated when the shape is
        recognised, else (None, None, "untimed").
    """
    s = (timeframe or "").strip()
    if not s or s.lower() in _UNTIMED_HINTS:
        return ParsedDates(None, None, "untimed")

    if (m := _QUARTER.search(s)):
        q, year = int(m.group(1)), int(m.group(2))
        start = date(year, 3 * q - 2, 1)
        end_month = 3 * q
        if end_month == 12:
            end = date(year, 12, 31)
        else:
            end = date(year, end_month + 1, 1) - timedelta(days=1)
        return ParsedDates(start, end, "parsed_quarter")

    if (m := _HALF.search(s)):
        h, year = int(m.group(1)), int(m.group(2))
        if h == 1:
            return ParsedDates(date(year, 1, 1), date(year, 6, 30), "parsed_half")
        return ParsedDates(date(year, 7, 1), date(year, 12, 31), "parsed_half")

    if (m := _YEAR.match(s)):
        year = int(m.group(1))
        return ParsedDates(date(year, 1, 1), date(year, 12, 31), "parsed_year")

    if (m := _RELATIVE.search(s)):
        lo = int(m.group(1))
        hi = int(m.group(2)) if m.group(2) else lo
        unit = m.group(3).lower()
        days_per = {
            "day": 1, "days": 1,
            "wk": 7, "week": 7, "weeks": 7,
            "mo": 30, "month": 30, "months": 30,
        }[unit]
        anchor_date = anchor.date()
        return ParsedDates(
            anchor_date + timedelta(days=lo * days_per),
            anchor_date + timedelta(days=hi * days_per),
            "parsed_relative",
        )

    return ParsedDates(None, None, "untimed")

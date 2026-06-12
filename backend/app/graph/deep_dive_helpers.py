"""Pure helpers used by `node_deep_dive`'s context builders.

Lifted from inside the function so they can be exercised on JSON
fixtures in unit tests rather than only as a side-effect of running
the full deep-dive node. Behaviour-identical to the originals.
"""
from __future__ import annotations

from typing import TypeVar

T = TypeVar("T")


def unwrap_gather_result(result: object, default: T) -> T:
    """Unwrap one slot of an `asyncio.gather(..., return_exceptions=True)` result.

    Each FMP / EDGAR / X / FRED client method returns `(data, citation)`
    on success. When gather is told to return exceptions, a failed slot
    is the exception itself rather than a tuple — return the default in
    that case so the caller can keep going.
    """
    if isinstance(result, BaseException):
        return default
    # Each client method returns (data, citation); we want the data.
    return result[0]  # type: ignore[index, return-value]


def unwrap_gather_citation(result: object):
    """Citation counterpart of unwrap_gather_result: pull the Citation half
    of a `(data, citation)` gather slot, or None for a failed slot."""
    if isinstance(result, BaseException):
        return None
    return result[1]  # type: ignore[index]


def format_fact_value(value: float, unit: str) -> str:
    """Format an XBRL fact value for inclusion in an LLM prompt.

    USD values are scaled to B / M / dollars; "pure" ratios become
    percentages when |value| <= 1, otherwise raw decimals; everything
    else gets the unit suffix.
    """
    if unit.upper() == "USD":
        if abs(value) >= 1e9:
            return f"${value/1e9:.2f}B"
        if abs(value) >= 1e6:
            return f"${value/1e6:.2f}M"
        return f"${value:,.0f}"
    if unit.lower() == "pure":
        return f"{value*100:.2f}%" if abs(value) <= 1 else f"{value:.2f}"
    return f"{value:,.0f} {unit}"

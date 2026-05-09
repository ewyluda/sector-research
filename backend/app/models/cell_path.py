"""Typed cell-path value objects for the financial model.

The wire format stays a dotted string (`drivers.<period>.<key>` /
`<stmt>.<line>.<period>` / `assumptions.<key>`); these types own parse/build
on the backend so callers don't open-code `str.split(".")` and so unknown
keys/periods/line-items are rejected at the boundary.

Mirrored in `frontend/lib/cellPath.ts`. Round-trip parse(to_str(p)) == p.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from backend.app.models.model_state import (
    DRIVER_KEYS,
    LINE_ITEMS_BS,
    LINE_ITEMS_CF,
    LINE_ITEMS_PNL,
)


class Statement(str, Enum):
    INCOME = "income_statement"
    BALANCE = "balance_sheet"
    CASH_FLOW = "cash_flow"


# ModelCell-shaped assumptions only. The categorical assumptions
# (`terminal_method`, `plug_priority`) edit through a different surface.
ASSUMPTION_CELL_KEYS: frozenset[str] = frozenset(
    {"discount_rate", "terminal_multiple", "perpetuity_growth", "tax_rate"}
)

_LINES_BY_STMT: dict[Statement, frozenset[str]] = {
    Statement.INCOME: frozenset(LINE_ITEMS_PNL),
    Statement.BALANCE: frozenset(LINE_ITEMS_BS),
    Statement.CASH_FLOW: frozenset(LINE_ITEMS_CF),
}

_DRIVER_KEYS_SET: frozenset[str] = frozenset(DRIVER_KEYS)
_PERIOD_RE = re.compile(r"^\d{4}(Q[1-4]|Y)$")


def _validate_period(p: str) -> None:
    if not _PERIOD_RE.match(p):
        raise ValueError(f"invalid period label: {p!r}")


@dataclass(frozen=True)
class DriverPath:
    period: str
    key: str

    def __post_init__(self) -> None:
        _validate_period(self.period)
        if self.key not in _DRIVER_KEYS_SET:
            raise ValueError(f"unknown driver key: {self.key!r}")

    def __str__(self) -> str:
        return f"drivers.{self.period}.{self.key}"


@dataclass(frozen=True)
class StatementCellPath:
    statement: Statement
    line: str
    period: str

    def __post_init__(self) -> None:
        _validate_period(self.period)
        if self.line not in _LINES_BY_STMT[self.statement]:
            raise ValueError(
                f"unknown line item {self.line!r} for {self.statement.value}"
            )

    def __str__(self) -> str:
        return f"{self.statement.value}.{self.line}.{self.period}"


@dataclass(frozen=True)
class AssumptionPath:
    key: str

    def __post_init__(self) -> None:
        if self.key not in ASSUMPTION_CELL_KEYS:
            raise ValueError(f"unknown assumption cell key: {self.key!r}")

    def __str__(self) -> str:
        return f"assumptions.{self.key}"


CellPath = DriverPath | StatementCellPath | AssumptionPath


_STATEMENT_VALUES: frozenset[str] = frozenset(s.value for s in Statement)


def parse(s: str) -> CellPath:
    """Parse a dotted cell_path string into a typed CellPath.

    Raises ValueError on unknown shapes, periods, or registry keys.
    """
    parts = s.split(".")
    if len(parts) == 3 and parts[0] == "drivers":
        return DriverPath(period=parts[1], key=parts[2])
    if len(parts) == 3 and parts[0] in _STATEMENT_VALUES:
        return StatementCellPath(
            statement=Statement(parts[0]), line=parts[1], period=parts[2]
        )
    if len(parts) == 2 and parts[0] == "assumptions":
        return AssumptionPath(key=parts[1])
    raise ValueError(f"unknown cell_path shape: {s!r}")


def to_str(p: CellPath) -> str:
    return str(p)

"""Cell-path-keyed JSON diff between two ModelStates."""
from __future__ import annotations
from typing import Iterable

from backend.app.models.model_state import ModelState, ModelCell


def _walk_cells(state: ModelState) -> Iterable[tuple[str, ModelCell]]:
    for stmt_name, stmt in [
        ("income_statement", state.income_statement),
        ("balance_sheet", state.balance_sheet),
        ("cash_flow", state.cash_flow),
    ]:
        for line, periods in stmt.items():
            for period, cell in periods.items():
                yield f"{stmt_name}.{line}.{period}", cell
    for period, drvs in state.drivers.items():
        for k, cell in drvs.items():
            yield f"drivers.{period}.{k}", cell
    for k in ("discount_rate", "terminal_multiple", "perpetuity_growth", "tax_rate"):
        cell = getattr(state.assumptions, k)
        yield f"assumptions.{k}", cell


def diff_states(a: ModelState, b: ModelState, *, eps: float = 1e-6) -> dict:
    """Return {added, removed, changed} keyed by cell_path."""
    a_map = {p: c for p, c in _walk_cells(a)}
    b_map = {p: c for p, c in _walk_cells(b)}
    added = sorted(set(b_map) - set(a_map))
    removed = sorted(set(a_map) - set(b_map))
    changed: list[dict] = []
    for path in sorted(set(a_map) & set(b_map)):
        ca, cb = a_map[path], b_map[path]
        va, vb = ca.value or 0.0, cb.value or 0.0
        if abs(va - vb) > eps or ca.source != cb.source:
            changed.append({"cell_path": path, "before": {"value": ca.value, "source": ca.source},
                            "after": {"value": cb.value, "source": cb.source}})
    return {"added": added, "removed": removed, "changed": changed}

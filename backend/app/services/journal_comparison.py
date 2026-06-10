"""Pure decision-vs-outcome math for the trade journal.

No DB, no FMP, no ORM imports — operates on primitives so it unit-tests
without fixtures (pattern: insider_signal.py, model_balancing.py).
All values are FRACTIONAL (0.12 = +12%), matching
verdict_return_snapshots.ticker_return_pct and the frontend ReturnCell.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

# Midpoints between consecutive snapshot durations (1, 7, 30, 91, 182 days);
# holding_days <= threshold maps to that offset.
_OFFSET_THRESHOLDS: list[tuple[int, str]] = [(4, "1d"), (18, "1w"), (60, "1m"), (136, "3m")]


@dataclass(frozen=True)
class TradeReturns:
    return_pct: Decimal | None
    spy_excess_pct: Decimal | None
    holding_days: int | None


@dataclass(frozen=True)
class DecisionComparison:
    offset: str
    trade_return_pct: Decimal
    trade_spy_excess_pct: Decimal | None
    paper_return_pct: Decimal
    paper_spy_excess_pct: Decimal | None
    execution_delta_pct: Decimal | None  # trade excess − paper excess


@dataclass(frozen=True)
class ClosedTradeStat:
    return_pct: Decimal
    spy_excess_pct: Decimal | None
    holding_days: int
    exit_reason: str | None
    execution_delta_pct: Decimal | None


def trade_returns(
    *,
    direction: str,
    entry_date: date,
    entry_price: Decimal,
    exit_date: date | None,
    exit_price: Decimal | None,
    spy_entry_price: Decimal | None,
    spy_exit_price: Decimal | None,
) -> TradeReturns:
    """Realized returns for a closed trade; all-None when exit data is absent.

    Short return = −(long return). SPY excess = trade_return − spy_return over
    the same holding period regardless of direction; None when either SPY
    price is missing.
    """
    if exit_date is None or exit_price is None:
        return TradeReturns(None, None, None)
    raw = (exit_price - entry_price) / entry_price
    ret = -raw if direction == "short" else raw
    excess = None
    if spy_entry_price is not None and spy_exit_price is not None:
        excess = ret - (spy_exit_price - spy_entry_price) / spy_entry_price
    return TradeReturns(ret, excess, (exit_date - entry_date).days)


def nearest_offset(holding_days: int) -> str:
    for threshold, offset in _OFFSET_THRESHOLDS:
        if holding_days <= threshold:
            return offset
    return "6m"


def decision_vs_outcome(
    returns: TradeReturns, snapshots: list[dict]
) -> DecisionComparison | None:
    """Compare a closed trade against its outcome's snapshot at the offset
    nearest the holding period. `snapshots` rows need snapshot_offset,
    ticker_return_pct, spy_excess_pct. None when the trade is open or the
    snapshot at that offset doesn't exist yet. Labeled, not interpolated.
    """
    if returns.return_pct is None or returns.holding_days is None:
        return None
    offset = nearest_offset(returns.holding_days)
    snap = next((s for s in snapshots if s.get("snapshot_offset") == offset), None)
    if snap is None or snap.get("ticker_return_pct") is None:
        return None
    paper_ret = Decimal(str(snap["ticker_return_pct"]))
    paper_excess = (
        Decimal(str(snap["spy_excess_pct"]))
        if snap.get("spy_excess_pct") is not None
        else None
    )
    delta = None
    if returns.spy_excess_pct is not None and paper_excess is not None:
        delta = returns.spy_excess_pct - paper_excess
    return DecisionComparison(
        offset=offset,
        trade_return_pct=returns.return_pct,
        trade_spy_excess_pct=returns.spy_excess_pct,
        paper_return_pct=paper_ret,
        paper_spy_excess_pct=paper_excess,
        execution_delta_pct=delta,
    )


def summarize(closed: list[ClosedTradeStat]) -> dict:
    """Aggregate rollups over closed trades; plain dict the API wraps in
    JournalSummary. A 'hit' is positive SPY excess when available, else
    positive raw return; excess_basis_count = trades judged on excess.
    """
    n = len(closed)
    if n == 0:
        return {
            "closed_count": 0,
            "hit_rate": None,
            "excess_basis_count": 0,
            "avg_return_pct": None,
            "median_return_pct": None,
            "avg_spy_excess_pct": None,
            "avg_holding_days": None,
            "execution_vs_paper": {"n": 0, "avg_delta_pct": None},
            "by_exit_reason": [],
        }

    returns = sorted(t.return_pct for t in closed)
    mid = n // 2
    median = returns[mid] if n % 2 else (returns[mid - 1] + returns[mid]) / 2

    excesses = [t.spy_excess_pct for t in closed if t.spy_excess_pct is not None]
    hits = sum(
        1
        for t in closed
        if (t.spy_excess_pct if t.spy_excess_pct is not None else t.return_pct) > 0
    )
    deltas = [t.execution_delta_pct for t in closed if t.execution_delta_pct is not None]

    by_reason: dict[str, list[ClosedTradeStat]] = {}
    for t in closed:
        by_reason.setdefault(t.exit_reason or "unspecified", []).append(t)

    def _avg(values):
        return sum(values) / len(values) if values else None

    return {
        "closed_count": n,
        "hit_rate": hits / n,
        "excess_basis_count": len(excesses),
        "avg_return_pct": sum(returns) / n,
        "median_return_pct": median,
        "avg_spy_excess_pct": _avg(excesses),
        "avg_holding_days": sum(t.holding_days for t in closed) / n,
        "execution_vs_paper": {"n": len(deltas), "avg_delta_pct": _avg(deltas)},
        "by_exit_reason": [
            {
                "exit_reason": reason,
                "count": len(group),
                "avg_return_pct": _avg([t.return_pct for t in group]),
                "avg_spy_excess_pct": _avg(
                    [t.spy_excess_pct for t in group if t.spy_excess_pct is not None]
                ),
            }
            for reason, group in sorted(by_reason.items())
        ],
    }

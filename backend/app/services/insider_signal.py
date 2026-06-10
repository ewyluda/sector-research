"""Insider-signal aggregate + discovery modifier.

Pure synchronous functions over insider_transactions rows (the
model_balancing.py pattern). Spec:
docs/superpowers/specs/2026-06-10-material-events-design.md

Modifier table (spec — evaluated in this order):
  cluster buying                                  → +5
  net open-market buying (no cluster)             → +2
  pronounced selling (net ≤ -$1M AND ≥3 sellers)  → -3
  otherwise                                       →  0
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, timedelta
from typing import Iterable, Protocol

WINDOW_DAYS = 90
CLUSTER_WINDOW_DAYS = 30
PRONOUNCED_SELL_NET_VALUE = -1_000_000.0
PRONOUNCED_SELL_MIN_SELLERS = 3
# Staleness for the cached insider signal — its own constant, not X's
# STALE_THRESHOLD_HOURS. The scan runs daily; 48h tolerates one missed run.
INSIDER_STALE_HOURS = 48


class _TransactionLike(Protocol):
    direction: str
    transaction_date: date | None
    shares: float | None
    price: float | None
    insider_name: str


@dataclass
class InsiderAggregate:
    buy_count: int
    sell_count: int
    distinct_buyers: int
    distinct_sellers: int
    # Σ(buy shares×price) − Σ(sell shares×price) over priced rows.
    # None when no in-window row has both shares and price.
    net_value: float | None
    cluster_buy: bool
    window_days: int = WINDOW_DAYS


def compute_insider_aggregate(
    transactions: Iterable[_TransactionLike], today: date
) -> InsiderAggregate:
    cutoff = today - timedelta(days=WINDOW_DAYS)
    buys: list[_TransactionLike] = []
    sells: list[_TransactionLike] = []
    for t in transactions:
        if t.transaction_date is None or t.transaction_date < cutoff:
            continue
        if t.direction == "buy":
            buys.append(t)
        elif t.direction == "sell":
            sells.append(t)
        # direction == "other" (awards, exercises…) is excluded entirely

    def _value(t: _TransactionLike) -> float | None:
        if t.shares is None or t.price is None:
            return None
        return float(t.shares) * float(t.price)

    buy_values = [v for v in (_value(t) for t in buys) if v is not None]
    sell_values = [v for v in (_value(t) for t in sells) if v is not None]
    net_value: float | None = None
    if buy_values or sell_values:
        net_value = sum(buy_values) - sum(sell_values)

    # Cluster: ≥2 distinct insiders with buys inside any 30-day window.
    cluster_buy = False
    dated_buys = sorted(
        ((t.transaction_date, t.insider_name) for t in buys), key=lambda p: p[0]
    )
    for i, (d, _) in enumerate(dated_buys):
        window_insiders = {
            name for (d2, name) in dated_buys[i:]
            if (d2 - d).days < CLUSTER_WINDOW_DAYS
        }
        if len(window_insiders) >= 2:
            cluster_buy = True
            break

    return InsiderAggregate(
        buy_count=len(buys),
        sell_count=len(sells),
        distinct_buyers=len({t.insider_name for t in buys}),
        distinct_sellers=len({t.insider_name for t in sells}),
        net_value=net_value,
        cluster_buy=cluster_buy,
    )


def modifier_from_aggregate(agg: InsiderAggregate) -> int:
    if agg.cluster_buy:
        return 5
    if agg.buy_count > 0 and (agg.net_value is None or agg.net_value > 0):
        return 2
    if (
        agg.net_value is not None
        and agg.net_value <= PRONOUNCED_SELL_NET_VALUE
        and agg.distinct_sellers >= PRONOUNCED_SELL_MIN_SELLERS
    ):
        return -3
    return 0


def signal_value(agg: InsiderAggregate) -> dict:
    """JSONB payload for the signals row (signal_type='insider')."""
    return {**asdict(agg), "modifier": modifier_from_aggregate(agg)}

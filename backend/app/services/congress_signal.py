"""Congressional-trading aggregate + discovery modifier.

Pure synchronous functions over congress_transactions rows — the
insider_signal.py pattern, third insider-adjacent signal. Net value comes
from disclosed amount-range midpoints (amount_mid), not shares×price.

Modifier table (evaluated in this order) — deliberately smaller than the
insider one (+5/+2/-3): disclosures lag up to 45 days and amounts are
coarse ranges, so the signal is noisier.
  cluster buying                                  → +3
  net buying (no cluster)                         → +1
  pronounced selling (net ≤ -$1M AND ≥3 sellers)  → -2
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
# Staleness for the cached congress signal — daily scan; 48h tolerates one
# missed run (same rationale as INSIDER_STALE_HOURS).
CONGRESS_STALE_HOURS = 48


class _TransactionLike(Protocol):
    direction: str
    transaction_date: date | None
    amount_mid: float | None
    politician_name: str


@dataclass
class CongressAggregate:
    buy_count: int
    sell_count: int
    distinct_buyers: int
    distinct_sellers: int
    # Σ(buy amount_mid) − Σ(sell amount_mid) over rows with a parsed range.
    # None when no in-window row has amount_mid.
    net_value: float | None
    cluster_buy: bool
    window_days: int = WINDOW_DAYS


def compute_congress_aggregate(
    transactions: Iterable[_TransactionLike], today: date
) -> CongressAggregate:
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
        # direction == "other" (exchanges, non-stock assets…) is excluded

    buy_values = [float(t.amount_mid) for t in buys if t.amount_mid is not None]
    sell_values = [float(t.amount_mid) for t in sells if t.amount_mid is not None]
    net_value: float | None = None
    if buy_values or sell_values:
        net_value = sum(buy_values) - sum(sell_values)

    # Cluster: ≥2 distinct politicians with buys inside any 30-day window.
    cluster_buy = False
    dated_buys = sorted(
        ((t.transaction_date, t.politician_name) for t in buys), key=lambda p: p[0]
    )
    for i, (d, _) in enumerate(dated_buys):
        window_politicians = {
            name for (d2, name) in dated_buys[i:]
            if (d2 - d).days < CLUSTER_WINDOW_DAYS
        }
        if len(window_politicians) >= 2:
            cluster_buy = True
            break

    return CongressAggregate(
        buy_count=len(buys),
        sell_count=len(sells),
        distinct_buyers=len({t.politician_name for t in buys}),
        distinct_sellers=len({t.politician_name for t in sells}),
        net_value=net_value,
        cluster_buy=cluster_buy,
    )


def modifier_from_aggregate(agg: CongressAggregate) -> int:
    if agg.cluster_buy:
        return 3
    if agg.buy_count > 0 and (agg.net_value is None or agg.net_value > 0):
        return 1
    if (
        agg.net_value is not None
        and agg.net_value <= PRONOUNCED_SELL_NET_VALUE
        and agg.distinct_sellers >= PRONOUNCED_SELL_MIN_SELLERS
    ):
        return -2
    return 0


def signal_value(agg: CongressAggregate) -> dict:
    """JSONB payload for the signals row (signal_type='congress')."""
    return {**asdict(agg), "modifier": modifier_from_aggregate(agg)}

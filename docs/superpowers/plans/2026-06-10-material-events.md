# 8-K + Form 4 Monitoring (Material Events) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Daily scan of the universe (theme seeds ∪ active theses) for 8-K filings (Haiku-classified into `material_events`) and Form 4 insider transactions (FMP-sourced into `insider_transactions` → `signals` insider signal), surfaced as a status-board badge + drawer, a Today attention row, and a bounded discovery-score modifier.

**Architecture:** New APScheduler cron job (4th, 06:30 UTC) with fanout-style per-ticker session isolation. 8-K side: EDGAR submissions → item-code prefilter → Haiku structured-output classify → `Filing` + `MaterialEvent` rows. Form 4 side: `FMPClient.get_insider_trading` → natural-key-deduped upsert → pure-function 90-day aggregate → `signals` row (`signal_type="insider"`) mirroring the X velocity pattern. Read side: one-query board join, `/api/events` router, frontend drawer/attention-row/chip.

**Tech Stack:** FastAPI + async SQLAlchemy + Alembic, Anthropic Haiku via `graph/llm.complete` + `assistant_prefill`, Next.js 16 / React 19 / Tailwind v4, Python stdlib `unittest`, `node --test`.

**Spec:** `docs/superpowers/specs/2026-06-10-material-events-design.md` — read it first. Decisions there are settled; don't re-litigate.

**Branch:** `feat/material-events` off `main`.

**Conventions you MUST follow (verified against the repo 2026-06-10):**
- Backend tests: file in `backend/tests/` starting with the env-defaults block (see any existing test). Run from repo root: `backend/venv/bin/python -m unittest backend.tests.<module> -v`.
- API routers: do **NOT** add `from __future__ import annotations` (FastAPI 0.115 + Py3.12 footgun — see `api/status.py` history).
- Tickers upper-cased at write time, everywhere.
- Write paths: explicit `await db.commit()` (or `unit_of_work()`); `async_session` does NOT autocommit.
- Alembic runs from `backend/`: `cd backend && venv/bin/alembic upgrade head` (venv active or use full path `backend/venv/bin/alembic` with `-c backend/alembic.ini` from root — simplest is `cd backend`).
- Current Alembic head: `d9659a472017` (verified by walking the revision graph).

---

### Task 1: Live FMP wire-key verification (GATE — do this before any Form 4 code)

The /stable/ API's field names routinely diverge from docs and training data (cost a review cycle in the peer-comp session). Pin the actual keys now.

**Files:** none modified — this is a verification step whose output adjusts Task 4 if needed.

- [ ] **Step 1: Dump live insider-trading keys**

Run from repo root:

```bash
backend/venv/bin/python -c "
import asyncio, json
from backend.app.clients.fmp import FMPClient
async def main():
    c = FMPClient()
    try:
        rows, _ = await c.get_insider_trading('NVDA', limit=3)
        print('COUNT:', len(rows))
        if rows:
            print('KEYS:', sorted(rows[0].keys()))
            print(json.dumps(rows[0], indent=2, default=str))
    finally:
        await c.close()
asyncio.run(main())
"
```

Expected: `COUNT: 3` (or fewer) and a key list.

- [ ] **Step 2: Compare against the mapping Task 4 assumes**

Task 4's `_map_fmp_row` assumes these wire keys (fallbacks in parentheses):

| Model column | Expected FMP key |
|---|---|
| `insider_name` | `reportingName` |
| `insider_title` | `typeOfOwner` |
| `transaction_type` | `transactionType` |
| `transaction_date` | `transactionDate` |
| `shares` | `securitiesTransacted` |
| `price` | `price` |
| `shares_owned_after` | `securitiesOwned` |
| `sec_link` | `url` (fallback `link`) |
| `accession_number` | parsed from `url` via regex |

**VERIFIED LIVE 2026-06-10 (NVDA):** keys are `['acquisitionOrDisposition', 'companyCik', 'directOrIndirect', 'filingDate', 'formType', 'price', 'reportingCik', 'reportingName', 'securitiesOwned', 'securitiesTransacted', 'securityName', 'symbol', 'transactionDate', 'transactionType', 'typeOfOwner', 'url']`. The link field is `url` (NOT `link`); Task 4 below is already written url-first. Sample accession in `url`: `0001768670-26-000002` (dashed — regex matches).

If a key differs, edit the `_map_fmp_row` constants in Task 4 **before implementing it** and note the change in the commit message. If `link`/`url` is absent entirely, set `sec_link`/`accession_number` to `None` and note that EDGAR traceability needs a follow-up (don't silently drop the columns).

- [ ] **Step 3: Record findings** — paste the key list into the Task 4 commit message body.

No commit for this task.

---

### Task 2: ORM models + migration

**Files:**
- Create: `backend/app/models/material_event.py`
- Create: `backend/app/models/insider_transaction.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/migrations/versions/b7e2c9f4a1d3_material_events_insider_transactions.py`

- [ ] **Step 1: Create `backend/app/models/material_event.py`**

```python
"""MaterialEvent — one classified 8-K per row, surfaced on the status board."""

from datetime import date, datetime
from uuid import uuid4

from sqlalchemy import Date, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base


class MaterialEvent(Base):
    """Haiku-classified 8-K filing. One row per Filing (the classifier picks
    the dominant event type; the summary may mention secondary items)."""

    __tablename__ = "material_events"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    filing_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("filings.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    ticker: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    # Raw EDGAR items string, e.g. "2.02,9.01"
    item_codes: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # guidance | personnel | ma | financing | other
    event_type: Mapped[str] = mapped_column(String(16), nullable=False)
    # high | medium | low
    materiality: Mapped[str] = mapped_column(String(8), nullable=False)
    headline: Mapped[str] = mapped_column(String(256), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    filing_date: Mapped[date] = mapped_column(Date, nullable=False)
    classified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.utcnow()
    )
    # Mirrors read-through dismissal: hidden from badge + Today when set.
    dismissed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("filing_id", name="uq_material_events_filing"),
        Index("ix_material_events_ticker_date", "ticker", "filing_date"),
    )
```

- [ ] **Step 2: Create `backend/app/models/insider_transaction.py`**

```python
"""InsiderTransaction — one Form 4 transaction line, FMP-sourced.

`natural_key` is a sha256 over the identifying fields (see
services/insider_ingest.py) so daily re-ingests are idempotent without
guessing FMP's uniqueness semantics. `accession_number`/`sec_link` keep the
door open for a raw-EDGAR backfill later (spec decision)."""

from datetime import date, datetime
from uuid import uuid4

from sqlalchemy import Date, DateTime, Index, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base


class InsiderTransaction(Base):
    __tablename__ = "insider_transactions"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    ticker: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    insider_name: Mapped[str] = mapped_column(String(256), nullable=False)
    insider_title: Mapped[str | None] = mapped_column(String(256), nullable=True)
    # Raw FMP code, e.g. "P-Purchase", "S-Sale", "A-Award"
    transaction_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Normalized: buy | sell | other (open-market P/S only; awards/exercises = other)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    transaction_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    shares: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    price: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    shares_owned_after: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    accession_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sec_link: Mapped[str | None] = mapped_column(String(512), nullable=True)
    natural_key: Mapped[str] = mapped_column(String(64), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.utcnow()
    )

    __table_args__ = (
        UniqueConstraint("natural_key", name="uq_insider_transactions_natural_key"),
        Index("ix_insider_transactions_ticker_date", "ticker", "transaction_date"),
    )
```

- [ ] **Step 3: Register both in `backend/app/models/__init__.py`**

Add to the import block (alphabetical-ish placement next to the other filing imports):

```python
from backend.app.models.insider_transaction import InsiderTransaction  # noqa: F401
from backend.app.models.material_event import MaterialEvent  # noqa: F401
```

And add `"InsiderTransaction",` and `"MaterialEvent",` to `__all__`.

- [ ] **Step 4: Create the migration** `backend/migrations/versions/b7e2c9f4a1d3_material_events_insider_transactions.py`

```python
"""material_events + insider_transactions

Revision ID: b7e2c9f4a1d3
Revises: d9659a472017
Create Date: 2026-06-10
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b7e2c9f4a1d3"
down_revision: Union[str, None] = "d9659a472017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "material_events",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "filing_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("filings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ticker", sa.String(16), nullable=False),
        sa.Column("item_codes", sa.String(128), nullable=True),
        sa.Column("event_type", sa.String(16), nullable=False),
        sa.Column("materiality", sa.String(8), nullable=False),
        sa.Column("headline", sa.String(256), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("filing_date", sa.Date(), nullable=False),
        sa.Column("classified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("filing_id", name="uq_material_events_filing"),
    )
    op.create_index("ix_material_events_filing_id", "material_events", ["filing_id"])
    op.create_index("ix_material_events_ticker", "material_events", ["ticker"])
    op.create_index(
        "ix_material_events_ticker_date", "material_events", ["ticker", "filing_date"]
    )

    op.create_table(
        "insider_transactions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("ticker", sa.String(16), nullable=False),
        sa.Column("insider_name", sa.String(256), nullable=False),
        sa.Column("insider_title", sa.String(256), nullable=True),
        sa.Column("transaction_type", sa.String(64), nullable=True),
        sa.Column("direction", sa.String(8), nullable=False),
        sa.Column("transaction_date", sa.Date(), nullable=True),
        sa.Column("shares", sa.Numeric(), nullable=True),
        sa.Column("price", sa.Numeric(), nullable=True),
        sa.Column("shares_owned_after", sa.Numeric(), nullable=True),
        sa.Column("accession_number", sa.String(32), nullable=True),
        sa.Column("sec_link", sa.String(512), nullable=True),
        sa.Column("natural_key", sa.String(64), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "natural_key", name="uq_insider_transactions_natural_key"
        ),
    )
    op.create_index("ix_insider_transactions_ticker", "insider_transactions", ["ticker"])
    op.create_index(
        "ix_insider_transactions_ticker_date",
        "insider_transactions",
        ["ticker", "transaction_date"],
    )


def downgrade() -> None:
    op.drop_table("insider_transactions")
    op.drop_table("material_events")
```

- [ ] **Step 5: Run the migration**

```bash
cd backend && venv/bin/alembic upgrade head && cd ..
```

Expected: `Running upgrade d9659a472017 -> b7e2c9f4a1d3`.

- [ ] **Step 6: Verify model import wiring**

```bash
backend/venv/bin/python -c "from backend.app.models import MaterialEvent, InsiderTransaction; print('ok')"
```

Expected: `ok`.

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/material_event.py backend/app/models/insider_transaction.py backend/app/models/__init__.py backend/migrations/versions/b7e2c9f4a1d3_material_events_insider_transactions.py
git commit -m "feat(events): material_events + insider_transactions tables"
```

---

### Task 3: Insider aggregate + modifier (pure functions, TDD)

**Files:**
- Create: `backend/app/services/insider_signal.py`
- Test: `backend/tests/test_insider_signal.py`

- [ ] **Step 1: Write the failing tests** — `backend/tests/test_insider_signal.py`

```python
"""Pins the 90-day insider aggregate + discovery modifier semantics
(spec: docs/superpowers/specs/2026-06-10-material-events-design.md)."""

import os
import unittest
from datetime import date
from types import SimpleNamespace

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("SEC_USER_AGENT", "test")
os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

from backend.app.services.insider_signal import (
    compute_insider_aggregate,
    modifier_from_aggregate,
    signal_value,
)

TODAY = date(2026, 6, 10)


def tx(direction="buy", days_ago=5, shares=100, price=10.0, insider="Alice"):
    from datetime import timedelta
    return SimpleNamespace(
        direction=direction,
        transaction_date=TODAY - timedelta(days=days_ago),
        shares=shares,
        price=price,
        insider_name=insider,
    )


class AggregateTests(unittest.TestCase):
    def test_empty_input(self):
        agg = compute_insider_aggregate([], TODAY)
        self.assertEqual(agg.buy_count, 0)
        self.assertEqual(agg.sell_count, 0)
        self.assertIsNone(agg.net_value)
        self.assertFalse(agg.cluster_buy)

    def test_other_direction_excluded(self):
        agg = compute_insider_aggregate([tx(direction="other")], TODAY)
        self.assertEqual(agg.buy_count, 0)
        self.assertIsNone(agg.net_value)

    def test_outside_window_excluded(self):
        agg = compute_insider_aggregate([tx(days_ago=120)], TODAY)
        self.assertEqual(agg.buy_count, 0)

    def test_null_date_excluded(self):
        t = tx()
        t.transaction_date = None
        agg = compute_insider_aggregate([t], TODAY)
        self.assertEqual(agg.buy_count, 0)

    def test_net_value_buy_minus_sell(self):
        agg = compute_insider_aggregate(
            [tx(shares=100, price=10.0), tx(direction="sell", shares=30, price=10.0, insider="Bob")],
            TODAY,
        )
        self.assertEqual(agg.buy_count, 1)
        self.assertEqual(agg.sell_count, 1)
        self.assertAlmostEqual(agg.net_value, 700.0)

    def test_null_price_counts_but_no_value(self):
        # spec: null-price rows count toward counts but not net_value
        agg = compute_insider_aggregate([tx(price=None)], TODAY)
        self.assertEqual(agg.buy_count, 1)
        self.assertIsNone(agg.net_value)

    def test_cluster_two_distinct_buyers_within_30d(self):
        agg = compute_insider_aggregate(
            [tx(insider="Alice", days_ago=5), tx(insider="Bob", days_ago=20)], TODAY
        )
        self.assertTrue(agg.cluster_buy)

    def test_no_cluster_same_buyer_twice(self):
        agg = compute_insider_aggregate(
            [tx(insider="Alice", days_ago=5), tx(insider="Alice", days_ago=10)], TODAY
        )
        self.assertFalse(agg.cluster_buy)

    def test_no_cluster_buyers_more_than_30d_apart(self):
        agg = compute_insider_aggregate(
            [tx(insider="Alice", days_ago=2), tx(insider="Bob", days_ago=80)], TODAY
        )
        self.assertFalse(agg.cluster_buy)


class ModifierTests(unittest.TestCase):
    def test_cluster_buy_plus_5(self):
        agg = compute_insider_aggregate(
            [tx(insider="Alice"), tx(insider="Bob", days_ago=8)], TODAY
        )
        self.assertEqual(modifier_from_aggregate(agg), 5)

    def test_net_buying_plus_2(self):
        agg = compute_insider_aggregate([tx(insider="Alice")], TODAY)
        self.assertEqual(modifier_from_aggregate(agg), 2)

    def test_buys_with_null_price_still_plus_2(self):
        agg = compute_insider_aggregate([tx(price=None)], TODAY)
        self.assertEqual(modifier_from_aggregate(agg), 2)

    def test_pronounced_selling_minus_3(self):
        sells = [
            tx(direction="sell", insider=name, shares=100_000, price=20.0)
            for name in ("A", "B", "C")
        ]
        agg = compute_insider_aggregate(sells, TODAY)
        self.assertEqual(modifier_from_aggregate(agg), -3)

    def test_mild_selling_zero(self):
        # below the -$1M threshold OR fewer than 3 sellers → 0
        agg = compute_insider_aggregate(
            [tx(direction="sell", shares=100, price=10.0)], TODAY
        )
        self.assertEqual(modifier_from_aggregate(agg), 0)

    def test_empty_zero(self):
        agg = compute_insider_aggregate([], TODAY)
        self.assertEqual(modifier_from_aggregate(agg), 0)


class SignalValueTests(unittest.TestCase):
    def test_jsonb_payload_shape(self):
        agg = compute_insider_aggregate([tx()], TODAY)
        value = signal_value(agg)
        for key in (
            "buy_count", "sell_count", "distinct_buyers", "distinct_sellers",
            "net_value", "cluster_buy", "window_days", "modifier",
        ):
            self.assertIn(key, value)
        self.assertEqual(value["modifier"], 2)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify failure**

```bash
backend/venv/bin/python -m unittest backend.tests.test_insider_signal -v
```

Expected: `ModuleNotFoundError: No module named 'backend.app.services.insider_signal'`.

- [ ] **Step 3: Implement `backend/app/services/insider_signal.py`**

```python
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
```

- [ ] **Step 4: Run tests**

```bash
backend/venv/bin/python -m unittest backend.tests.test_insider_signal -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/insider_signal.py backend/tests/test_insider_signal.py
git commit -m "feat(events): insider aggregate + discovery modifier (pure functions)"
```

---

### Task 4: Form 4 ingest service (mapping, natural key, upsert — TDD)

**Files:**
- Create: `backend/app/services/insider_ingest.py`
- Test: `backend/tests/test_insider_ingest.py`

⚠️ Apply any wire-key corrections from Task 1 before writing `_map_fmp_row`.

- [ ] **Step 1: Write the failing tests** — `backend/tests/test_insider_ingest.py`

```python
"""Pins FMP Form 4 row normalization, the natural-key dedupe, and the
idempotent upsert (re-ingest of identical rows adds nothing)."""

import os
import unittest
from datetime import date
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("SEC_USER_AGENT", "test")
os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

from backend.app.models.insider_transaction import InsiderTransaction
from backend.app.services.insider_ingest import (
    _accession_from_link,
    _direction,
    _map_fmp_row,
    _natural_key,
    upsert_insider_transactions,
)

ROW = {
    "symbol": "NVDA",
    "reportingName": "HUANG JEN HSUN",
    "typeOfOwner": "officer: CEO",
    "transactionType": "S-Sale",
    "transactionDate": "2026-06-01",
    "securitiesTransacted": 1000,
    "price": 120.5,
    "securitiesOwned": 75000000,
    "url": "https://www.sec.gov/Archives/edgar/data/1045810/000104581026000123/0001045810-26-000123-index.htm",
}


class DirectionTests(unittest.TestCase):
    def test_purchase_is_buy(self):
        self.assertEqual(_direction("P-Purchase"), "buy")

    def test_sale_is_sell(self):
        self.assertEqual(_direction("S-Sale"), "sell")

    def test_award_exercise_gift_are_other(self):
        for code in ("A-Award", "M-Exempt", "G-Gift", "F-InKind", None, ""):
            self.assertEqual(_direction(code), "other")


class AccessionTests(unittest.TestCase):
    def test_extracts_dashed_accession(self):
        self.assertEqual(
            _accession_from_link(ROW["url"]), "0001045810-26-000123"
        )

    def test_none_when_absent(self):
        self.assertIsNone(_accession_from_link("https://example.com/x.htm"))
        self.assertIsNone(_accession_from_link(None))


class MappingTests(unittest.TestCase):
    def test_maps_all_fields(self):
        kwargs = _map_fmp_row("NVDA", ROW)
        self.assertEqual(kwargs["ticker"], "NVDA")
        self.assertEqual(kwargs["insider_name"], "HUANG JEN HSUN")
        self.assertEqual(kwargs["insider_title"], "officer: CEO")
        self.assertEqual(kwargs["transaction_type"], "S-Sale")
        self.assertEqual(kwargs["direction"], "sell")
        self.assertEqual(kwargs["transaction_date"], date(2026, 6, 1))
        self.assertEqual(kwargs["shares"], 1000)
        self.assertEqual(kwargs["price"], 120.5)
        self.assertEqual(kwargs["shares_owned_after"], 75000000)
        self.assertEqual(kwargs["accession_number"], "0001045810-26-000123")
        self.assertTrue(kwargs["sec_link"].startswith("https://www.sec.gov/"))
        self.assertEqual(len(kwargs["natural_key"]), 64)

    def test_bad_date_maps_to_none(self):
        kwargs = _map_fmp_row("NVDA", {**ROW, "transactionDate": "garbage"})
        self.assertIsNone(kwargs["transaction_date"])

    def test_natural_key_deterministic_and_distinct(self):
        a = _natural_key("NVDA", ROW)
        b = _natural_key("NVDA", dict(ROW))
        c = _natural_key("NVDA", {**ROW, "securitiesTransacted": 999})
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)


class UpsertTests(unittest.IsolatedAsyncioTestCase):
    async def test_skips_existing_keys_adds_new(self):
        added: list[object] = []
        db = MagicMock()
        db.add = MagicMock(side_effect=added.append)

        existing_key = _natural_key("NVDA", ROW)
        result = MagicMock()
        result.scalars.return_value.all.return_value = [existing_key]
        db.execute = AsyncMock(return_value=result)

        new_row = {**ROW, "transactionDate": "2026-06-05", "transactionType": "P-Purchase"}
        summary = await upsert_insider_transactions(
            db, "NVDA", [ROW, new_row]
        )

        self.assertEqual(summary["added"], 1)
        self.assertEqual(summary["skipped_existing"], 1)
        self.assertEqual(len(added), 1)
        self.assertIsInstance(added[0], InsiderTransaction)
        self.assertEqual(added[0].direction, "buy")

    async def test_empty_rows_no_db_calls(self):
        db = MagicMock()
        db.execute = AsyncMock()
        summary = await upsert_insider_transactions(db, "NVDA", [])
        self.assertEqual(summary["added"], 0)
        db.execute.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify failure**

```bash
backend/venv/bin/python -m unittest backend.tests.test_insider_ingest -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `backend/app/services/insider_ingest.py`**

```python
"""Form 4 insider-transaction ingest — FMP-primary, EDGAR-traceable.

Maps `FMPClient.get_insider_trading` rows into insider_transactions with a
sha256 natural key for idempotent re-ingest. Wire keys live-verified
2026-06-10 (see plan Task 1); adjust _FIELDS if FMP renames.
Service is commit-free — callers own the session (peer_sets convention).
"""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.insider_transaction import InsiderTransaction

logger = logging.getLogger(__name__)

# Dashed accession number anywhere in the SEC link.
_ACCESSION_RE = re.compile(r"(\d{10}-\d{2}-\d{6})")

# Fields that identify a transaction line for dedupe purposes.
# Wire keys live-verified 2026-06-10: the SEC link field is `url`.
_KEY_FIELDS = (
    "reportingName", "transactionDate", "transactionType",
    "securitiesTransacted", "price", "url",
)


def _direction(transaction_type: str | None) -> str:
    """Open-market purchase/sale only; everything else is 'other'."""
    code = (transaction_type or "").strip().upper()
    if code.startswith("P"):
        return "buy"
    if code.startswith("S"):
        return "sell"
    return "other"


def _accession_from_link(link: str | None) -> str | None:
    if not link:
        return None
    m = _ACCESSION_RE.search(link)
    return m.group(1) if m else None


def _natural_key(ticker: str, row: dict) -> str:
    raw = "|".join([ticker.upper()] + [str(row.get(f)) for f in _KEY_FIELDS])
    return hashlib.sha256(raw.encode()).hexdigest()


def _parse_date(s: object) -> date | None:
    try:
        return date.fromisoformat(str(s)[:10])
    except (ValueError, TypeError):
        return None


def _num(v: object) -> float | None:
    try:
        return float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _map_fmp_row(ticker: str, row: dict) -> dict:
    """InsiderTransaction kwargs from one FMP insider-trading/search row."""
    link = row.get("url") or row.get("link")  # live key is `url` (verified 2026-06-10)
    return {
        "ticker": ticker.upper(),
        "insider_name": str(row.get("reportingName") or "unknown")[:256],
        "insider_title": (str(row["typeOfOwner"])[:256] if row.get("typeOfOwner") else None),
        "transaction_type": (str(row["transactionType"])[:64] if row.get("transactionType") else None),
        "direction": _direction(row.get("transactionType")),
        "transaction_date": _parse_date(row.get("transactionDate")),
        "shares": _num(row.get("securitiesTransacted")),
        "price": _num(row.get("price")),
        "shares_owned_after": _num(row.get("securitiesOwned")),
        "accession_number": _accession_from_link(link),
        "sec_link": (str(link)[:512] if link else None),
        "natural_key": _natural_key(ticker, row),
    }


async def upsert_insider_transactions(
    db: AsyncSession, ticker: str, rows: list[dict]
) -> dict:
    """Insert rows whose natural_key isn't present yet. Commit-free."""
    summary = {"ticker": ticker.upper(), "added": 0, "skipped_existing": 0}
    if not rows:
        return summary

    mapped = [_map_fmp_row(ticker, r) for r in rows]
    keys = [m["natural_key"] for m in mapped]
    existing_result = await db.execute(
        select(InsiderTransaction.natural_key).where(
            InsiderTransaction.natural_key.in_(keys)
        )
    )
    existing = set(existing_result.scalars().all())

    seen: set[str] = set()
    for m in mapped:
        key = m["natural_key"]
        if key in existing or key in seen:
            summary["skipped_existing"] += 1
            continue
        seen.add(key)
        db.add(InsiderTransaction(**m))
        summary["added"] += 1
    return summary
```

- [ ] **Step 4: Run tests**

```bash
backend/venv/bin/python -m unittest backend.tests.test_insider_ingest -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/insider_ingest.py backend/tests/test_insider_ingest.py
git commit -m "feat(events): Form 4 ingest — FMP row mapping + natural-key upsert"
```

(Include the Task 1 key dump in the commit body.)

---

### Task 5: 8-K event classifier (prefilter + Haiku, TDD)

**Files:**
- Create: `backend/app/services/event_classifier.py`
- Test: `backend/tests/test_event_classifier.py`

- [ ] **Step 1: Write the failing tests** — `backend/tests/test_event_classifier.py`

```python
"""Pins the 8-K item-code prefilter and the Haiku classification parse path.
Prefilter spec: skip filings whose item set is a non-empty subset of
{7.01, 9.01}; an EMPTY items string means missing metadata → classify."""

import os
import unittest
from unittest.mock import AsyncMock, patch

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("SEC_USER_AGENT", "test")
os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

from backend.app.services.event_classifier import (
    EventClassification,
    classify_8k,
    should_classify,
)


class PrefilterTests(unittest.TestCase):
    def test_regfd_only_skipped(self):
        self.assertFalse(should_classify("7.01"))

    def test_exhibits_only_skipped(self):
        self.assertFalse(should_classify("9.01"))

    def test_regfd_plus_exhibits_skipped(self):
        self.assertFalse(should_classify("7.01,9.01"))

    def test_earnings_8k_kept(self):
        # 2.02 must NOT be skipped — guidance changes live there (spec)
        self.assertTrue(should_classify("2.02,9.01"))

    def test_personnel_kept(self):
        self.assertTrue(should_classify("5.02"))

    def test_empty_or_none_kept(self):
        self.assertTrue(should_classify(""))
        self.assertTrue(should_classify(None))


class ClassifyTests(unittest.IsolatedAsyncioTestCase):
    async def test_parses_valid_response(self):
        raw = (
            '{"event_type": "personnel", "materiality": "high",'
            ' "headline": "CFO resigns effective immediately",'
            ' "summary": "The company announced its CFO resigned."}'
        )
        with patch(
            "backend.app.services.event_classifier.complete",
            new=AsyncMock(return_value=raw),
        ):
            result, err = await classify_8k(
                ticker="NVDA", filing_date="2026-06-09",
                item_codes="5.02", text="<html>CFO resigns</html>",
            )
        self.assertIsNone(err)
        self.assertIsInstance(result, EventClassification)
        self.assertEqual(result.event_type, "personnel")
        self.assertEqual(result.materiality, "high")

    async def test_unknown_event_type_normalizes_to_other(self):
        raw = (
            '{"event_type": "weird", "materiality": "low",'
            ' "headline": "h", "summary": "s"}'
        )
        with patch(
            "backend.app.services.event_classifier.complete",
            new=AsyncMock(return_value=raw),
        ):
            result, err = await classify_8k(
                ticker="NVDA", filing_date="2026-06-09", item_codes="", text="x",
            )
        self.assertIsNone(err)
        self.assertEqual(result.event_type, "other")

    async def test_invalid_materiality_is_error(self):
        raw = (
            '{"event_type": "guidance", "materiality": "extreme",'
            ' "headline": "h", "summary": "s"}'
        )
        with patch(
            "backend.app.services.event_classifier.complete",
            new=AsyncMock(return_value=raw),
        ):
            result, err = await classify_8k(
                ticker="NVDA", filing_date="2026-06-09", item_codes="", text="x",
            )
        self.assertIsNone(result)
        self.assertIn("materiality", err)

    async def test_call_failure_returns_error_not_raise(self):
        with patch(
            "backend.app.services.event_classifier.complete",
            new=AsyncMock(side_effect=RuntimeError("api down")),
        ):
            result, err = await classify_8k(
                ticker="NVDA", filing_date="2026-06-09", item_codes="", text="x",
            )
        self.assertIsNone(result)
        self.assertIn("haiku_call_failed", err)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify failure**

```bash
backend/venv/bin/python -m unittest backend.tests.test_event_classifier -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `backend/app/services/event_classifier.py`**

```python
"""8-K event classifier — item-code prefilter + one Haiku call per filing.

Same structured-output pattern as edgar_relationships.py: `complete()` with
an assistant prefill, parsed via parse_structured_output. Never raises —
all error paths return (None, error_string).
"""
from __future__ import annotations

import logging

from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

from backend.app.graph.llm import HAIKU, complete
from backend.app.graph.output_parser import parse_structured_output

logger = logging.getLogger(__name__)

# Items that are pure noise on their own: Reg FD disclosure + exhibits.
# 2.02 (results) is deliberately NOT here — guidance changes arrive in
# earnings 8-Ks; materiality is the gate for those, not the prefilter.
SKIPPABLE_ITEMS = {"7.01", "9.01"}

# Same per-document budget as relationship extraction (~3.5K tokens).
DOC_CHAR_BUDGET = 15000

ALLOWED_EVENT_TYPES = ("guidance", "personnel", "ma", "financing", "other")
ALLOWED_MATERIALITY = ("high", "medium", "low")


class EventClassification(BaseModel):
    event_type: str = Field(
        ..., description="One of: guidance, personnel, ma, financing, other."
    )
    materiality: str = Field(..., description="One of: high, medium, low.")
    headline: str = Field(
        ..., description="One factual line, max ~120 chars, no ticker prefix."
    )
    summary: str = Field(..., description="1-2 sentences. What happened and why it matters.")


def should_classify(item_codes: str | None) -> bool:
    """False only when the filing discloses a NON-EMPTY subset of
    {7.01, 9.01}. Empty/missing items = missing metadata → classify."""
    items = {c.strip() for c in (item_codes or "").split(",") if c.strip()}
    if not items:
        return True
    return not items.issubset(SKIPPABLE_ITEMS)


_SYSTEM_PROMPT = """You classify SEC 8-K filings for a personal stock-research dashboard. Given the filing text, output the dominant event type, its materiality to an investor with a long thesis on the stock, a one-line headline, and a 1-2 sentence summary.

event_type — pick the dominant one:
- guidance: changes to financial guidance or outlook, preliminary results, earnings releases that raise/cut/introduce guidance
- personnel: executive or director departures, appointments, terminations (Item 5.02)
- ma: mergers, acquisitions, divestitures, material definitive agreements tied to M&A
- financing: debt issuance, credit agreements, equity offerings, buyback or dividend changes
- other: anything else (legal, restructuring, listing matters, routine items)

materiality:
- high: likely to move the stock or change an investment thesis — guidance cuts/raises, CEO/CFO departure, M&A announcement, bankruptcy, restatement, delisting notice
- medium: noteworthy but not thesis-changing on its own
- low: administrative or mechanical — routine earnings 8-K with no guidance change, housekeeping amendments, annual-meeting vote results

Rules:
- Judge ONLY from the provided text. Do not use background knowledge about the company.
- headline: one factual line (max ~120 characters). No editorializing.
- summary: 1-2 sentences, concrete (names, numbers, dates from the text).

Output strict JSON:
{
  "event_type": "guidance|personnel|ma|financing|other",
  "materiality": "high|medium|low",
  "headline": "string",
  "summary": "string"
}"""

_USER_TEMPLATE = """Ticker: {ticker}
Form: 8-K filed {filing_date}
Item codes: {item_codes}

Filing text (possibly truncated to {budget} chars):
\"\"\"
{text}
\"\"\"

Classify this 8-K. Output the JSON object described in the system prompt."""


def _strip_html(text: str) -> str:
    """8-K primary documents are HTML; send Haiku visible text only."""
    try:
        return BeautifulSoup(text, "lxml").get_text(" ", strip=True)
    except Exception:
        return text


async def classify_8k(
    *, ticker: str, filing_date: str, item_codes: str | None, text: str
) -> tuple[EventClassification | None, str | None]:
    plain = _strip_html(text)[:DOC_CHAR_BUDGET]
    prompt = _USER_TEMPLATE.format(
        ticker=ticker.upper(),
        filing_date=filing_date,
        item_codes=item_codes or "unknown",
        budget=DOC_CHAR_BUDGET,
        text=plain,
    )
    try:
        raw = await complete(
            system=_SYSTEM_PROMPT,
            user=prompt,
            model=HAIKU,
            max_tokens=600,
            assistant_prefill='{"event_type":',
        )
    except Exception as e:
        logger.warning("8-K classify call failed for %s: %s", ticker, e)
        return None, f"haiku_call_failed: {e}"

    parsed, err = parse_structured_output(raw, EventClassification)
    if parsed is None:
        logger.warning("8-K classify parse failed for %s: %s; raw head: %r",
                       ticker, err, raw[:300])
        return None, err or "unknown_parse_error"

    event_type = parsed.event_type.strip().lower()
    if event_type not in ALLOWED_EVENT_TYPES:
        event_type = "other"
    materiality = parsed.materiality.strip().lower()
    if materiality not in ALLOWED_MATERIALITY:
        # Don't guess a grade — error means "retry next run" (no tombstone).
        return None, f"invalid materiality: {parsed.materiality!r}"

    return EventClassification(
        event_type=event_type,
        materiality=materiality,
        headline=parsed.headline.strip()[:256],
        summary=parsed.summary.strip(),
    ), None
```

- [ ] **Step 4: Run tests**

```bash
backend/venv/bin/python -m unittest backend.tests.test_event_classifier -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/event_classifier.py backend/tests/test_event_classifier.py
git commit -m "feat(events): 8-K item-code prefilter + Haiku classifier"
```

---

### Task 6: Scan orchestrator — 8-K flow, universe, insider signal persist (TDD)

**Files:**
- Create: `backend/app/services/material_events_scheduler.py`
- Test: `backend/tests/test_material_events_scheduler.py`

- [ ] **Step 1: Write the failing tests** — `backend/tests/test_material_events_scheduler.py`

```python
"""Pins the daily material scan internals: recent-8-K extraction from the
submissions feed, accession-dedupe idempotency (classifier never re-invoked
for an existing event), and the insider-signal persist (delete-then-add +
history dual-write, mirroring _persist_signal_set)."""

import os
import unittest
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("SEC_USER_AGENT", "test")
os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

from backend.app.models.signal import Signal
from backend.app.models.signal_history import SignalHistory
from backend.app.services.material_events_scheduler import (
    _persist_insider_signal,
    _recent_8ks,
    _scan_ticker_8ks,
)

SUBMISSIONS = {
    "filings": {
        "recent": {
            "form": ["8-K", "10-Q", "8-K", "8-K"],
            "accessionNumber": ["0001-26-000001", "0001-26-000002", "0001-26-000003", "0001-26-000004"],
            "primaryDocument": ["a.htm", "b.htm", "c.htm", "d.htm"],
            "filingDate": ["2026-06-08", "2026-06-05", "2026-06-01", "2026-01-15"],
            "items": ["5.02", "", "7.01,9.01", "2.02,9.01"],
        }
    }
}


class Recent8KTests(unittest.TestCase):
    def test_filters_form_and_window(self):
        out = _recent_8ks(SUBMISSIONS, since=date(2026, 5, 28))
        # 10-Q excluded; the January 8-K is outside the window.
        self.assertEqual(
            [c["accession_number"] for c in out],
            ["0001-26-000001", "0001-26-000003"],
        )
        self.assertEqual(out[0]["item_codes"], "5.02")
        self.assertEqual(out[0]["filing_date"], date(2026, 6, 8))

    def test_empty_submissions(self):
        self.assertEqual(_recent_8ks({}, since=date(2026, 5, 28)), [])


class ScanTicker8KTests(unittest.IsolatedAsyncioTestCase):
    async def test_existing_accession_skips_classifier(self):
        edgar = MagicMock()
        edgar.get_submissions = AsyncMock(return_value=(SUBMISSIONS, MagicMock()))
        edgar.fetch_document = AsyncMock(return_value=("<html>x</html>", MagicMock()))

        db = MagicMock()
        existing = MagicMock()
        existing.first.return_value = ("some-id",)  # every accession already has an event
        db.execute = AsyncMock(return_value=existing)

        with patch(
            "backend.app.services.material_events_scheduler.classify_8k",
            new=AsyncMock(),
        ) as mock_classify:
            counts = await _scan_ticker_8ks(
                ticker="NVDA", cik="0001045810", edgar=edgar, db=db,
                since=date(2026, 5, 28),
            )

        mock_classify.assert_not_awaited()
        self.assertEqual(counts["events_created"], 0)
        # 5.02 8-K dedupe-skipped; 7.01,9.01 8-K prefilter-skipped
        self.assertEqual(counts["skipped_existing"], 1)
        self.assertEqual(counts["skipped_prefilter"], 1)

    async def test_new_8k_creates_event(self):
        edgar = MagicMock()
        edgar.get_submissions = AsyncMock(return_value=(SUBMISSIONS, MagicMock()))
        edgar.fetch_document = AsyncMock(return_value=("<html>CFO out</html>", MagicMock()))

        added: list[object] = []
        db = MagicMock()
        db.add = MagicMock(side_effect=added.append)
        no_hit = MagicMock()
        no_hit.first.return_value = None
        no_hit.scalar_one_or_none.return_value = None  # for _upsert_filing's SELECT
        db.execute = AsyncMock(return_value=no_hit)
        db.flush = AsyncMock()

        from backend.app.services.event_classifier import EventClassification
        classification = EventClassification(
            event_type="personnel", materiality="high",
            headline="CFO resigns", summary="The CFO resigned.",
        )
        with patch(
            "backend.app.services.material_events_scheduler.classify_8k",
            new=AsyncMock(return_value=(classification, None)),
        ):
            counts = await _scan_ticker_8ks(
                ticker="NVDA", cik="0001045810", edgar=edgar, db=db,
                since=date(2026, 5, 28),
            )

        self.assertEqual(counts["events_created"], 1)
        from backend.app.models.material_event import MaterialEvent
        events = [a for a in added if isinstance(a, MaterialEvent)]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, "personnel")
        self.assertEqual(events[0].ticker, "NVDA")


class PersistInsiderSignalTests(unittest.IsolatedAsyncioTestCase):
    async def test_delete_then_add_signal_and_history(self):
        added: list[object] = []
        deletes: list[object] = []
        db = MagicMock()
        db.add = MagicMock(side_effect=added.append)
        db.execute = AsyncMock(side_effect=lambda stmt: deletes.append(stmt) or MagicMock())

        now = datetime(2026, 6, 10, 6, 30, tzinfo=timezone.utc)
        value = {"buy_count": 1, "modifier": 2}
        await _persist_insider_signal(
            db=db, ticker="NVDA",
            theme_id="00000000-0000-0000-0000-000000000001",
            value=value, computed_at=now,
        )

        self.assertEqual(len(deletes), 1)
        signals = [a for a in added if isinstance(a, Signal)]
        history = [a for a in added if isinstance(a, SignalHistory)]
        self.assertEqual(len(signals), 1)
        self.assertEqual(len(history), 1)
        self.assertEqual(signals[0].signal_type, "insider")
        self.assertEqual(signals[0].value, value)
        self.assertEqual(signals[0].computed_at, now)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify failure**

```bash
backend/venv/bin/python -m unittest backend.tests.test_material_events_scheduler -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `backend/app/services/material_events_scheduler.py`**

```python
"""Daily material-events scan: 8-K classification + Form 4 insider ingest.

Universe = theme seed_tickers ∪ active-thesis tickers (the calendar's
definition — same private import of the status board's latest-runs SQL,
which owns the "active thesis" semantics).

Fanout-style isolation: each ticker runs in its own async_session() with an
explicit commit; per-ticker errors land in summary["errors"] and never abort
the loop. EDGAR rate limiting lives inside EdgarClient._throttle().
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.clients.edgar import EdgarClient
from backend.app.clients.fmp import FMPClient
from backend.app.db import async_session
from backend.app.models.filing import Filing
from backend.app.models.insider_transaction import InsiderTransaction
from backend.app.models.material_event import MaterialEvent
from backend.app.models.signal import Signal
from backend.app.models.signal_history import SignalHistory
from backend.app.models.theme import Theme
from backend.app.services.edgar_sections_ingest import _upsert_filing
from backend.app.services.event_classifier import classify_8k, should_classify
from backend.app.services.insider_ingest import upsert_insider_transactions
from backend.app.services.insider_signal import (
    WINDOW_DAYS,
    compute_insider_aggregate,
    signal_value,
)

logger = logging.getLogger(__name__)

# Bounds the first run; accession dedupe makes every later run idempotent.
LOOKBACK_DAYS = 14
# FMP default limit (20) is too small for a 90-day window on active names.
FMP_INSIDER_LIMIT = 100


# ── Universe ──────────────────────────────────────────────────────────────────


async def _theme_universe(db: AsyncSession) -> dict[str, set[str]]:
    """theme_id -> tickers (seeds ∪ that theme's active-thesis tickers)."""
    # Private import is deliberate — same pattern + rationale as
    # calendar_events.get_universe: the status board owns "active thesis".
    from backend.app.services.status_board import _build_latest_runs_sql  # noqa: PLC0415

    out: dict[str, set[str]] = {}
    themes = (await db.execute(select(Theme))).scalars().all()
    for t in themes:
        seeds = t.seed_tickers if isinstance(t.seed_tickers, list) else []
        out[str(t.id)] = {str(s).upper() for s in seeds}

    sql, params = _build_latest_runs_sql(theme_id=None, include_archived=False)
    for r in (await db.execute(text(sql), params)).mappings().all():
        out.setdefault(str(r["theme_id"]), set()).add(str(r["ticker"]).upper())
    return out


# ── 8-K flow ──────────────────────────────────────────────────────────────────


def _recent_8ks(submissions: dict, since: date) -> list[dict]:
    """Plain-8-K entries from the submissions feed filed on/after `since`.
    (8-K/A amendments are out of scope for v1.)"""
    recent = submissions.get("filings", {}).get("recent", {}) or {}
    forms = recent.get("form", []) or []
    accessions = recent.get("accessionNumber", []) or []
    docs = recent.get("primaryDocument", []) or []
    filing_dates = recent.get("filingDate", []) or []
    items_list = recent.get("items", []) or []

    out: list[dict] = []
    for i, form in enumerate(forms):
        if form != "8-K":
            continue
        try:
            fd = date.fromisoformat(filing_dates[i])
        except (ValueError, IndexError):
            continue
        if fd < since:
            continue
        out.append({
            "accession_number": accessions[i] if i < len(accessions) else None,
            "primary_document": docs[i] if i < len(docs) else None,
            "filing_date": fd,
            "item_codes": items_list[i] if i < len(items_list) else "",
        })
    return out


async def _scan_ticker_8ks(
    *, ticker: str, cik: str, edgar: EdgarClient, db: AsyncSession, since: date
) -> dict:
    """Classify new 8-Ks for one ticker. Commit-free — caller owns the session."""
    counts = {
        "events_created": 0,
        "skipped_prefilter": 0,
        "skipped_existing": 0,
        "errors": [],
    }
    submissions, _ = await edgar.get_submissions(cik)
    for c in _recent_8ks(submissions, since=since):
        accession = c["accession_number"]
        if not accession or not c["primary_document"]:
            continue
        if not should_classify(c["item_codes"]):
            counts["skipped_prefilter"] += 1
            continue

        existing = await db.execute(
            select(MaterialEvent.id)
            .join(Filing, Filing.id == MaterialEvent.filing_id)
            .where(Filing.accession_number == accession)
            .limit(1)
        )
        if existing.first() is not None:
            counts["skipped_existing"] += 1
            continue

        doc_url = (
            f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
            f"{accession.replace('-', '')}/{c['primary_document']}"
        )
        doc_text, _ = await edgar.fetch_document(doc_url)
        classification, err = await classify_8k(
            ticker=ticker,
            filing_date=c["filing_date"].isoformat(),
            item_codes=c["item_codes"],
            text=doc_text,
        )
        if classification is None:
            # No tombstone on failure — retried on the next run.
            counts["errors"].append(f"{accession}: {err}")
            continue

        filing = await _upsert_filing(
            db,
            ticker=ticker,
            cik=cik,
            form_type="8-K",
            accession_number=accession,
            primary_document_url=doc_url,
            filing_date=c["filing_date"],
            period_of_report=None,
        )
        db.add(MaterialEvent(
            filing_id=filing.id,
            ticker=ticker.upper(),
            item_codes=(c["item_codes"] or None),
            event_type=classification.event_type,
            materiality=classification.materiality,
            headline=classification.headline,
            summary=classification.summary,
            filing_date=c["filing_date"],
        ))
        counts["events_created"] += 1
    return counts


# ── Insider signal persist (mirrors signal_scheduler._persist_signal_set) ────


async def _persist_insider_signal(
    *, db: AsyncSession, ticker: str, theme_id: str, value: dict,
    computed_at: datetime,
) -> None:
    await db.execute(
        delete(Signal).where(
            Signal.ticker == ticker,
            Signal.theme_id == theme_id,
            Signal.signal_type == "insider",
        )
    )
    db.add(Signal(
        ticker=ticker, theme_id=theme_id, signal_type="insider",
        value=value, computed_at=computed_at, is_stale=False,
    ))
    db.add(SignalHistory(
        ticker=ticker, theme_id=theme_id, signal_type="insider",
        value=value, computed_at=computed_at,
    ))


# ── Orchestrator ─────────────────────────────────────────────────────────────


async def run_daily_material_scan(*, edgar: EdgarClient, fmp: FMPClient) -> dict:
    """Full daily scan. Returns a summary dict for logging."""
    started = datetime.now(timezone.utc)
    summary: dict = {
        "tickers_scanned": 0,
        "events_created": 0,
        "events_skipped_prefilter": 0,
        "events_skipped_existing": 0,
        "transactions_added": 0,
        "signals_written": 0,
        "errors": [],
    }

    async with async_session() as db:
        theme_universe = await _theme_universe(db)
    all_tickers = sorted(set().union(*theme_universe.values())) if theme_universe else []
    since = date.today() - timedelta(days=LOOKBACK_DAYS)
    window_cutoff = date.today() - timedelta(days=WINDOW_DAYS)
    insider_values: dict[str, dict] = {}

    for ticker in all_tickers:
        try:
            async with async_session() as db:
                cik, _ = await edgar.get_ticker_to_cik(ticker)
                if cik:
                    counts = await _scan_ticker_8ks(
                        ticker=ticker, cik=cik, edgar=edgar, db=db, since=since
                    )
                    summary["events_created"] += counts["events_created"]
                    summary["events_skipped_prefilter"] += counts["skipped_prefilter"]
                    summary["events_skipped_existing"] += counts["skipped_existing"]
                    summary["errors"].extend(f"{ticker} {e}" for e in counts["errors"])
                else:
                    summary["errors"].append(f"{ticker}: no CIK in EDGAR ticker map")

                rows, _ = await fmp.get_insider_trading(ticker, limit=FMP_INSIDER_LIMIT)
                ins = await upsert_insider_transactions(db, ticker, rows)
                summary["transactions_added"] += ins["added"]

                window_rows = (await db.execute(
                    select(InsiderTransaction).where(
                        InsiderTransaction.ticker == ticker,
                        InsiderTransaction.transaction_date >= window_cutoff,
                    )
                )).scalars().all()
                agg = compute_insider_aggregate(window_rows, date.today())
                insider_values[ticker] = signal_value(agg)

                await db.commit()
            summary["tickers_scanned"] += 1
        except Exception as e:
            logger.exception("material scan failed for %s", ticker)
            summary["errors"].append(f"{ticker}: {e}")

    # Signal rows per (ticker, theme) — one shared timestamp, one session.
    now = datetime.now(timezone.utc)
    try:
        async with async_session() as db:
            for theme_id, tickers in theme_universe.items():
                for t in sorted(tickers):
                    if t in insider_values:
                        await _persist_insider_signal(
                            db=db, ticker=t, theme_id=theme_id,
                            value=insider_values[t], computed_at=now,
                        )
                        summary["signals_written"] += 1
            await db.commit()
    except Exception as e:
        logger.exception("insider signal persist failed")
        summary["errors"].append(f"signal persist: {e}")

    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    logger.info("material scan complete in %.1fs: %s", elapsed, summary)
    return summary
```

- [ ] **Step 4: Run tests**

```bash
backend/venv/bin/python -m unittest backend.tests.test_material_events_scheduler -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/material_events_scheduler.py backend/tests/test_material_events_scheduler.py
git commit -m "feat(events): daily material scan orchestrator (8-K + Form 4 + insider signal)"
```

---

### Task 7: Events API router + main.py wiring (cron + manual trigger)

**Files:**
- Create: `backend/app/api/events.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_events_api.py`

- [ ] **Step 1: Write the failing tests** — `backend/tests/test_events_api.py`

```python
"""Pins the /api/events contract: list filters, dismissal, 404s, and the
fire-and-forget scan trigger."""

import os
import unittest
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("SEC_USER_AGENT", "test")
os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.events import router
from backend.app.db import get_db


def make_app() -> tuple[TestClient, MagicMock]:
    app = FastAPI()
    app.include_router(router, prefix="/api")
    db = MagicMock()

    async def _fake_db():
        yield db

    app.dependency_overrides[get_db] = _fake_db
    app.state.edgar = MagicMock()
    app.state.fmp = MagicMock()
    return TestClient(app), db


def _event(**over):
    base = dict(
        id="ev-1", ticker="NVDA", event_type="guidance", materiality="high",
        headline="Guidance cut", summary="Cut FY outlook.", item_codes="2.02",
        filing_date=date(2026, 6, 8), dismissed_at=None,
    )
    base.update(over)
    return SimpleNamespace(**base)


class ListEventsTests(unittest.TestCase):
    def test_list_returns_events(self):
        client, db = make_app()
        result = MagicMock()
        result.all.return_value = [(_event(), "https://sec.gov/doc.htm")]
        db.execute = AsyncMock(return_value=result)

        resp = client.get("/api/events?since_days=14")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["total"], 1)
        self.assertEqual(body["events"][0]["ticker"], "NVDA")
        self.assertEqual(body["events"][0]["filing_date"], "2026-06-08")
        self.assertEqual(body["events"][0]["document_url"], "https://sec.gov/doc.htm")

    def test_since_days_validation(self):
        client, _ = make_app()
        self.assertEqual(client.get("/api/events?since_days=0").status_code, 422)
        self.assertEqual(client.get("/api/events?since_days=400").status_code, 422)


class DismissTests(unittest.TestCase):
    def test_dismiss_404_unknown(self):
        client, db = make_app()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result)
        resp = client.post("/api/events/nope/dismiss")
        self.assertEqual(resp.status_code, 404)

    def test_dismiss_sets_timestamp_and_commits(self):
        client, db = make_app()
        ev = _event()
        result = MagicMock()
        result.scalar_one_or_none.return_value = ev
        db.execute = AsyncMock(return_value=result)
        db.commit = AsyncMock()

        resp = client.post("/api/events/ev-1/dismiss")
        self.assertEqual(resp.status_code, 204)
        self.assertIsNotNone(ev.dismissed_at)
        db.commit.assert_awaited()


class ScanTriggerTests(unittest.TestCase):
    def test_scan_returns_202(self):
        client, _ = make_app()
        with patch(
            "backend.app.services.material_events_scheduler.run_daily_material_scan",
            new=AsyncMock(return_value={}),
        ):
            resp = client.post("/api/events/scan")
        self.assertEqual(resp.status_code, 202)
        self.assertEqual(resp.json(), {"started": True})


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify failure**

```bash
backend/venv/bin/python -m unittest backend.tests.test_events_api -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `backend/app/api/events.py`**

NOTE: no `from __future__ import annotations` in this file (repo convention for API routers).

```python
"""Material-events endpoints.

GET  /api/events                      — classified 8-K events, filterable
POST /api/events/{event_id}/dismiss   — hide from board badge + Today
POST /api/events/scan                 — manual daily-scan trigger (202, fire-and-forget)
"""
import asyncio
import logging
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import get_db
from backend.app.models.filing import Filing
from backend.app.models.material_event import MaterialEvent

logger = logging.getLogger(__name__)

router = APIRouter()


class MaterialEventOut(BaseModel):
    id: str
    ticker: str
    event_type: str
    materiality: str
    headline: str
    summary: str
    item_codes: str | None
    filing_date: str
    document_url: str | None
    dismissed_at: str | None


class EventListResponse(BaseModel):
    events: list[MaterialEventOut]
    total: int


@router.get("/events", response_model=EventListResponse)
async def list_events(
    since_days: int = Query(default=14, ge=1, le=365),
    ticker: str | None = None,
    materiality: str | None = None,  # comma-separated, e.g. "high,medium"
    include_dismissed: bool = False,
    db: AsyncSession = Depends(get_db),
) -> EventListResponse:
    cutoff = date.today() - timedelta(days=since_days)
    stmt = (
        select(MaterialEvent, Filing.primary_document_url)
        .join(Filing, Filing.id == MaterialEvent.filing_id)
        .where(MaterialEvent.filing_date >= cutoff)
    )
    if ticker:
        stmt = stmt.where(MaterialEvent.ticker == ticker.upper())
    if materiality:
        levels = [m.strip().lower() for m in materiality.split(",") if m.strip()]
        if levels:
            stmt = stmt.where(MaterialEvent.materiality.in_(levels))
    if not include_dismissed:
        stmt = stmt.where(MaterialEvent.dismissed_at.is_(None))
    stmt = stmt.order_by(MaterialEvent.filing_date.desc(), MaterialEvent.ticker)

    rows = (await db.execute(stmt)).all()
    events = [
        MaterialEventOut(
            id=str(ev.id),
            ticker=ev.ticker,
            event_type=ev.event_type,
            materiality=ev.materiality,
            headline=ev.headline,
            summary=ev.summary,
            item_codes=ev.item_codes,
            filing_date=ev.filing_date.isoformat(),
            document_url=doc_url,
            dismissed_at=ev.dismissed_at.isoformat() if ev.dismissed_at else None,
        )
        for ev, doc_url in rows
    ]
    return EventListResponse(events=events, total=len(events))


@router.post("/events/scan", status_code=202)
async def trigger_scan(request: Request) -> dict:
    """Dev/testing convenience — cron is the primary path. Fire-and-forget;
    the summary lands in the server log."""
    edgar = request.app.state.edgar
    fmp = request.app.state.fmp

    async def _run() -> None:
        from backend.app.services.material_events_scheduler import (
            run_daily_material_scan,
        )
        try:
            summary = await run_daily_material_scan(edgar=edgar, fmp=fmp)
            logger.info("manual material scan: %s", summary)
        except Exception:
            logger.exception("manual material scan crashed")

    asyncio.create_task(_run())
    return {"started": True}


@router.post("/events/{event_id}/dismiss", status_code=204)
async def dismiss_event(event_id: str, db: AsyncSession = Depends(get_db)) -> None:
    row = (
        await db.execute(select(MaterialEvent).where(MaterialEvent.id == event_id))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Event not found")
    if row.dismissed_at is None:
        row.dismissed_at = datetime.now(timezone.utc)
        await db.commit()
```

(`/events/scan` is declared before `/events/{event_id}/dismiss` so the literal path wins — same defensive ordering as `/catalysts/calendar` and `/peers/compare`, pinned by the 202 test.)

- [ ] **Step 4: Wire into `backend/app/main.py`**

Add the import alongside the other api imports:

```python
from backend.app.api.events import router as events_router
```

Add the router registration after `app.include_router(company_router, prefix="/api")`:

```python
app.include_router(events_router, prefix="/api")
```

Add the cron job in `lifespan`, after the outcome-snapshot job and before `scheduler.start()`:

```python
    scheduler.add_job(
        _daily_material_scan_job,
        CronTrigger(hour=6, minute=30, timezone="UTC"),
        args=[app],
        id="daily_material_scan",
        name="Daily 8-K + Form 4 Scan",
        replace_existing=True,
    )
```

Update the startup log line to mention it:

```python
    logger.info(
        "Schedulers started: X signals @ 02:00 UTC, earnings @ 21:00 UTC, "
        "outcomes @ 03:00 UTC, material events @ 06:30 UTC"
    )
```

Add the job wrapper next to `_daily_earnings_refresh_job`:

```python
async def _daily_material_scan_job(app: FastAPI) -> None:
    """APScheduler entry point — wraps run_daily_material_scan with logging."""
    from backend.app.services.material_events_scheduler import run_daily_material_scan
    try:
        summary = await run_daily_material_scan(
            edgar=app.state.edgar, fmp=app.state.fmp
        )
        logger.info("Daily material scan: %s", summary)
    except Exception:
        logger.exception("Daily material scan crashed")
```

- [ ] **Step 5: Run tests + app import check**

```bash
backend/venv/bin/python -m unittest backend.tests.test_events_api -v
backend/venv/bin/python -c "from backend.app.main import app; print('app ok')"
```

Expected: all PASS; `app ok`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/events.py backend/app/main.py backend/tests/test_events_api.py
git commit -m "feat(events): /api/events router + 06:30 UTC cron + manual scan trigger"
```

---

### Task 8: Status-board material-events join (TDD)

**Files:**
- Modify: `backend/app/services/status_board.py`
- Modify: `backend/app/api/status.py`
- Test: `backend/tests/test_status_board_material_events.py`

- [ ] **Step 1: Write the failing tests** — `backend/tests/test_status_board_material_events.py`

```python
"""Pins the pure material-events summarizer the board join uses: count,
max-materiality escalation, latest-headline = first row (rows arrive
ordered filing_date DESC)."""

import os
import unittest
from datetime import date
from types import SimpleNamespace

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("SEC_USER_AGENT", "test")
os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

from backend.app.services.status_board import _summarize_material_events


def ev(ticker="NVDA", materiality="low", headline="h", days=1):
    return SimpleNamespace(
        ticker=ticker, materiality=materiality, headline=headline,
        filing_date=date(2026, 6, 10),
    )


class SummarizeTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(_summarize_material_events([]), {})

    def test_counts_and_latest_headline(self):
        # ordered DESC by filing_date — first row per ticker is the latest
        out = _summarize_material_events([
            ev(headline="newest", materiality="low"),
            ev(headline="older", materiality="high"),
        ])
        s = out["NVDA"]
        self.assertEqual(s.count_14d, 2)
        self.assertEqual(s.latest_headline, "newest")
        self.assertEqual(s.max_materiality, "high")

    def test_groups_by_ticker(self):
        out = _summarize_material_events([
            ev(ticker="NVDA"), ev(ticker="MSFT", materiality="medium"),
        ])
        self.assertEqual(set(out), {"NVDA", "MSFT"})
        self.assertEqual(out["MSFT"].max_materiality, "medium")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify failure**

```bash
backend/venv/bin/python -m unittest backend.tests.test_status_board_material_events -v
```

Expected: `ImportError: cannot import name '_summarize_material_events'`.

- [ ] **Step 3: Modify `backend/app/services/status_board.py`**

Change the datetime import line to include `timedelta`:

```python
from datetime import date, datetime, timedelta, timezone
```

Add to the model imports:

```python
from backend.app.models.material_event import MaterialEvent
```

Add below the `NextCatalyst` dataclass:

```python
EVENT_WINDOW_DAYS = 14
_MATERIALITY_RANK = {"high": 2, "medium": 1, "low": 0}


@dataclass
class MaterialEventsSummary:
    count_14d: int
    max_materiality: str  # high | medium | low
    latest_headline: str
```

Append a defaulted field to `StatusBoardEntry` (after `kill_criteria_summary`):

```python
    material_events: MaterialEventsSummary | None = None
```

Add the pure summarizer (module level, near `_build_next_catalyst`):

```python
def _summarize_material_events(events: list) -> dict[str, MaterialEventsSummary]:
    """Group undismissed events (ordered filing_date DESC) per ticker."""
    out: dict[str, MaterialEventsSummary] = {}
    for ev in events:
        s = out.get(ev.ticker)
        if s is None:
            out[ev.ticker] = MaterialEventsSummary(
                count_14d=1,
                max_materiality=ev.materiality,
                latest_headline=ev.headline,
            )
        else:
            s.count_14d += 1
            if _MATERIALITY_RANK.get(ev.materiality, 0) > _MATERIALITY_RANK.get(s.max_materiality, 0):
                s.max_materiality = ev.materiality
    return out
```

In `build_status_board`, after the workspace-run lookup block (`ws_lookup = ...`), add the one-query fetch:

```python
    # Material events (last 14 days, undismissed) for the board's tickers —
    # one query, grouped in Python; same summary on every theme row of a ticker.
    board_tickers = list({row["ticker"] for row in run_rows})
    ev_result = await db.execute(
        select(MaterialEvent)
        .where(
            MaterialEvent.ticker.in_(board_tickers),
            MaterialEvent.filing_date >= today - timedelta(days=EVENT_WINDOW_DAYS),
            MaterialEvent.dismissed_at.is_(None),
        )
        .order_by(MaterialEvent.filing_date.desc())
    )
    events_by_ticker = _summarize_material_events(list(ev_result.scalars()))
```

And in the `StatusBoardEntry(...)` constructor call, add:

```python
                material_events=events_by_ticker.get(row["ticker"]),
```

- [ ] **Step 4: Modify `backend/app/api/status.py`**

Add wire model after `NextCatalystOut`:

```python
class MaterialEventsSummaryOut(BaseModel):
    count_14d: int
    max_materiality: str
    latest_headline: str
```

Add field to `StatusBoardEntryOut`:

```python
    material_events: MaterialEventsSummaryOut | None
```

In `_serialize_entry`, add:

```python
        material_events=(
            MaterialEventsSummaryOut(
                count_14d=e.material_events.count_14d,
                max_materiality=e.material_events.max_materiality,
                latest_headline=e.material_events.latest_headline,
            )
            if e.material_events
            else None
        ),
```

- [ ] **Step 5: Run the new test + the existing board tests (regression)**

```bash
backend/venv/bin/python -m unittest backend.tests.test_status_board_material_events backend.tests.test_status_board_workspace_aware -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/status_board.py backend/app/api/status.py backend/tests/test_status_board_material_events.py
git commit -m "feat(events): material-events summary on status-board entries"
```

---

### Task 9: Discovery insider modifier + card field (TDD)

**Files:**
- Modify: `backend/app/services/discovery.py`
- Modify: `backend/app/api/discovery.py`
- Test: `backend/tests/test_discovery_insider_modifier.py`

- [ ] **Step 1: Write the failing tests** — `backend/tests/test_discovery_insider_modifier.py`

```python
"""Pins apply_insider_modifier: bounded adjustment, 48h staleness gate,
[0,100] clamp, absent/garbage data → unchanged."""

import os
import unittest
from datetime import datetime, timedelta, timezone

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("SEC_USER_AGENT", "test")
os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

from backend.app.services.discovery import apply_insider_modifier

NOW = datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)
FRESH = (NOW - timedelta(hours=6)).isoformat()
STALE = (NOW - timedelta(hours=72)).isoformat()


class ApplyInsiderModifierTests(unittest.TestCase):
    def test_fresh_positive_modifier_applied(self):
        score, mod = apply_insider_modifier(60.0, {"modifier": 5, "computed_at": FRESH}, NOW)
        self.assertEqual(score, 65.0)
        self.assertEqual(mod, 5)

    def test_stale_signal_ignored(self):
        score, mod = apply_insider_modifier(60.0, {"modifier": 5, "computed_at": STALE}, NOW)
        self.assertEqual(score, 60.0)
        self.assertEqual(mod, 0)

    def test_absent_data_unchanged(self):
        self.assertEqual(apply_insider_modifier(60.0, {}, NOW), (60.0, 0))

    def test_zero_modifier_unchanged(self):
        self.assertEqual(
            apply_insider_modifier(60.0, {"modifier": 0, "computed_at": FRESH}, NOW),
            (60.0, 0),
        )

    def test_clamped_at_100(self):
        score, _ = apply_insider_modifier(98.0, {"modifier": 5, "computed_at": FRESH}, NOW)
        self.assertEqual(score, 100.0)

    def test_clamped_at_0(self):
        score, _ = apply_insider_modifier(1.0, {"modifier": -3, "computed_at": FRESH}, NOW)
        self.assertEqual(score, 0.0)

    def test_garbage_computed_at_ignored(self):
        score, mod = apply_insider_modifier(60.0, {"modifier": 5, "computed_at": "garbage"}, NOW)
        self.assertEqual((score, mod), (60.0, 0))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify failure**

```bash
backend/venv/bin/python -m unittest backend.tests.test_discovery_insider_modifier -v
```

Expected: `ImportError`.

- [ ] **Step 3: Modify `backend/app/services/discovery.py`**

Add import near the top of the file (with the other service imports):

```python
from backend.app.services.insider_signal import INSIDER_STALE_HOURS
```

Add an `InsiderSnapshot` dataclass after `XSignalSnapshot`:

```python
@dataclass
class InsiderSnapshot:
    """Cached Form 4 signal as applied to this card. modifier is 0 when the
    signal is stale or absent (i.e., what was actually applied)."""
    modifier: int = 0
    buy_count: int = 0
    sell_count: int = 0
    cluster_buy: bool = False
    net_value: float | None = None
    is_stale: bool = True
```

Add a field to `CompanySignalCard` (after `x_signal`):

```python
    insider: InsiderSnapshot = field(default_factory=InsiderSnapshot)
```

Add the pure helper after `compute_combined_score`:

```python
def apply_insider_modifier(
    base_score: float, insider_data: dict, now: datetime
) -> tuple[float, int]:
    """Clamped combined-score adjustment from the cached insider signal.

    Bounded modifier, NOT a 4th weight (spec): insider activity is sparse —
    a weight would multiply zeros most days and force a rework of per-theme
    weights and the cold-start collapse. Stale (>48h) or absent → unchanged.
    Returns (adjusted_score, applied_modifier).
    """
    if not insider_data:
        return base_score, 0
    raw = insider_data.get("computed_at")
    try:
        computed = datetime.fromisoformat(raw) if raw else None
    except (ValueError, TypeError):
        computed = None
    if computed is None or computed < now - timedelta(hours=INSIDER_STALE_HOURS):
        return base_score, 0
    modifier = int(insider_data.get("modifier", 0) or 0)
    if modifier == 0:
        return base_score, 0
    return round(min(100.0, max(0.0, base_score + modifier)), 1), modifier
```

In `_merge_results`, after the `combined = compute_combined_score(...)` call and before `badge = ...`, add:

```python
            insider_data = ticker_signals.get("insider", {})
            combined, applied_modifier = apply_insider_modifier(
                combined, insider_data, datetime.now(timezone.utc)
            )
            insider_snap = InsiderSnapshot(
                modifier=applied_modifier,
                buy_count=int(insider_data.get("buy_count", 0) or 0),
                sell_count=int(insider_data.get("sell_count", 0) or 0),
                cluster_buy=bool(insider_data.get("cluster_buy", False)),
                net_value=insider_data.get("net_value"),
                is_stale=applied_modifier == 0 and bool(insider_data),
            )
```

And in the `CompanySignalCard(...)` constructor call, add (after `x_signal=x_snap`):

```python
                insider=insider_snap,
```

- [ ] **Step 4: Modify `backend/app/api/discovery.py`**

In `_card_to_dict`, add an `"insider"` key alongside the `"x_signal"` block:

```python
        "insider": {
            "modifier": card.insider.modifier,
            "buy_count": card.insider.buy_count,
            "sell_count": card.insider.sell_count,
            "cluster_buy": card.insider.cluster_buy,
            "net_value": card.insider.net_value,
            "is_stale": card.insider.is_stale,
        },
```

- [ ] **Step 5: Run tests**

```bash
backend/venv/bin/python -m unittest backend.tests.test_discovery_insider_modifier -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/discovery.py backend/app/api/discovery.py backend/tests/test_discovery_insider_modifier.py
git commit -m "feat(events): bounded insider modifier in discovery combined score"
```

---

### Task 10: Frontend API types + events client

**Files:**
- Modify: `frontend/lib/api.ts`
- Modify: `frontend/lib/todayDerive.test.mts` (type-completeness only)

- [ ] **Step 1: Add types + client to `frontend/lib/api.ts`**

Add to the `CompanySignalCard` interface (it's near the top, after `x_signal: XSignalSnapshot;`):

```typescript
  insider: InsiderSnapshot;
```

And define above `CompanySignalCard` (after `XSignalSnapshot`):

```typescript
export interface InsiderSnapshot {
  modifier: number;
  buy_count: number;
  sell_count: number;
  cluster_buy: boolean;
  net_value: number | null;
  is_stale: boolean;
}
```

In the status-board section, add above `StatusBoardEntry`:

```typescript
export interface MaterialEventsSummary {
  count_14d: number;
  max_materiality: "high" | "medium" | "low";
  latest_headline: string;
}
```

Add to `StatusBoardEntry` (after `kill_criteria_summary`):

```typescript
  material_events: MaterialEventsSummary | null;
```

Add the events client after the `readThroughs` const:

```typescript
// ── Material events (classified 8-Ks) ───────────────────────────────────────

export interface MaterialEvent {
  id: string;
  ticker: string;
  event_type: "guidance" | "personnel" | "ma" | "financing" | "other";
  materiality: "high" | "medium" | "low";
  headline: string;
  summary: string;
  item_codes: string | null;
  filing_date: string;
  document_url: string | null;
  dismissed_at: string | null;
}

export interface EventListResponse {
  events: MaterialEvent[];
  total: number;
}

export const events = {
  list: (params?: {
    since_days?: number;
    ticker?: string;
    materiality?: string;
    include_dismissed?: boolean;
  }) => {
    const qs = new URLSearchParams();
    if (params?.since_days) qs.set("since_days", String(params.since_days));
    if (params?.ticker) qs.set("ticker", params.ticker);
    if (params?.materiality) qs.set("materiality", params.materiality);
    if (params?.include_dismissed) qs.set("include_dismissed", "true");
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return apiFetch<EventListResponse>(`/api/events${suffix}`);
  },
  dismiss: (id: string) =>
    apiFetch<void>(`/api/events/${encodeURIComponent(id)}/dismiss`, {
      method: "POST",
    }),
};
```

- [ ] **Step 2: Fix the test helper for the widened type**

In `frontend/lib/todayDerive.test.mts`, the `entry()` factory builds a complete `StatusBoardEntry` — add to its base object:

```typescript
    material_events: null,
```

- [ ] **Step 3: Verify it compiles**

```bash
cd frontend && npm run lint && cd ..
```

Expected: clean (warnings ok, no errors).

- [ ] **Step 4: Commit**

```bash
git add frontend/lib/api.ts frontend/lib/todayDerive.test.mts
git commit -m "feat(events): frontend types + events API client"
```

---

### Task 11: Status board badge + MaterialEventsDrawer + deep link

**Files:**
- Create: `frontend/components/status/MaterialEventsDrawer.tsx`
- Modify: `frontend/app/status/page.tsx`

- [ ] **Step 1: Create `frontend/components/status/MaterialEventsDrawer.tsx`** (modeled on `ReadThroughDrawer.tsx`)

```tsx
"use client";

import { useState } from "react";
import type { MaterialEvent } from "@/lib/api";
import { events as eventsApi } from "@/lib/api";

interface Props {
  items: MaterialEvent[];
  onDismissed: (eventId: string) => void;
}

const MATERIALITY_BADGE: Record<string, string> = {
  high: "bg-rose-900/40 text-rose-200 ring-rose-700",
  medium: "bg-amber-900/40 text-amber-200 ring-amber-700",
  low: "bg-slate-800 text-slate-300 ring-slate-700",
};

const TYPE_LABEL: Record<string, string> = {
  guidance: "Guidance",
  personnel: "Personnel",
  ma: "M&A",
  financing: "Financing",
  other: "Other",
};

export function MaterialEventsDrawer({ items, onDismissed }: Props) {
  if (items.length === 0) {
    return (
      <div className="px-4 py-3 text-sm text-slate-500" data-print-hide="true">
        No material events in the last 14 days.
      </div>
    );
  }

  return (
    <div className="space-y-2 px-4 py-3" data-print-hide="true">
      {items.map((item) => (
        <EventRow key={item.id} item={item} onDismissed={onDismissed} />
      ))}
    </div>
  );
}

function EventRow({
  item,
  onDismissed,
}: {
  item: MaterialEvent;
  onDismissed: (eventId: string) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleDismiss() {
    setBusy(true);
    setError(null);
    try {
      await eventsApi.dismiss(item.id);
      onDismissed(item.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Dismiss failed");
      setBusy(false);
    }
  }

  return (
    <div className="rounded-md border border-slate-800 bg-slate-900/40 p-3 text-sm">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <span
            className={`rounded px-1.5 py-0.5 text-[11px] ring-1 shrink-0 ${
              MATERIALITY_BADGE[item.materiality] ?? MATERIALITY_BADGE.low
            }`}
          >
            {item.materiality}
          </span>
          <span className="text-slate-400 text-xs shrink-0">
            {TYPE_LABEL[item.event_type] ?? item.event_type}
          </span>
          <span className="text-slate-500 shrink-0">·</span>
          <span className="text-slate-500 text-xs shrink-0">{item.filing_date}</span>
        </div>
        <div className="flex gap-2 shrink-0">
          {item.document_url && (
            <a
              href={item.document_url}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded border border-slate-700 px-2 py-0.5 text-xs text-slate-300 hover:bg-slate-800"
            >
              Filing ↗
            </a>
          )}
          <button
            onClick={handleDismiss}
            disabled={busy}
            className="rounded border border-slate-700 px-2 py-0.5 text-xs text-slate-400 hover:bg-slate-800 disabled:opacity-50"
          >
            {busy ? "…" : "Dismiss"}
          </button>
        </div>
      </div>
      <div className="mt-1.5 font-medium text-slate-200">{item.headline}</div>
      <div className="mt-0.5 text-xs text-slate-400">{item.summary}</div>
      {error && <div className="mt-2 text-xs text-rose-400">{error}</div>}
    </div>
  );
}
```

- [ ] **Step 2: Wire into `frontend/app/status/page.tsx`**

Add imports (top of file, alongside the existing `@/lib/api` import — extend it):

```tsx
import { events as eventsApi, type MaterialEvent } from "@/lib/api";
import { MaterialEventsDrawer } from "@/components/status/MaterialEventsDrawer";
```

(If the file imports from `@/lib/api` in one statement, add `events as eventsApi` and `type MaterialEvent` to it instead of a second import.)

Add state next to the read-through state declarations:

```tsx
  const [eventsByTicker, setEventsByTicker] = useState<Record<string, MaterialEvent[]>>({});
  const [eventsExpanded, setEventsExpanded] = useState<Record<string, boolean>>({});
```

Add a fetch effect (mirror the readThroughs effect exactly — 60s poll, visibility-gated, best-effort):

```tsx
  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const out = await eventsApi.list({ since_days: 14 });
        if (cancelled) return;
        const grouped: Record<string, MaterialEvent[]> = {};
        for (const ev of out.events) {
          (grouped[ev.ticker] ??= []).push(ev);
        }
        setEventsByTicker(grouped);
      } catch {
        // best-effort — leave previous data on the screen
      }
    }
    load();
    const interval = setInterval(() => {
      if (document.visibilityState === "visible") load();
    }, 60_000);
    const onVis = () => {
      if (document.visibilityState === "visible") load();
    };
    document.addEventListener("visibilitychange", onVis);
    return () => {
      cancelled = true;
      clearInterval(interval);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, []);
```

Add the one-shot deep-link effect (below the `expand_earnings` effect, same pattern):

```tsx
  // Deep link from Today: /status?expand_events=<ticker> auto-opens that
  // ticker's MaterialEventsDrawer once board + events have loaded. One-shot.
  const expandEventsConsumed = useRef(false);
  useEffect(() => {
    if (expandEventsConsumed.current) return;
    const ticker = new URLSearchParams(window.location.search)
      .get("expand_events")
      ?.toUpperCase();
    if (!ticker || entries.length === 0) return;
    const entry = entries.find((en) => en.ticker === ticker);
    if (entry && (eventsByTicker[ticker] ?? []).length > 0) {
      expandEventsConsumed.current = true;
      setEventsExpanded((prev) => ({ ...prev, [entry.run_id]: true }));
    }
  }, [entries, eventsByTicker]);
```

Add a dismiss handler next to `handleReadThroughDismissed`:

```tsx
  function handleEventDismissed(ticker: string, eventId: string) {
    setEventsByTicker((prev) => ({
      ...prev,
      [ticker]: (prev[ticker] ?? []).filter((ev) => ev.id !== eventId),
    }));
    fetchBoard(); // refresh the badge summary
  }
```

Add the badge tint map at module level (next to the other badge maps):

```tsx
const EVENT_BADGE: Record<string, string> = {
  high: "bg-rose-900/40 text-rose-200 ring-rose-700 hover:bg-rose-900/60",
  medium: "bg-amber-900/40 text-amber-200 ring-amber-700 hover:bg-amber-900/60",
  low: "bg-slate-800 text-slate-300 ring-slate-700 hover:bg-slate-700",
};
```

In the row `actions={<>...</>}` block, after the read-through button and before the earnings IIFE, add the badge:

```tsx
                      {e.material_events && (
                        <button
                          type="button"
                          data-print-hide="true"
                          onClick={(ev) => {
                            ev.stopPropagation();
                            setEventsExpanded((m) => ({ ...m, [e.run_id]: !m[e.run_id] }));
                          }}
                          title={e.material_events.latest_headline}
                          className={`rounded px-1.5 py-0.5 text-[11px] ring-1 ${
                            EVENT_BADGE[e.material_events.max_materiality] ?? EVENT_BADGE.low
                          }`}
                        >
                          8-K ×{e.material_events.count_14d}
                        </button>
                      )}
```

After the read-through drawer block (`{isExpanded && items.length > 0 && (...)}`), add:

```tsx
                {eventsExpanded[e.run_id] && (
                  <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-alt)]">
                    <MaterialEventsDrawer
                      items={eventsByTicker[e.ticker] ?? []}
                      onDismissed={(id) => handleEventDismissed(e.ticker, id)}
                    />
                  </div>
                )}
```

- [ ] **Step 3: Lint**

```bash
cd frontend && npm run lint && cd ..
```

Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add frontend/components/status/MaterialEventsDrawer.tsx frontend/app/status/page.tsx
git commit -m "feat(events): status-board 8-K badge + MaterialEventsDrawer + expand_events deep link"
```

---

### Task 12: Today attention rows (TDD via node --test)

**Files:**
- Modify: `frontend/lib/todayDerive.ts`
- Modify: `frontend/lib/todayDerive.test.mts`
- Modify: `frontend/components/today/AttentionList.tsx`
- Modify: `frontend/app/page.tsx`

- [ ] **Step 1: Write the failing tests** — append to `frontend/lib/todayDerive.test.mts`

Add to the imports: `import type { MaterialEvent } from "./api.ts";` and a factory + tests:

```typescript
function matEvent(over: Partial<MaterialEvent>): MaterialEvent {
  return {
    id: "ev-1",
    ticker: "NVDA",
    event_type: "guidance",
    materiality: "high",
    headline: "Guidance cut",
    summary: "Cut FY outlook.",
    item_codes: "2.02",
    filing_date: "2026-06-08",
    document_url: null,
    dismissed_at: null,
    ...over,
  };
}

test("event rows slot between health rows and question rows", () => {
  const rows = deriveAttention(
    [entry({ ticker: "BROKE", health: "broken" })],
    [rollup({ ticker: "QQQ", p1_count: 1, open_count: 1 })],
    [matEvent({ ticker: "NVDA" })],
  );
  assert.deepEqual(
    rows.map((r) => r.kind),
    ["health", "event", "questions"],
  );
  const ev = rows[1];
  assert.equal(ev.kind, "event");
  if (ev.kind === "event") {
    assert.equal(ev.ticker, "NVDA");
    assert.equal(ev.severity, "amber");
    assert.equal(ev.headline, "Guidance cut");
  }
});

test("events default arg keeps old call sites working", () => {
  const rows = deriveAttention([], []);
  assert.deepEqual(rows, []);
});

test("event rows sort newest first", () => {
  const rows = deriveAttention(
    [],
    [],
    [
      matEvent({ id: "a", filing_date: "2026-06-05", ticker: "OLD" }),
      matEvent({ id: "b", filing_date: "2026-06-09", ticker: "NEW" }),
    ],
  );
  assert.deepEqual(
    rows.map((r) => (r.kind === "event" ? r.ticker : "")),
    ["NEW", "OLD"],
  );
});
```

- [ ] **Step 2: Run to verify failure**

```bash
cd frontend && node --test lib/todayDerive.test.mts; cd ..
```

Expected: new tests FAIL (deriveAttention takes 2 args / no `event` kind).

- [ ] **Step 3: Implement in `frontend/lib/todayDerive.ts`**

Update the import:

```typescript
import type { Health, MaterialEvent, QuestionTickerRollup, StatusBoardEntry } from "./api";
```

Add the row type after `QuestionsAttentionRow`:

```typescript
export interface EventAttentionRow {
  kind: "event";
  severity: "amber";
  ticker: string;
  headline: string;
  eventType: string;
  filingDate: string;
  eventId: string;
}
```

Widen the union:

```typescript
export type AttentionRow = HealthAttentionRow | QuestionsAttentionRow | EventAttentionRow;
```

Update `deriveAttention` — new optional third param, event rows between health and questions:

```typescript
export function deriveAttention(
  entries: StatusBoardEntry[],
  rollup: QuestionTickerRollup[],
  events: MaterialEvent[] = [],
): AttentionRow[] {
```

and before the `return` statement add:

```typescript
  const eventRows = [...events]
    .sort((a, b) => b.filing_date.localeCompare(a.filing_date))
    .map(
      (ev): EventAttentionRow => ({
        kind: "event",
        severity: "amber",
        ticker: ev.ticker,
        headline: ev.headline,
        eventType: ev.event_type,
        filingDate: ev.filing_date,
        eventId: ev.id,
      }),
    );
```

then change the return to:

```typescript
  return [...healthRows, ...eventRows, ...questionRows];
```

- [ ] **Step 4: Run tests**

```bash
cd frontend && node --test lib/todayDerive.test.mts; cd ..
```

Expected: all PASS (existing tests unchanged).

- [ ] **Step 5: Render in `frontend/components/today/AttentionList.tsx`**

Add a label map at module level:

```tsx
const EVENT_TYPE_LABEL: Record<string, string> = {
  guidance: "Guidance",
  personnel: "Personnel",
  ma: "M&A",
  financing: "Financing",
  other: "8-K",
};
```

In the `rows.map(...)` ternary, add an `event` branch between the health branch and the questions branch (turn the ternary into a chain):

```tsx
            ) : row.kind === "event" ? (
              <Link
                key={`event-${row.eventId}`}
                href={`/status?expand_events=${row.ticker}`}
                className={`flex items-center gap-3 rounded-lg border border-[var(--border)] border-l-[3px] ${ROW_BORDER[row.severity]} bg-[var(--surface)] px-3 py-2 hover:bg-[var(--surface-alt)] transition-colors`}
              >
                <span className="font-mono font-bold text-sm text-[var(--text)] tracking-wide shrink-0">
                  {row.ticker}
                </span>
                <span className="text-[11px] text-[var(--text-muted)] shrink-0">
                  {EVENT_TYPE_LABEL[row.eventType] ?? "8-K"} · {row.filingDate}
                </span>
                <span className="text-xs text-[var(--text-muted)] truncate flex-1">
                  <span className="font-semibold text-[var(--text)]">8-K</span> — {row.headline}
                </span>
                <span className="text-[11px] text-[var(--primary)] shrink-0">View →</span>
              </Link>
            ) : (
```

- [ ] **Step 6: Fetch in `frontend/app/page.tsx`**

Extend the api import with `events as eventsApi, type MaterialEvent`.

Add state after the rollup state:

```tsx
  const [materialEvents, setMaterialEvents] = useState<MaterialEvent[] | null>(null);
  const [eventsError, setEventsError] = useState<string | null>(null);
```

Add `events: false` to `loadedRef.current`'s initial object.

Add a fourth promise to the `Promise.allSettled` array:

```tsx
        eventsApi.list({ since_days: 7, materiality: "high" }),
```

(destructure as `const [boardRes, calRes, qRes, evRes] = ...`), and handle it after the questions block:

```tsx
      if (evRes.status === "fulfilled") {
        loadedRef.current.events = true;
        setMaterialEvents(evRes.value.events);
        setEventsError(null);
      } else if (!loadedRef.current.events) {
        setEventsError("Could not load material events.");
      }
```

Update the derivation + error line:

```tsx
  const attentionRows = useMemo(
    () => deriveAttention(board ?? [], rollup ?? [], materialEvents ?? []),
    [board, rollup, materialEvents],
  );

  const attentionError =
    boardError ??
    (questionsError ? `${questionsError} Health rows may be incomplete.` : null) ??
    (eventsError ? `${eventsError} 8-K rows may be missing.` : null);
```

- [ ] **Step 7: Lint + tests**

```bash
cd frontend && npm run lint && node --test lib/todayDerive.test.mts; cd ..
```

Expected: clean lint; all tests PASS.

- [ ] **Step 8: Commit**

```bash
git add frontend/lib/todayDerive.ts frontend/lib/todayDerive.test.mts frontend/components/today/AttentionList.tsx frontend/app/page.tsx
git commit -m "feat(events): high-materiality 8-K rows in Today attention list"
```

---

### Task 13: Discovery card insider chip

**Files:**
- Modify: `frontend/app/theme/[id]/ThemeDetailClient.tsx`

- [ ] **Step 1: Add the chip**

In `ThemeDetailClient.tsx`, find the main badge row (around line 111-115, where `<SourceBadge badge={card.signal_source_badge} />` and `<VelocityBadge signal={card.x_signal} />` render). Add after the `card.is_surprise` badge:

```tsx
          {card.insider && card.insider.modifier !== 0 && (
            <span
              className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${
                card.insider.modifier > 0
                  ? "bg-emerald-900/40 text-emerald-300"
                  : "bg-amber-900/40 text-amber-300"
              }`}
              title={`Combined score ${card.insider.modifier > 0 ? "+" : ""}${card.insider.modifier} from 90-day insider activity (${card.insider.buy_count} buys / ${card.insider.sell_count} sells)`}
            >
              {card.insider.modifier > 0 ? "Insider buying" : "Insider selling"}
            </span>
          )}
```

(The `card.insider &&` guard keeps old cached API responses without the field from crashing.)

- [ ] **Step 2: Lint + build**

```bash
cd frontend && npm run lint && npm run build; cd ..
```

Expected: clean lint; build succeeds.

- [ ] **Step 3: Commit**

```bash
git add "frontend/app/theme/[id]/ThemeDetailClient.tsx"
git commit -m "feat(events): insider buying/selling chip on discovery cards"
```

---

### Task 14: Full verification, live smoke (GATE 2), docs

**Files:**
- Modify: `TODO.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Full backend suite**

```bash
backend/venv/bin/python -m unittest $(ls backend/tests/test_*.py | sed 's|/|.|g; s|\.py$||' | tr '\n' ' ')
```

Expected: all green (was 342 before this feature; now ~342 + ~35 new).

- [ ] **Step 2: Frontend lint + build + node tests**

```bash
cd frontend && npm run lint && npm run build && node --test lib/todayDerive.test.mts; cd ..
```

Expected: all clean.

- [ ] **Step 3: Live smoke — real scan (GATE 2 from the spec)**

Requires Postgres up and migrations applied. Run from repo root:

```bash
backend/venv/bin/python -c "
import asyncio
from backend.app.clients.edgar import EdgarClient
from backend.app.clients.fmp import FMPClient
from backend.app.services.material_events_scheduler import run_daily_material_scan

async def main():
    edgar, fmp = EdgarClient(), FMPClient()
    try:
        summary = await run_daily_material_scan(edgar=edgar, fmp=fmp)
        print('SUMMARY:', summary)
    finally:
        await edgar.close()
        await fmp.close()

asyncio.run(main())
"
```

Expected: a summary dict with `tickers_scanned` = universe size, plausible `events_created` / `transactions_added`, and an `errors` list you should actually read. Then verify rows landed:

```bash
backend/venv/bin/python -c "
import asyncio
from sqlalchemy import select, func
from backend.app.db import async_session
from backend.app.models.material_event import MaterialEvent
from backend.app.models.insider_transaction import InsiderTransaction
from backend.app.models.signal import Signal

async def main():
    async with async_session() as db:
        ev = (await db.execute(select(func.count()).select_from(MaterialEvent))).scalar()
        tx = (await db.execute(select(func.count()).select_from(InsiderTransaction))).scalar()
        sig = (await db.execute(select(func.count()).select_from(Signal).where(Signal.signal_type == 'insider'))).scalar()
        print(f'material_events={ev} insider_transactions={tx} insider_signals={sig}')
        rows = (await db.execute(select(MaterialEvent).limit(3))).scalars().all()
        for r in rows:
            print(r.ticker, r.event_type, r.materiality, '—', r.headline)

asyncio.run(main())
"
```

Expected: non-zero counts (assuming any universe ticker filed an 8-K in the last 14 days — if all zeros, spot-check one ticker's EDGAR submissions manually before concluding the scan is broken). Read 2-3 classified headlines for sanity — they should be factual one-liners with sensible materiality.

Re-run the first command once more: `events_created` must be 0 the second time (idempotency, live-confirmed).

- [ ] **Step 4: UI smoke (manual, dev servers running)**

With `uvicorn backend.app.main:app --reload` + `cd frontend && npm run dev` (`NEXT_PUBLIC_API_URL=http://127.0.0.1:8000` — Docker steals IPv6 localhost:8000 on this machine):
- `/status` — 8-K badges visible where events exist; click opens drawer; dismiss removes the row and the badge count drops on next poll.
- `/` — high-materiality events appear as amber attention rows; clicking deep-links to `/status` with the drawer open.
- `/theme/[id]` — insider chip appears on cards whose ticker has a non-zero fresh insider signal.

- [ ] **Step 5: Update `TODO.md`** — add to "Done (recent)":

```markdown
- **8-K + Form 4 monitoring (investor-portal sub-project 4)** — daily 06:30 UTC scan of the universe (seeds ∪ active theses): 8-Ks item-code-prefiltered and Haiku-classified into `material_events` (badge + drawer on `/status`, high-materiality rows on Today, `expand_events` deep link); Form 4 via FMP `insider-trading/search` into `insider_transactions` (sha256 natural-key idempotent, accession/link kept for EDGAR backfill) → 90-day aggregate → `signals` `insider` rows (history dual-write) → bounded ±5/−3 modifier on the discovery combined score + card chip. `/api/events` router (list/dismiss/scan). Spec: `docs/superpowers/specs/2026-06-10-material-events-design.md`.
```

Remove (or trim) the corresponding "SEC 8-K + Form 4 monitoring" bullet from the Backlog section — leave a note that congressional trading remains backlog.

- [ ] **Step 6: Update `CLAUDE.md`** — add a short section after "Status board, catalysts, and questions":

```markdown
### Material events + insider signal (read this before touching `backend/app/services/material_events_scheduler.py`, `event_classifier.py`, `insider_*.py`, or `api/events.py`)

Daily 06:30 UTC cron (4th job in `main.py::lifespan`) scans the universe (theme seeds ∪ active theses — same derivation as the calendar, via the status board's latest-runs SQL). 8-K side: EDGAR submissions → item-code prefilter (skip non-empty subsets of {7.01, 9.01}; 2.02 kept — guidance lives there; empty items = missing metadata → classify) → Haiku classify (`event_classifier.py`, prefill + `parse_structured_output`, enum-normalized; classification errors are NOT tombstoned so they retry next run) → `Filing` (reuses `edgar_sections_ingest._upsert_filing`) + `material_events` (unique per filing, `dismissed_at` mirrors read-throughs). Form 4 side: FMP `insider-trading/search` (`limit=100`) → `insider_transactions` upsert idempotent on a sha256 `natural_key`; `accession_number`/`sec_link` kept for future raw-EDGAR backfill — wire keys live-verified 2026-06-10. `insider_signal.py` is pure (90-day aggregate: open-market P/S only, null-price rows count but don't add value, cluster = ≥2 distinct buyers in 30d) → `signals` row `signal_type="insider"` per (ticker, theme) + `signal_history` dual-write. Discovery applies it as a bounded modifier (`apply_insider_modifier`: +5 cluster / +2 net buying / −3 pronounced selling, 48h staleness via `INSIDER_STALE_HOURS`, clamp [0,100]) — deliberately NOT a 4th weight. Status board joins a 14-day undismissed summary per ticker (one query). `/api/events`: list (filterable), `{id}/dismiss`, `scan` (202 fire-and-forget; cron is primary). Frontend: `MaterialEventsDrawer` + badge on `/status` (deep link `/status?expand_events=<ticker>`), amber attention rows on Today (high materiality, 7d), insider chip on discovery cards.
```

- [ ] **Step 7: Commit**

```bash
git add TODO.md CLAUDE.md
git commit -m "docs: material events + insider signal — TODO done-log + CLAUDE.md section"
```

- [ ] **Step 8: Finish** — use superpowers:finishing-a-development-branch (push branch, open PR against `main` with the feature summary; PR body ends with the standard generated-with footer).

---

## Self-review notes (already applied)

- **Spec coverage:** tables (T2), cron + universe + per-ticker isolation (T6/T7), prefilter + classifier (T5), FMP-primary Form 4 with EDGAR traceability (T1/T4), aggregate + signals + history (T3/T6), bounded discovery modifier (T9), board join (T8), `/api/events` (T7), badge + drawer + deep link (T11), Today rows (T12), insider chip (T13), both live-verification gates (T1, T14 step 3), out-of-scope list respected (no congressional, no snapshots, no feed page).
- **Type consistency:** `MaterialEventsSummary` fields (`count_14d`, `max_materiality`, `latest_headline`) identical across service dataclass, API model, and TS interface. `signal_value` keys match `InsiderSnapshot` reads in `_merge_results`. `classify_8k` returns `(EventClassification | None, str | None)` and the scheduler consumes exactly that.
- **Known judgment calls** (documented in code): empty `items` string → classify (missing metadata ≠ noise); classification failures not tombstoned (retry next run); 8-K/A amendments out of scope; insider signal written per (ticker, theme) like velocity.

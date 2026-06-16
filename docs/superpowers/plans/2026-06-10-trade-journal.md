# Lightweight Trade Journal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Manual entry/exit trade logging linked to `verdict_outcomes`, with a decision-vs-outcome comparison section on `/performance`.

**Architecture:** One new table (`journal_trades`) + a commit-free service + a pure comparison module; all comparison math computed at read time by joining trades to their linked verdict outcomes (no cron, no materialized state). New `/api/journal` router; frontend section on `/performance` plus "Log trade" deep-link buttons on the status board and company header.

**Tech Stack:** FastAPI + async SQLAlchemy + Alembic (backend), stdlib `unittest`, Next.js 16 App Router + React 19 + Tailwind v4 (frontend).

**Spec:** `docs/superpowers/specs/2026-06-10-trade-journal-design.md` — read it first.

**Branch:** `feat/trade-journal` off `main`.

**House rules that apply to every task:**
- Backend imports are absolute (`backend.app.*`); run everything from project root with `backend/venv` active.
- Tests: `backend/venv/bin/python -m unittest backend.tests.<module> -v` from project root.
- Service write functions are **commit-free** — API routes own the session and commit (`unit_of_work`).
- Tickers upper-cased at API entry via `normalize_ticker` (`backend/app/models/ticker.py`).
- Never instantiate `FMPClient()` in a route — use `request.app.state.fmp`.
- All return values are **fractional** (0.12 = +12%), matching `verdict_return_snapshots.ticker_return_pct` and the frontend `ReturnCell`.
- Frontend: read `frontend/AGENTS.md` warning — check `node_modules/next/dist/docs/` before assuming Next.js APIs.

---

### Task 1: `JournalTrade` ORM model + migration

**Files:**
- Create: `backend/app/models/journal_trade.py`
- Create: `backend/migrations/versions/<generated>_journal_trades.py`
- Modify: `backend/app/models/__init__.py` (register model for Alembic metadata)

- [ ] **Step 1: Write the model**

Create `backend/app/models/journal_trade.py`:

```python
"""JournalTrade — manual entry/exit trade log linked to verdict_outcomes.

One row = one entry + one exit; scaling in/out = multiple rows. A null
exit_date means the trade is open (no status column — derived).
See docs/superpowers/specs/2026-06-10-trade-journal-design.md.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import Date, ForeignKey, Index, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base, TimestampMixin
from backend.app.models.outcome import VerdictOutcome


class JournalTrade(TimestampMixin, Base):
    __tablename__ = "journal_trades"
    __table_args__ = (
        # open-trades list is the hot read path
        Index(
            "ix_journal_trades_open_ticker",
            "ticker",
            postgresql_where=text("exit_date IS NULL"),
        ),
        Index("ix_journal_trades_outcome_id", "outcome_id"),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    direction: Mapped[str] = mapped_column(
        String(8), nullable=False, server_default="long"
    )  # 'long' | 'short'

    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    entry_price: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    entry_price_source: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # 'manual' | 'fmp_eod_adjusted'

    exit_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    exit_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    exit_price_source: Mapped[str | None] = mapped_column(String(32), nullable=True)

    quantity: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)

    spy_entry_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    spy_exit_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)

    outcome_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("verdict_outcomes.id", ondelete="SET NULL"),
        nullable=True,
    )

    entry_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    exit_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    exit_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    outcome: Mapped[VerdictOutcome | None] = relationship("VerdictOutcome")
```

- [ ] **Step 2: Register the model**

In `backend/app/models/__init__.py`, add with the other imports (alphabetical-ish placement next to `kill_criterion_state`):

```python
from backend.app.models.journal_trade import JournalTrade  # noqa: F401
```

and add `"JournalTrade",` to `__all__`.

- [ ] **Step 3: Generate the migration**

```bash
cd backend && alembic revision --autogenerate -m "journal_trades"
```

Open the generated file and verify it contains ONLY the `journal_trades` table + the two indexes (autogenerate sometimes picks up drift — delete anything unrelated). Verify `down_revision` is `'b7e2c9f4a1d3'` (current head — confirm with `alembic heads` first; if a different head exists, chain off that). The upgrade body should be equivalent to:

```python
def upgrade() -> None:
    op.create_table(
        "journal_trades",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("direction", sa.String(length=8), server_default="long", nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("entry_price", sa.Numeric(20, 6), nullable=False),
        sa.Column("entry_price_source", sa.String(length=32), nullable=False),
        sa.Column("exit_date", sa.Date(), nullable=True),
        sa.Column("exit_price", sa.Numeric(20, 6), nullable=True),
        sa.Column("exit_price_source", sa.String(length=32), nullable=True),
        sa.Column("quantity", sa.Numeric(20, 6), nullable=True),
        sa.Column("spy_entry_price", sa.Numeric(20, 6), nullable=True),
        sa.Column("spy_exit_price", sa.Numeric(20, 6), nullable=True),
        sa.Column(
            "outcome_id",
            postgresql.UUID(),
            sa.ForeignKey("verdict_outcomes.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("entry_rationale", sa.Text(), nullable=True),
        sa.Column("exit_reason", sa.String(length=32), nullable=True),
        sa.Column("exit_note", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
    )
    op.create_index(
        "ix_journal_trades_open_ticker", "journal_trades", ["ticker"],
        postgresql_where=sa.text("exit_date IS NULL"),
    )
    op.create_index("ix_journal_trades_outcome_id", "journal_trades", ["outcome_id"])


def downgrade() -> None:
    op.drop_index("ix_journal_trades_outcome_id", table_name="journal_trades")
    op.drop_index("ix_journal_trades_open_ticker", table_name="journal_trades")
    op.drop_table("journal_trades")
```

- [ ] **Step 4: Apply and smoke-test**

```bash
cd backend && alembic upgrade head && cd ..
backend/venv/bin/python -c "from backend.app.models import JournalTrade; print(JournalTrade.__tablename__)"
```

Expected: `journal_trades` printed, no import errors, migration applies cleanly.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/journal_trade.py backend/app/models/__init__.py backend/migrations/versions/
git commit -m "feat(journal): JournalTrade model + journal_trades migration"
```

---

### Task 2: Pure comparison module (TDD)

**Files:**
- Create: `backend/app/services/journal_comparison.py`
- Test: `backend/tests/test_journal_comparison.py`

Pure synchronous functions over primitives — no DB, no FMP, no ORM imports (pattern: `insider_signal.py`, `model_balancing.py`).

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_journal_comparison.py`:

```python
"""Pins the pure decision-vs-outcome math: direction-aware returns,
SPY-excess None propagation, nearest-offset boundaries, snapshot
comparison, and summary rollups."""
from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal

from backend.app.services.journal_comparison import (
    ClosedTradeStat,
    decision_vs_outcome,
    nearest_offset,
    summarize,
    trade_returns,
)


def _returns(**overrides):
    kwargs = dict(
        direction="long",
        entry_date=date(2026, 1, 5),
        entry_price=Decimal("100"),
        exit_date=date(2026, 4, 6),
        exit_price=Decimal("110"),
        spy_entry_price=Decimal("500"),
        spy_exit_price=Decimal("510"),
    )
    kwargs.update(overrides)
    return trade_returns(**kwargs)


class TradeReturnsTests(unittest.TestCase):
    def test_long_return_and_spy_excess(self):
        r = _returns()
        self.assertEqual(r.return_pct, Decimal("0.1"))
        self.assertEqual(r.spy_excess_pct, Decimal("0.08"))
        self.assertEqual(r.holding_days, 91)

    def test_short_return_is_negated_but_excess_still_trade_minus_spy(self):
        r = _returns(direction="short")
        self.assertEqual(r.return_pct, Decimal("-0.1"))
        self.assertEqual(r.spy_excess_pct, Decimal("-0.12"))

    def test_open_trade_returns_all_none(self):
        r = _returns(exit_date=None, exit_price=None)
        self.assertIsNone(r.return_pct)
        self.assertIsNone(r.spy_excess_pct)
        self.assertIsNone(r.holding_days)

    def test_missing_spy_price_propagates_none_excess(self):
        r = _returns(spy_exit_price=None)
        self.assertEqual(r.return_pct, Decimal("0.1"))
        self.assertIsNone(r.spy_excess_pct)


class NearestOffsetTests(unittest.TestCase):
    def test_boundaries(self):
        cases = [(0, "1d"), (4, "1d"), (5, "1w"), (18, "1w"), (19, "1m"),
                 (60, "1m"), (61, "3m"), (136, "3m"), (137, "6m"), (200, "6m")]
        for days, expected in cases:
            with self.subTest(days=days):
                self.assertEqual(nearest_offset(days), expected)


def _snap(offset, ret, excess):
    return {
        "snapshot_offset": offset,
        "ticker_return_pct": ret,
        "spy_excess_pct": excess,
    }


class DecisionVsOutcomeTests(unittest.TestCase):
    def test_picks_nearest_offset_and_computes_delta(self):
        r = _returns()  # 91 holding days -> '3m'
        snaps = [_snap("1m", Decimal("0.05"), Decimal("0.02")),
                 _snap("3m", Decimal("0.15"), Decimal("0.11"))]
        c = decision_vs_outcome(r, snaps)
        self.assertEqual(c.offset, "3m")
        self.assertEqual(c.paper_return_pct, Decimal("0.15"))
        self.assertEqual(c.execution_delta_pct, Decimal("0.08") - Decimal("0.11"))

    def test_none_when_snapshot_missing(self):
        r = _returns()
        self.assertIsNone(decision_vs_outcome(r, [_snap("1d", Decimal("0.01"), None)]))

    def test_none_for_open_trade(self):
        r = _returns(exit_date=None, exit_price=None)
        self.assertIsNone(decision_vs_outcome(r, [_snap("3m", Decimal("0.1"), None)]))

    def test_delta_none_when_either_excess_missing(self):
        r = _returns(spy_exit_price=None)  # trade excess None
        c = decision_vs_outcome(r, [_snap("3m", Decimal("0.15"), Decimal("0.11"))])
        self.assertIsNotNone(c)
        self.assertIsNone(c.execution_delta_pct)


def _stat(ret, excess, days=30, reason="stop_loss", delta=None):
    return ClosedTradeStat(
        return_pct=Decimal(str(ret)),
        spy_excess_pct=None if excess is None else Decimal(str(excess)),
        holding_days=days,
        exit_reason=reason,
        execution_delta_pct=None if delta is None else Decimal(str(delta)),
    )


class SummarizeTests(unittest.TestCase):
    def test_empty_journal_shape(self):
        s = summarize([])
        self.assertEqual(s["closed_count"], 0)
        self.assertIsNone(s["hit_rate"])
        self.assertEqual(s["by_exit_reason"], [])
        self.assertEqual(s["execution_vs_paper"], {"n": 0, "avg_delta_pct": None})

    def test_hit_rate_uses_excess_when_available_else_raw_return(self):
        stats = [
            _stat("0.10", "0.05"),   # hit on excess
            _stat("0.10", "-0.02"),  # miss on excess despite positive return
            _stat("0.10", None),     # falls back to raw return -> hit
        ]
        s = summarize(stats)
        self.assertAlmostEqual(s["hit_rate"], 2 / 3)
        self.assertEqual(s["excess_basis_count"], 2)

    def test_median_even_count_and_exit_reason_grouping(self):
        stats = [_stat("0.10", "0.01", reason="stop_loss"),
                 _stat("0.20", "0.02", reason="thesis_played_out"),
                 _stat("-0.10", None, reason=None),
                 _stat("0.40", "0.03", reason="stop_loss", delta="0.01")]
        s = summarize(stats)
        self.assertEqual(s["median_return_pct"], Decimal("0.15"))
        reasons = {r["exit_reason"]: r for r in s["by_exit_reason"]}
        self.assertEqual(reasons["stop_loss"]["count"], 2)
        self.assertEqual(reasons["unspecified"]["count"], 1)
        self.assertEqual(s["execution_vs_paper"], {"n": 1, "avg_delta_pct": Decimal("0.01")})


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
backend/venv/bin/python -m unittest backend.tests.test_journal_comparison -v
```

Expected: `ModuleNotFoundError: No module named 'backend.app.services.journal_comparison'`

- [ ] **Step 3: Implement the module**

Create `backend/app/services/journal_comparison.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
backend/venv/bin/python -m unittest backend.tests.test_journal_comparison -v
```

Expected: all PASS. (If `test_long_return_and_spy_excess` fails on exact Decimal equality, check the math, not the test — `10/100 = Decimal("0.1")` exactly.)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/journal_comparison.py backend/tests/test_journal_comparison.py
git commit -m "feat(journal): pure decision-vs-outcome comparison module"
```

---

### Task 3: Journal service — auto-fill + commit-free persistence (TDD)

**Files:**
- Create: `backend/app/services/journal.py`
- Test: `backend/tests/test_journal_service.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_journal_service.py`. Note the env-var preamble and the mock-session helper copied from `backend/tests/test_peer_sets.py` — that's the house pattern for DB-less service tests:

```python
"""Pins journal service behavior: adjusted-close on-or-before lookup,
create/close auto-fill with best-effort SPY, reopen clearing, and the
commit-free contract."""
from __future__ import annotations

import os
import unittest
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("SEC_USER_AGENT", "test")
os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

from backend.app.services import journal


def _fmp_with_history(rows, fail=False):
    fmp = MagicMock()
    if fail:
        fmp.get_historical_price_adjusted = AsyncMock(side_effect=RuntimeError("fmp down"))
    else:
        fmp.get_historical_price_adjusted = AsyncMock(return_value=(rows, MagicMock()))
    return fmp


def _db():
    db = MagicMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.execute = AsyncMock()
    return db


class AdjustedCloseTests(unittest.IsolatedAsyncioTestCase):
    async def test_picks_newest_row_on_or_before_target(self):
        rows = [
            {"date": "2026-06-08", "adjClose": 101.5},  # Monday
            {"date": "2026-06-05", "adjClose": 100.0},  # Friday
        ]
        fmp = _fmp_with_history(rows)
        # Saturday target -> Friday close... but Monday 6/8 > 6/6, so Friday wins
        result = await journal.adjusted_close_on_or_before(fmp, "NVDA", date(2026, 6, 6))
        self.assertEqual(result, (Decimal("100.0"), date(2026, 6, 5)))

    async def test_none_on_fmp_failure(self):
        fmp = _fmp_with_history([], fail=True)
        self.assertIsNone(
            await journal.adjusted_close_on_or_before(fmp, "NVDA", date(2026, 6, 6))
        )

    async def test_none_on_empty_rows_and_skips_malformed(self):
        fmp = _fmp_with_history([{"date": "garbage", "adjClose": 1}, {"adjClose": 2}])
        self.assertIsNone(
            await journal.adjusted_close_on_or_before(fmp, "NVDA", date(2026, 6, 6))
        )


class CreateTradeTests(unittest.IsolatedAsyncioTestCase):
    async def test_autofill_entry_price_and_spy_best_effort(self):
        rows = [{"date": "2026-06-05", "adjClose": 100.0}]
        fmp = _fmp_with_history(rows)
        db = _db()
        trade = await journal.create_trade(
            db, fmp, ticker="NVDA", entry_date=date(2026, 6, 5),
            entry_price=None, quantity=None, direction="long",
            outcome_id=None, entry_rationale=None,
        )
        self.assertEqual(trade.entry_price, Decimal("100.0"))
        self.assertEqual(trade.entry_price_source, "fmp_eod_adjusted")
        self.assertEqual(trade.spy_entry_price, Decimal("100.0"))
        db.add.assert_called_once()
        db.commit.assert_not_awaited()  # commit-free contract

    async def test_manual_price_skips_ticker_lookup_but_spy_failure_is_null(self):
        fmp = _fmp_with_history([], fail=True)
        db = _db()
        trade = await journal.create_trade(
            db, fmp, ticker="NVDA", entry_date=date(2026, 6, 5),
            entry_price=Decimal("99.5"), quantity=Decimal("10"), direction="long",
            outcome_id=None, entry_rationale="dip buy",
        )
        self.assertEqual(trade.entry_price_source, "manual")
        self.assertIsNone(trade.spy_entry_price)  # degraded, not raised

    async def test_autofill_failure_without_manual_price_raises(self):
        fmp = _fmp_with_history([], fail=True)
        with self.assertRaises(journal.PriceUnavailableError):
            await journal.create_trade(
                _db(), fmp, ticker="NVDA", entry_date=date(2026, 6, 5),
                entry_price=None, quantity=None, direction="long",
                outcome_id=None, entry_rationale=None,
            )


def _open_trade(**overrides):
    from backend.app.models.journal_trade import JournalTrade

    kwargs = dict(
        ticker="NVDA", direction="long",
        entry_date=date(2026, 6, 1), entry_price=Decimal("100"),
        entry_price_source="manual", spy_entry_price=Decimal("500"),
    )
    kwargs.update(overrides)
    return JournalTrade(**kwargs)


class UpdateTradeTests(unittest.IsolatedAsyncioTestCase):
    async def test_close_autofills_exit_and_spy(self):
        rows = [{"date": "2026-06-08", "adjClose": 110.0}]
        fmp = _fmp_with_history(rows)
        trade = _open_trade()
        await journal.update_trade(_db(), fmp, trade, {"exit_date": date(2026, 6, 8),
                                                       "exit_reason": "stop_loss"})
        self.assertEqual(trade.exit_price, Decimal("110.0"))
        self.assertEqual(trade.exit_price_source, "fmp_eod_adjusted")
        self.assertEqual(trade.spy_exit_price, Decimal("110.0"))
        self.assertEqual(trade.exit_reason, "stop_loss")

    async def test_close_with_manual_price_spy_failure_degrades(self):
        fmp = _fmp_with_history([], fail=True)
        trade = _open_trade()
        await journal.update_trade(
            _db(), fmp, trade,
            {"exit_date": date(2026, 6, 8), "exit_price": Decimal("111")},
        )
        self.assertEqual(trade.exit_price, Decimal("111"))
        self.assertEqual(trade.exit_price_source, "manual")
        self.assertIsNone(trade.spy_exit_price)

    async def test_exit_before_entry_raises_value_error(self):
        trade = _open_trade()
        with self.assertRaises(ValueError):
            await journal.update_trade(
                _db(), _fmp_with_history([]), trade, {"exit_date": date(2026, 5, 1),
                                                      "exit_price": Decimal("1")},
            )

    async def test_exit_fields_without_exit_date_raise(self):
        trade = _open_trade()
        with self.assertRaises(ValueError):
            await journal.update_trade(
                _db(), _fmp_with_history([]), trade, {"exit_reason": "mistake"}
            )

    async def test_reopen_clears_all_exit_fields(self):
        trade = _open_trade(
            exit_date=date(2026, 6, 8), exit_price=Decimal("110"),
            exit_price_source="manual", exit_reason="stop_loss",
            exit_note="note", spy_exit_price=Decimal("510"),
        )
        await journal.update_trade(_db(), _fmp_with_history([]), trade, {"exit_date": None})
        for field in ("exit_date", "exit_price", "exit_price_source",
                      "exit_reason", "exit_note", "spy_exit_price"):
            self.assertIsNone(getattr(trade, field), field)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
backend/venv/bin/python -m unittest backend.tests.test_journal_service -v
```

Expected: `ModuleNotFoundError: No module named 'backend.app.services.journal'`

- [ ] **Step 3: Implement the service**

Create `backend/app/services/journal.py`:

```python
"""Trade-journal persistence + FMP price auto-fill.

Write functions are COMMIT-FREE — the caller owns the session and must
commit (same contract as peer_sets.py; API routes commit). FMP benchmark
fetches are best-effort: SPY gaps degrade to NULL columns, never raise.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.models.journal_trade import JournalTrade
from backend.app.models.outcome import VerdictOutcome

log = logging.getLogger(__name__)

PRICE_LOOKBACK_DAYS = 7  # covers weekends + holiday clusters


class PriceUnavailableError(Exception):
    """No FMP price for the requested date and no manual price supplied."""


async def adjusted_close_on_or_before(
    fmp, ticker: str, target: date
) -> tuple[Decimal, date] | None:
    """Newest dividend-adjusted close at or before `target` within the
    lookback window. None on FMP failure or no usable rows — callers fall
    back to manual entry / NULL benchmark. The returned date may be earlier
    than requested (weekend/holiday) — surface it so the user sees which
    session priced the fill."""
    from_date = (target - timedelta(days=PRICE_LOOKBACK_DAYS)).isoformat()
    try:
        rows, _ = await fmp.get_historical_price_adjusted(
            ticker, from_date, target.isoformat()
        )
    except Exception:  # noqa: BLE001 — best-effort by contract
        log.warning("adjusted-close lookup failed for %s @ %s", ticker, target)
        return None
    best: tuple[Decimal, date] | None = None
    for row in rows or []:
        raw_date, raw_px = row.get("date"), row.get("adjClose")
        if not raw_date or raw_px is None:
            continue
        try:
            d = date.fromisoformat(str(raw_date)[:10])
            px = Decimal(str(raw_px))
        except (ValueError, InvalidOperation):
            continue
        if d <= target and (best is None or d > best[1]):
            best = (px, d)
    return best


async def create_trade(
    db: AsyncSession,
    fmp,
    *,
    ticker: str,
    entry_date: date,
    entry_price: Decimal | None,
    quantity: Decimal | None,
    direction: str,
    outcome_id: str | None,
    entry_rationale: str | None,
) -> JournalTrade:
    """Add (not commit) a new open trade. Auto-fills entry price when not
    supplied; raises PriceUnavailableError when neither manual nor FMP
    price is available. SPY entry is best-effort NULL-on-failure."""
    if entry_price is not None:
        price, source = entry_price, "manual"
    else:
        found = await adjusted_close_on_or_before(fmp, ticker, entry_date)
        if found is None:
            raise PriceUnavailableError(
                f"no adjusted close for {ticker} on or before {entry_date}"
            )
        price, source = found[0], "fmp_eod_adjusted"
    spy = await adjusted_close_on_or_before(fmp, "SPY", entry_date)
    trade = JournalTrade(
        ticker=ticker,
        direction=direction,
        entry_date=entry_date,
        entry_price=price,
        entry_price_source=source,
        quantity=quantity,
        outcome_id=outcome_id,
        entry_rationale=entry_rationale,
        spy_entry_price=spy[0] if spy else None,
    )
    db.add(trade)
    return trade


_EXIT_FIELDS = ("exit_date", "exit_price", "exit_price_source",
                "exit_reason", "exit_note", "spy_exit_price")


async def update_trade(
    db: AsyncSession, fmp, trade: JournalTrade, changes: dict
) -> JournalTrade:
    """Apply a PATCH (mutates, does not commit). `changes` must come from
    model_dump(exclude_unset=True) so absent-key ≠ explicit-null.

    Closing = exit_date arrives non-null (auto-fills exit_price when not
    supplied). Reopening = explicit exit_date=None (clears every exit
    field). Raises ValueError on invariant violations (exit before entry,
    exit fields on an open trade), PriceUnavailableError when a close has
    no resolvable price."""
    if "entry_price" in changes and changes["entry_price"] is not None:
        trade.entry_price = changes["entry_price"]
        trade.entry_price_source = "manual"
    for field in ("entry_date", "quantity", "direction", "outcome_id", "entry_rationale"):
        if field in changes:
            setattr(trade, field, changes[field])

    if "exit_date" in changes and changes["exit_date"] is None:
        for field in _EXIT_FIELDS:
            setattr(trade, field, None)
        return trade

    if changes.get("exit_date") is not None:
        trade.exit_date = changes["exit_date"]

    if trade.exit_date is None:
        bad = [k for k in ("exit_price", "exit_reason", "exit_note")
               if changes.get(k) is not None]
        if bad:
            raise ValueError(f"{bad[0]} requires exit_date")
        return trade

    if trade.exit_date < trade.entry_date:
        raise ValueError("exit_date is before entry_date")

    if changes.get("exit_price") is not None:
        trade.exit_price = changes["exit_price"]
        trade.exit_price_source = "manual"
    elif trade.exit_price is None:
        found = await adjusted_close_on_or_before(fmp, trade.ticker, trade.exit_date)
        if found is None:
            raise PriceUnavailableError(
                f"no adjusted close for {trade.ticker} on or before {trade.exit_date}"
            )
        trade.exit_price, _price_date = found
        trade.exit_price_source = "fmp_eod_adjusted"

    if "exit_reason" in changes:
        trade.exit_reason = changes["exit_reason"]
    if "exit_note" in changes:
        trade.exit_note = changes["exit_note"]

    if trade.spy_exit_price is None:
        spy = await adjusted_close_on_or_before(fmp, "SPY", trade.exit_date)
        trade.spy_exit_price = spy[0] if spy else None
    return trade


async def delete_trade(db: AsyncSession, trade: JournalTrade) -> None:
    """Mark for deletion (does not commit — caller owns the session)."""
    await db.delete(trade)


def _eager_options():
    return selectinload(JournalTrade.outcome).selectinload(VerdictOutcome.snapshots)


async def get_trade(db: AsyncSession, trade_id: str) -> JournalTrade | None:
    stmt = (
        select(JournalTrade)
        .options(_eager_options())
        .where(JournalTrade.id == trade_id)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def list_trades(
    db: AsyncSession,
    *,
    status: str = "all",
    ticker: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[JournalTrade]:
    stmt = (
        select(JournalTrade)
        .options(_eager_options())
        .order_by(JournalTrade.entry_date.desc(), JournalTrade.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if status == "open":
        stmt = stmt.where(JournalTrade.exit_date.is_(None))
    elif status == "closed":
        stmt = stmt.where(JournalTrade.exit_date.is_not(None))
    if ticker:
        stmt = stmt.where(JournalTrade.ticker == ticker.upper())
    return list((await db.execute(stmt)).scalars().all())


async def trade_counts(db: AsyncSession) -> tuple[int, int]:
    """(open_count, closed_count)."""
    open_count = (
        await db.execute(
            select(func.count()).select_from(JournalTrade)
            .where(JournalTrade.exit_date.is_(None))
        )
    ).scalar_one()
    closed_count = (
        await db.execute(
            select(func.count()).select_from(JournalTrade)
            .where(JournalTrade.exit_date.is_not(None))
        )
    ).scalar_one()
    return open_count, closed_count


async def link_candidates(
    db: AsyncSession, ticker: str, limit: int = 10
) -> list[VerdictOutcome]:
    """Recent non-superseded outcomes for the ticker — the form's picker.
    Lives here because GET /api/outcomes has no ticker filter."""
    stmt = (
        select(VerdictOutcome)
        .where(
            VerdictOutcome.ticker == ticker.upper(),
            VerdictOutcome.superseded_at.is_(None),
        )
        .order_by(VerdictOutcome.verdict_emitted_at.desc())
        .limit(limit)
    )
    return list((await db.execute(stmt)).scalars().all())


async def coverage_counts(db: AsyncSession) -> tuple[int, int]:
    """(outcomes_traded, outcomes_total) over non-superseded outcomes."""
    total = (
        await db.execute(
            select(func.count()).select_from(VerdictOutcome)
            .where(VerdictOutcome.superseded_at.is_(None))
        )
    ).scalar_one()
    traded = (
        await db.execute(
            select(func.count(func.distinct(JournalTrade.outcome_id)))
            .select_from(JournalTrade)
            .join(VerdictOutcome, VerdictOutcome.id == JournalTrade.outcome_id)
            .where(VerdictOutcome.superseded_at.is_(None))
        )
    ).scalar_one()
    return traded, total
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
backend/venv/bin/python -m unittest backend.tests.test_journal_service backend.tests.test_journal_comparison -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/journal.py backend/tests/test_journal_service.py
git commit -m "feat(journal): commit-free journal service with FMP auto-fill"
```

---

### Task 4: Pydantic schemas + `/api/journal` router (TDD)

**Files:**
- Create: `backend/app/models/journal_schemas.py`
- Create: `backend/app/api/journal.py`
- Modify: `backend/app/main.py` (router registration)
- Test: `backend/tests/test_journal_api.py`

- [ ] **Step 1: Write the schemas**

Create `backend/app/models/journal_schemas.py`:

```python
"""Pydantic schemas for the trade-journal public API."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from backend.app.models.outcome_schemas import SnapshotOffset, SourceType

Direction = Literal["long", "short"]
ExitReason = Literal[
    "thesis_played_out", "kill_criterion", "stop_loss",
    "better_opportunity", "rebalance", "mistake", "other",
]
TradeStatusFilter = Literal["open", "closed", "all"]


class TradeCreate(BaseModel):
    ticker: str
    entry_date: date
    entry_price: Decimal | None = Field(default=None, gt=0)  # None -> auto-fill
    quantity: Decimal | None = Field(default=None, gt=0)
    direction: Direction = "long"
    outcome_id: str | None = None
    entry_rationale: str | None = None


class TradeUpdate(BaseModel):
    """All fields optional; absent-vs-null distinguished via
    model_dump(exclude_unset=True). Explicit exit_date=None reopens."""
    entry_date: date | None = None
    entry_price: Decimal | None = Field(default=None, gt=0)
    quantity: Decimal | None = Field(default=None, gt=0)
    direction: Direction | None = None
    outcome_id: str | None = None
    entry_rationale: str | None = None
    exit_date: date | None = None
    exit_price: Decimal | None = Field(default=None, gt=0)
    exit_reason: ExitReason | None = None
    exit_note: str | None = None


class TradeReturnsRead(BaseModel):
    return_pct: Decimal | None
    spy_excess_pct: Decimal | None
    holding_days: int | None
    unrealized: bool


class DecisionComparisonRead(BaseModel):
    offset: SnapshotOffset
    trade_return_pct: Decimal
    trade_spy_excess_pct: Decimal | None
    paper_return_pct: Decimal
    paper_spy_excess_pct: Decimal | None
    execution_delta_pct: Decimal | None


class LinkedOutcomeSummary(BaseModel):
    id: str
    verdict: str
    source_type: SourceType
    source_id: str
    theme_id: str | None
    verdict_emitted_at: datetime
    entry_price_at: date
    realized_spy_excess_pct: Decimal | None


class TradeDetail(BaseModel):
    id: str
    ticker: str
    direction: Direction
    status: Literal["open", "closed"]
    entry_date: date
    entry_price: Decimal
    entry_price_source: str
    exit_date: date | None
    exit_price: Decimal | None
    exit_price_source: str | None
    quantity: Decimal | None
    spy_entry_price: Decimal | None
    spy_exit_price: Decimal | None
    outcome_id: str | None
    entry_rationale: str | None
    exit_reason: ExitReason | None
    exit_note: str | None
    returns: TradeReturnsRead | None
    linked_outcome: LinkedOutcomeSummary | None
    comparison: DecisionComparisonRead | None
    created_at: datetime


class ExitReasonStat(BaseModel):
    exit_reason: str
    count: int
    avg_return_pct: Decimal | None
    avg_spy_excess_pct: Decimal | None


class ExecutionVsPaper(BaseModel):
    n: int
    avg_delta_pct: Decimal | None


class CoverageStat(BaseModel):
    outcomes_traded: int
    outcomes_total: int


class JournalSummary(BaseModel):
    trade_count: int
    open_count: int
    closed_count: int
    hit_rate: float | None
    excess_basis_count: int
    avg_return_pct: Decimal | None
    median_return_pct: Decimal | None
    avg_spy_excess_pct: Decimal | None
    avg_holding_days: float | None
    execution_vs_paper: ExecutionVsPaper
    by_exit_reason: list[ExitReasonStat]
    coverage: CoverageStat


class PricePreview(BaseModel):
    price: Decimal
    price_date: date  # may be earlier than requested (weekend/holiday)
    source: str


class LinkCandidate(BaseModel):
    id: str
    verdict: str
    source_type: SourceType
    theme_id: str | None
    verdict_emitted_at: datetime
    entry_price_at: date
```

- [ ] **Step 2: Write the failing API tests**

Create `backend/tests/test_journal_api.py`. Pattern: `TestClient` + patch the service-module functions the routes call (same as `test_outcomes_api.py` — patched helpers mean the session never executes SQL, so no DB is needed):

```python
"""Tests for backend.app.api.journal — CRUD, validation, summary shape."""
from __future__ import annotations

import os
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("SEC_USER_AGENT", "test")
os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

from fastapi.testclient import TestClient

from backend.app.models.journal_trade import JournalTrade
from backend.app.models.outcome import VerdictOutcome, VerdictReturnSnapshot
from backend.app.services.journal import PriceUnavailableError


def _client():
    from backend.app.main import app

    app.state.fmp = MagicMock()
    return TestClient(app)


def _trade(**overrides):
    kwargs = dict(
        id=str(uuid4()),
        ticker="NVDA",
        direction="long",
        entry_date=date(2026, 6, 1),
        entry_price=Decimal("100"),
        entry_price_source="manual",
        spy_entry_price=Decimal("500"),
        outcome_id=None,
        quantity=None,
        entry_rationale=None,
        exit_date=None,
        exit_price=None,
        exit_price_source=None,
        exit_reason=None,
        exit_note=None,
        spy_exit_price=None,
    )
    kwargs.update(overrides)
    t = JournalTrade(**kwargs)
    t.created_at = datetime(2026, 6, 1, tzinfo=timezone.utc)
    return t


def _closed_trade(**overrides):
    base = dict(
        exit_date=date(2026, 6, 8),
        exit_price=Decimal("110"),
        exit_price_source="manual",
        spy_exit_price=Decimal("510"),
        exit_reason="stop_loss",
    )
    base.update(overrides)
    return _trade(**base)


def _outcome_with_snapshot():
    o = VerdictOutcome(
        id=str(uuid4()),
        source_type="research_run",
        source_id=str(uuid4()),
        ticker="NVDA",
        theme_id=None,
        verdict="completed",
        verdict_emitted_at=datetime(2026, 5, 30, tzinfo=timezone.utc),
        entry_price_at=date(2026, 6, 1),
        entry_price=Decimal("100"),
        realized_spy_excess_pct=None,
    )
    o.snapshots = [
        VerdictReturnSnapshot(
            id=str(uuid4()),
            outcome_id=o.id,
            snapshot_offset="1w",
            snapshot_date=date(2026, 6, 8),
            ticker_price=Decimal("108"),
            ticker_return_pct=Decimal("0.08"),
            spy_excess_pct=Decimal("0.05"),
        )
    ]
    return o


class CreateTradeTests(unittest.TestCase):
    def test_create_201(self):
        trade = _trade()
        with patch("backend.app.api.journal.journal.create_trade",
                   new=AsyncMock(return_value=trade)), \
             patch("backend.app.api.journal.journal.get_trade",
                   new=AsyncMock(return_value=trade)):
            r = _client().post("/api/journal/trades", json={
                "ticker": "nvda", "entry_date": "2026-06-01",
                "entry_price": "100",
            })
        self.assertEqual(r.status_code, 201)
        body = r.json()
        self.assertEqual(body["ticker"], "NVDA")
        self.assertEqual(body["status"], "open")
        self.assertIsNone(body["comparison"])

    def test_create_422_when_autofill_unavailable(self):
        with patch("backend.app.api.journal.journal.create_trade",
                   new=AsyncMock(side_effect=PriceUnavailableError("no price"))):
            r = _client().post("/api/journal/trades", json={
                "ticker": "NVDA", "entry_date": "2026-06-01",
            })
        self.assertEqual(r.status_code, 422)

    def test_create_400_on_garbage_ticker(self):
        r = _client().post("/api/journal/trades", json={
            "ticker": "not a ticker!!", "entry_date": "2026-06-01",
            "entry_price": "1",
        })
        self.assertEqual(r.status_code, 400)


class PatchTradeTests(unittest.TestCase):
    def test_patch_close_returns_closed_status(self):
        closed = _closed_trade()
        with patch("backend.app.api.journal.journal.get_trade",
                   new=AsyncMock(return_value=closed)), \
             patch("backend.app.api.journal.journal.update_trade",
                   new=AsyncMock(return_value=closed)):
            r = _client().patch(f"/api/journal/trades/{closed.id}", json={
                "exit_date": "2026-06-08", "exit_reason": "stop_loss",
            })
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "closed")
        # realized: (110-100)/100 = 0.1; spy (510-500)/500 = 0.02 -> excess 0.08
        self.assertAlmostEqual(float(body["returns"]["return_pct"]), 0.1)
        self.assertAlmostEqual(float(body["returns"]["spy_excess_pct"]), 0.08)
        self.assertFalse(body["returns"]["unrealized"])

    def test_patch_404_unknown_trade(self):
        with patch("backend.app.api.journal.journal.get_trade",
                   new=AsyncMock(return_value=None)):
            r = _client().patch(f"/api/journal/trades/{uuid4()}", json={})
        self.assertEqual(r.status_code, 404)

    def test_patch_422_on_invariant_violation(self):
        trade = _trade()
        with patch("backend.app.api.journal.journal.get_trade",
                   new=AsyncMock(return_value=trade)), \
             patch("backend.app.api.journal.journal.update_trade",
                   new=AsyncMock(side_effect=ValueError("exit_date is before entry_date"))):
            r = _client().patch(f"/api/journal/trades/{trade.id}", json={
                "exit_date": "2020-01-01",
            })
        self.assertEqual(r.status_code, 422)


class ListTradesTests(unittest.TestCase):
    def test_list_embeds_linked_outcome_and_comparison(self):
        outcome = _outcome_with_snapshot()
        closed = _closed_trade(outcome_id=outcome.id)
        closed.outcome = outcome
        with patch("backend.app.api.journal.journal.list_trades",
                   new=AsyncMock(return_value=[closed])):
            r = _client().get("/api/journal/trades?status=closed")
        self.assertEqual(r.status_code, 200)
        row = r.json()[0]
        self.assertEqual(row["linked_outcome"]["verdict"], "completed")
        # 7 holding days -> '1w' snapshot; delta = 0.08 - 0.05
        self.assertEqual(row["comparison"]["offset"], "1w")
        self.assertAlmostEqual(float(row["comparison"]["execution_delta_pct"]), 0.03)

    def test_list_open_trade_unrealized_quote_failure_degrades(self):
        trade = _trade()
        trade.outcome = None
        with patch("backend.app.api.journal.journal.list_trades",
                   new=AsyncMock(return_value=[trade])):
            client = _client()
            client.app.state.fmp.get_quote = AsyncMock(side_effect=RuntimeError("down"))
            r = client.get("/api/journal/trades")
        self.assertEqual(r.status_code, 200)
        row = r.json()[0]
        self.assertEqual(row["status"], "open")
        self.assertTrue(row["returns"]["unrealized"])
        self.assertIsNone(row["returns"]["return_pct"])


class DeleteTradeTests(unittest.TestCase):
    def test_delete_204(self):
        trade = _trade()
        with patch("backend.app.api.journal.journal.get_trade",
                   new=AsyncMock(return_value=trade)), \
             patch("backend.app.api.journal.journal.delete_trade",
                   new=AsyncMock(return_value=None)):
            r = _client().delete(f"/api/journal/trades/{trade.id}")
        self.assertEqual(r.status_code, 204)

    def test_delete_404(self):
        with patch("backend.app.api.journal.journal.get_trade",
                   new=AsyncMock(return_value=None)):
            r = _client().delete(f"/api/journal/trades/{uuid4()}")
        self.assertEqual(r.status_code, 404)


class SummaryTests(unittest.TestCase):
    def test_summary_shape(self):
        outcome = _outcome_with_snapshot()
        closed = _closed_trade(outcome_id=outcome.id)
        closed.outcome = outcome
        with patch("backend.app.api.journal.journal.list_trades",
                   new=AsyncMock(return_value=[closed])), \
             patch("backend.app.api.journal.journal.trade_counts",
                   new=AsyncMock(return_value=(2, 1))), \
             patch("backend.app.api.journal.journal.coverage_counts",
                   new=AsyncMock(return_value=(1, 4))):
            r = _client().get("/api/journal/summary")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["trade_count"], 3)
        self.assertEqual(body["open_count"], 2)
        self.assertEqual(body["closed_count"], 1)
        self.assertEqual(body["coverage"], {"outcomes_traded": 1, "outcomes_total": 4})
        self.assertEqual(body["execution_vs_paper"]["n"], 1)
        self.assertEqual(body["hit_rate"], 1.0)


class PricePreviewTests(unittest.TestCase):
    def test_preview_200(self):
        with patch("backend.app.api.journal.journal.adjusted_close_on_or_before",
                   new=AsyncMock(return_value=(Decimal("101.5"), date(2026, 6, 5)))):
            r = _client().get("/api/journal/price-preview?ticker=nvda&date=2026-06-06")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["price_date"], "2026-06-05")
        self.assertEqual(body["source"], "fmp_eod_adjusted")

    def test_preview_404_when_unavailable(self):
        with patch("backend.app.api.journal.journal.adjusted_close_on_or_before",
                   new=AsyncMock(return_value=None)):
            r = _client().get("/api/journal/price-preview?ticker=NVDA&date=2026-06-06")
        self.assertEqual(r.status_code, 404)


class LinkCandidatesTests(unittest.TestCase):
    def test_candidates_serialized(self):
        outcome = _outcome_with_snapshot()
        with patch("backend.app.api.journal.journal.link_candidates",
                   new=AsyncMock(return_value=[outcome])):
            r = _client().get("/api/journal/link-candidates?ticker=NVDA")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()[0]["verdict"], "completed")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
backend/venv/bin/python -m unittest backend.tests.test_journal_api -v
```

Expected: every test errors with `ModuleNotFoundError: No module named 'backend.app.api.journal'` (the `patch("backend.app.api.journal...")` targets can't resolve until the router module exists).

- [ ] **Step 4: Implement the router**

Create `backend/app/api/journal.py`:

```python
"""Trade-journal CRUD + decision-vs-outcome summary.

Routes own sessions (unit_of_work for writes) and commit; the journal
service is commit-free. FMP failures degrade per the spec's error-handling
section — no 500s from benchmark gaps.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import select

from backend.app.db import async_session, unit_of_work
from backend.app.models.journal_schemas import (
    JournalSummary,
    LinkCandidate,
    PricePreview,
    TradeCreate,
    TradeDetail,
    TradeStatusFilter,
    TradeUpdate,
)
from backend.app.models.journal_trade import JournalTrade
from backend.app.models.outcome import VerdictOutcome
from backend.app.models.ticker import normalize_ticker
from backend.app.services import journal, journal_comparison as comparison

router = APIRouter(prefix="/api/journal", tags=["journal"])


# ── Serialization helpers ─────────────────────────────────────────────────────

def _snap_dicts(outcome: VerdictOutcome) -> list[dict]:
    return [
        {
            "snapshot_offset": s.snapshot_offset,
            "ticker_return_pct": s.ticker_return_pct,
            "spy_excess_pct": s.spy_excess_pct,
        }
        for s in (outcome.snapshots or [])
    ]


def _realized(trade: JournalTrade) -> comparison.TradeReturns:
    return comparison.trade_returns(
        direction=trade.direction,
        entry_date=trade.entry_date,
        entry_price=trade.entry_price,
        exit_date=trade.exit_date,
        exit_price=trade.exit_price,
        spy_entry_price=trade.spy_entry_price,
        spy_exit_price=trade.spy_exit_price,
    )


def _serialize(
    trade: JournalTrade,
    outcome: VerdictOutcome | None,
    unrealized: comparison.TradeReturns | None = None,
) -> dict:
    """Build the TradeDetail payload. `outcome` is passed explicitly — never
    touch trade.outcome here unless the caller eager-loaded it (lazy loads
    explode in async context)."""
    closed = trade.exit_date is not None
    returns = None
    comp = None
    if closed:
        r = _realized(trade)
        returns = {
            "return_pct": r.return_pct,
            "spy_excess_pct": r.spy_excess_pct,
            "holding_days": r.holding_days,
            "unrealized": False,
        }
        if outcome is not None:
            c = comparison.decision_vs_outcome(r, _snap_dicts(outcome))
            if c is not None:
                comp = {
                    "offset": c.offset,
                    "trade_return_pct": c.trade_return_pct,
                    "trade_spy_excess_pct": c.trade_spy_excess_pct,
                    "paper_return_pct": c.paper_return_pct,
                    "paper_spy_excess_pct": c.paper_spy_excess_pct,
                    "execution_delta_pct": c.execution_delta_pct,
                }
    elif unrealized is not None:
        returns = {
            "return_pct": unrealized.return_pct,
            "spy_excess_pct": unrealized.spy_excess_pct,
            "holding_days": unrealized.holding_days,
            "unrealized": True,
        }

    linked = None
    if outcome is not None:
        linked = {
            "id": outcome.id,
            "verdict": outcome.verdict,
            "source_type": outcome.source_type,
            "source_id": outcome.source_id,
            "theme_id": outcome.theme_id,
            "verdict_emitted_at": outcome.verdict_emitted_at,
            "entry_price_at": outcome.entry_price_at,
            "realized_spy_excess_pct": outcome.realized_spy_excess_pct,
        }

    return {
        "id": trade.id,
        "ticker": trade.ticker,
        "direction": trade.direction,
        "status": "closed" if closed else "open",
        "entry_date": trade.entry_date,
        "entry_price": trade.entry_price,
        "entry_price_source": trade.entry_price_source,
        "exit_date": trade.exit_date,
        "exit_price": trade.exit_price,
        "exit_price_source": trade.exit_price_source,
        "quantity": trade.quantity,
        "spy_entry_price": trade.spy_entry_price,
        "spy_exit_price": trade.spy_exit_price,
        "outcome_id": trade.outcome_id,
        "entry_rationale": trade.entry_rationale,
        "exit_reason": trade.exit_reason,
        "exit_note": trade.exit_note,
        "returns": returns,
        "linked_outcome": linked,
        "comparison": comp,
        "created_at": trade.created_at,
    }


async def _unrealized(fmp, trade: JournalTrade) -> comparison.TradeReturns:
    """Open-trade mark from a live quote — best-effort. NOTE: the quote is
    unadjusted while entry may be adjClose; accepted approximation for open
    trades (spec: error handling)."""
    price = None
    try:
        q, _ = await fmp.get_quote(trade.ticker)
        if isinstance(q, dict) and q.get("price") is not None:
            price = Decimal(str(q["price"]))
    except Exception:  # noqa: BLE001 — degrade to no-mark
        price = None
    if price is None:
        return comparison.TradeReturns(
            None, None, (date.today() - trade.entry_date).days
        )
    return comparison.trade_returns(
        direction=trade.direction,
        entry_date=trade.entry_date,
        entry_price=trade.entry_price,
        exit_date=date.today(),
        exit_price=price,
        spy_entry_price=None,
        spy_exit_price=None,
    )


def _normalized_or_400(raw: str) -> str:
    try:
        return normalize_ticker(raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ── Static routes (declared before /trades/{trade_id} by convention) ─────────

@router.get("/summary", response_model=JournalSummary)
async def get_summary() -> JournalSummary:
    async with async_session() as db:
        closed = await journal.list_trades(db, status="closed", limit=5000)
        open_count, closed_count = await journal.trade_counts(db)
        traded, total = await journal.coverage_counts(db)

    stats: list[comparison.ClosedTradeStat] = []
    for t in closed:
        r = _realized(t)
        if r.return_pct is None or r.holding_days is None:
            continue
        delta = None
        if t.outcome is not None:
            c = comparison.decision_vs_outcome(r, _snap_dicts(t.outcome))
            if c is not None:
                delta = c.execution_delta_pct
        stats.append(
            comparison.ClosedTradeStat(
                return_pct=r.return_pct,
                spy_excess_pct=r.spy_excess_pct,
                holding_days=r.holding_days,
                exit_reason=t.exit_reason,
                execution_delta_pct=delta,
            )
        )
    rollup = comparison.summarize(stats)
    return JournalSummary(
        trade_count=open_count + closed_count,
        open_count=open_count,
        coverage={"outcomes_traded": traded, "outcomes_total": total},
        **{**rollup, "closed_count": closed_count},
    )


@router.get("/price-preview", response_model=PricePreview)
async def price_preview(
    request: Request,
    ticker: str,
    on: date = Query(alias="date"),
) -> PricePreview:
    fmp = request.app.state.fmp
    found = await journal.adjusted_close_on_or_before(
        fmp, _normalized_or_400(ticker), on
    )
    if found is None:
        raise HTTPException(status_code=404, detail="no price available for that date")
    price, price_date = found
    return PricePreview(price=price, price_date=price_date, source="fmp_eod_adjusted")


@router.get("/link-candidates", response_model=list[LinkCandidate])
async def get_link_candidates(ticker: str) -> list[LinkCandidate]:
    focus = _normalized_or_400(ticker)
    async with async_session() as db:
        rows = await journal.link_candidates(db, focus)
    return [
        LinkCandidate(
            id=o.id,
            verdict=o.verdict,
            source_type=o.source_type,
            theme_id=o.theme_id,
            verdict_emitted_at=o.verdict_emitted_at,
            entry_price_at=o.entry_price_at,
        )
        for o in rows
    ]


# ── Trade CRUD ────────────────────────────────────────────────────────────────

@router.post("/trades", status_code=201, response_model=TradeDetail)
async def create_trade(body: TradeCreate, request: Request) -> TradeDetail:
    fmp = request.app.state.fmp
    focus = _normalized_or_400(body.ticker)
    async with unit_of_work() as db:
        if body.outcome_id is not None:
            exists = (
                await db.execute(
                    select(VerdictOutcome.id).where(VerdictOutcome.id == body.outcome_id)
                )
            ).scalar_one_or_none()
            if exists is None:
                raise HTTPException(status_code=404, detail="outcome not found")
        try:
            trade = await journal.create_trade(
                db,
                fmp,
                ticker=focus,
                entry_date=body.entry_date,
                entry_price=body.entry_price,
                quantity=body.quantity,
                direction=body.direction,
                outcome_id=body.outcome_id,
                entry_rationale=body.entry_rationale,
            )
        except journal.PriceUnavailableError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        await db.commit()
        full = await journal.get_trade(db, trade.id)
    return _serialize(full or trade, (full or trade).outcome if full else None)


@router.patch("/trades/{trade_id}", response_model=TradeDetail)
async def patch_trade(trade_id: str, body: TradeUpdate, request: Request) -> TradeDetail:
    fmp = request.app.state.fmp
    changes = body.model_dump(exclude_unset=True)
    async with unit_of_work() as db:
        trade = await journal.get_trade(db, trade_id)
        if trade is None:
            raise HTTPException(status_code=404, detail="trade not found")
        if changes.get("outcome_id") is not None:
            exists = (
                await db.execute(
                    select(VerdictOutcome.id).where(
                        VerdictOutcome.id == changes["outcome_id"]
                    )
                )
            ).scalar_one_or_none()
            if exists is None:
                raise HTTPException(status_code=404, detail="outcome not found")
        try:
            trade = await journal.update_trade(db, fmp, trade, changes)
        except journal.PriceUnavailableError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        await db.commit()
        full = await journal.get_trade(db, trade.id)
    final = full or trade
    return _serialize(final, final.outcome if full else None)


@router.delete("/trades/{trade_id}", status_code=204)
async def delete_trade(trade_id: str) -> None:
    async with unit_of_work() as db:
        trade = await journal.get_trade(db, trade_id)
        if trade is None:
            raise HTTPException(status_code=404, detail="trade not found")
        await journal.delete_trade(db, trade)


@router.get("/trades", response_model=list[TradeDetail])
async def list_trades(
    request: Request,
    status: TradeStatusFilter = "all",
    ticker: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[TradeDetail]:
    fmp = request.app.state.fmp
    limit = max(1, min(limit, 500))
    focus = _normalized_or_400(ticker) if ticker else None
    async with async_session() as db:
        trades = await journal.list_trades(
            db, status=status, ticker=focus, limit=limit, offset=offset
        )
    out = []
    for t in trades:
        unrealized = None
        if t.exit_date is None:
            unrealized = await _unrealized(fmp, t)
        out.append(_serialize(t, t.outcome, unrealized=unrealized))
    return out
```

**Watch out:** in `get_summary`, `rollup` already contains `closed_count` from `summarize()` — but that counts only trades with computable returns. The DB `closed_count` is authoritative; the `{**rollup, "closed_count": closed_count}` merge deliberately overwrites it. Keep that order.

**Watch out:** `GET /trades` is declared after `/summary`, `/price-preview`, `/link-candidates` (route-ordering convention). `/trades` (collection) and `/trades/{trade_id}` don't collide.

- [ ] **Step 5: Register the router**

In `backend/app/main.py`: add the import next to the other api imports:

```python
from backend.app.api import journal as journal_api
```

and after `app.include_router(peers_api.router)` (line ~208):

```python
app.include_router(journal_api.router)
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
backend/venv/bin/python -m unittest backend.tests.test_journal_api -v
```

Expected: all PASS. If `test_list_embeds_linked_outcome_and_comparison` fails with a lazy-load/greenlet error, you touched `trade.outcome` on a non-eager-loaded instance — check `_serialize` call sites.

- [ ] **Step 7: Run the full backend suite (regression gate)**

```bash
backend/venv/bin/python -m unittest $(ls backend/tests/test_*.py | sed 's|/|.|g; s|\.py$||' | tr '\n' ' ')
```

Expected: all green (suite was 323+ tests before this feature).

- [ ] **Step 8: Commit**

```bash
git add backend/app/models/journal_schemas.py backend/app/api/journal.py backend/app/main.py backend/tests/test_journal_api.py
git commit -m "feat(journal): /api/journal router — CRUD, summary, price-preview, link-candidates"
```

---

### Task 5: Frontend API client (`journalApi`)

**Files:**
- Modify: `frontend/lib/api.ts` (append after the `outcomesApi` block, ~line 1957)

- [ ] **Step 1: Add types + client**

Insert after the `outcomesApi` const (before the `// ── Transcript delta` divider). `SnapshotOffset` and `SourceType` already exist in this file — do not redeclare:

```ts
// ── Trade journal ───────────────────────────────────────────────────────────

export type TradeDirection = "long" | "short";
export type ExitReason =
  | "thesis_played_out"
  | "kill_criterion"
  | "stop_loss"
  | "better_opportunity"
  | "rebalance"
  | "mistake"
  | "other";

export interface TradeReturnsRead {
  return_pct: string | null;
  spy_excess_pct: string | null;
  holding_days: number | null;
  unrealized: boolean;
}

export interface DecisionComparisonRead {
  offset: SnapshotOffset;
  trade_return_pct: string;
  trade_spy_excess_pct: string | null;
  paper_return_pct: string;
  paper_spy_excess_pct: string | null;
  execution_delta_pct: string | null;
}

export interface LinkedOutcomeSummary {
  id: string;
  verdict: string;
  source_type: SourceType;
  source_id: string;
  theme_id: string | null;
  verdict_emitted_at: string;
  entry_price_at: string;
  realized_spy_excess_pct: string | null;
}

export interface TradeDetail {
  id: string;
  ticker: string;
  direction: TradeDirection;
  status: "open" | "closed";
  entry_date: string;
  entry_price: string;
  entry_price_source: string;
  exit_date: string | null;
  exit_price: string | null;
  exit_price_source: string | null;
  quantity: string | null;
  spy_entry_price: string | null;
  spy_exit_price: string | null;
  outcome_id: string | null;
  entry_rationale: string | null;
  exit_reason: ExitReason | null;
  exit_note: string | null;
  returns: TradeReturnsRead | null;
  linked_outcome: LinkedOutcomeSummary | null;
  comparison: DecisionComparisonRead | null;
  created_at: string;
}

export interface TradeCreateBody {
  ticker: string;
  entry_date: string;
  entry_price?: string;
  quantity?: string;
  direction?: TradeDirection;
  outcome_id?: string;
  entry_rationale?: string;
}

export interface TradeUpdateBody {
  entry_date?: string;
  entry_price?: string;
  quantity?: string;
  direction?: TradeDirection;
  outcome_id?: string;
  entry_rationale?: string;
  exit_date?: string | null;
  exit_price?: string;
  exit_reason?: ExitReason;
  exit_note?: string;
}

export interface ExitReasonStat {
  exit_reason: string;
  count: number;
  avg_return_pct: string | null;
  avg_spy_excess_pct: string | null;
}

export interface JournalSummary {
  trade_count: number;
  open_count: number;
  closed_count: number;
  hit_rate: number | null;
  excess_basis_count: number;
  avg_return_pct: string | null;
  median_return_pct: string | null;
  avg_spy_excess_pct: string | null;
  avg_holding_days: number | null;
  execution_vs_paper: { n: number; avg_delta_pct: string | null };
  by_exit_reason: ExitReasonStat[];
  coverage: { outcomes_traded: number; outcomes_total: number };
}

export interface PricePreview {
  price: string;
  price_date: string;
  source: string;
}

export interface LinkCandidate {
  id: string;
  verdict: string;
  source_type: SourceType;
  theme_id: string | null;
  verdict_emitted_at: string;
  entry_price_at: string;
}

export const journalApi = {
  async list(q: { status?: "open" | "closed" | "all"; ticker?: string } = {}): Promise<TradeDetail[]> {
    const params = new URLSearchParams();
    if (q.status) params.set("status", q.status);
    if (q.ticker) params.set("ticker", q.ticker);
    return apiFetch(`/api/journal/trades?${params.toString()}`);
  },

  async create(body: TradeCreateBody): Promise<TradeDetail> {
    return apiFetch(`/api/journal/trades`, {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  async update(id: string, body: TradeUpdateBody): Promise<TradeDetail> {
    return apiFetch(`/api/journal/trades/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    });
  },

  async remove(id: string): Promise<void> {
    return apiFetch(`/api/journal/trades/${id}`, { method: "DELETE" });
  },

  async getSummary(): Promise<JournalSummary> {
    return apiFetch(`/api/journal/summary`);
  },

  async pricePreview(ticker: string, date: string): Promise<PricePreview> {
    return apiFetch(`/api/journal/price-preview?ticker=${encodeURIComponent(ticker)}&date=${date}`);
  },

  async linkCandidates(ticker: string): Promise<LinkCandidate[]> {
    return apiFetch(`/api/journal/link-candidates?ticker=${encodeURIComponent(ticker)}`);
  },
};
```

- [ ] **Step 2: Verify it compiles**

```bash
cd frontend && npm run build
```

Expected: build succeeds (the new exports are unused so far — that's fine, lint allows unused exports).

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "feat(journal): journalApi client + types in lib/api.ts"
```

---

### Task 6: Journal UI on `/performance`

**Files:**
- Create: `frontend/components/journal/TradeJournalSection.tsx`
- Create: `frontend/components/journal/TradeForm.tsx`
- Create: `frontend/components/journal/TradeList.tsx`
- Create: `frontend/components/journal/DecisionVsOutcomePanel.tsx`
- Create: `frontend/components/journal/ExitReasonTable.tsx`
- Modify: `frontend/app/performance/page.tsx` (add section below `OutcomeList`)

House style: CSS-var tokens (`var(--bg)`, `var(--surface-alt)`, `var(--border)`, `var(--text)`, `var(--text-muted)`), `ReturnCell` for sign-colored fractional returns, `data-print-hide="true"` on interactive chrome.

- [ ] **Step 1: `TradeJournalSection.tsx` (orchestrator + deep link)**

```tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import { journalApi } from "@/lib/api";
import type { JournalSummary, TradeDetail } from "@/lib/api";
import { TradeForm } from "./TradeForm";
import { TradeList } from "./TradeList";
import { DecisionVsOutcomePanel } from "./DecisionVsOutcomePanel";
import { ExitReasonTable } from "./ExitReasonTable";

export type FormState =
  | { mode: "create"; ticker?: string }
  | { mode: "edit"; trade: TradeDetail }
  | { mode: "close"; trade: TradeDetail };

export function TradeJournalSection() {
  const [trades, setTrades] = useState<TradeDetail[]>([]);
  const [summary, setSummary] = useState<JournalSummary | null>(null);
  const [form, setForm] = useState<FormState | null>(null);

  const refresh = useCallback(() => {
    journalApi.list().then(setTrades).catch(() => setTrades([]));
    journalApi.getSummary().then(setSummary).catch(() => setSummary(null));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // One-shot deep link: /performance?log_trade=TICKER (pattern: /status?expand_earnings)
  useEffect(() => {
    const t = new URLSearchParams(window.location.search).get("log_trade");
    if (!t) return;
    setForm({ mode: "create", ticker: t.toUpperCase() });
    const url = new URL(window.location.href);
    url.searchParams.delete("log_trade");
    window.history.replaceState({}, "", url.toString());
  }, []);

  return (
    <section className="px-4 py-4 border-t border-[var(--border)]">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--text-muted)]">
          Trade journal
        </h2>
        <button
          onClick={() => setForm({ mode: "create" })}
          data-print-hide="true"
          className="px-3 py-1 rounded-md border border-[var(--border)] text-xs font-semibold hover:bg-[var(--surface-alt)]"
        >
          Log trade
        </button>
      </div>

      {summary && summary.closed_count > 0 && (
        <DecisionVsOutcomePanel summary={summary} trades={trades} />
      )}
      <TradeList
        trades={trades}
        onEdit={(t) => setForm({ mode: "edit", trade: t })}
        onCloseTrade={(t) => setForm({ mode: "close", trade: t })}
        onChanged={refresh}
      />
      {summary && summary.by_exit_reason.length > 0 && (
        <ExitReasonTable rows={summary.by_exit_reason} />
      )}

      {form && (
        <TradeForm
          state={form}
          onDone={() => {
            setForm(null);
            refresh();
          }}
          onCancel={() => setForm(null)}
        />
      )}
    </section>
  );
}
```

- [ ] **Step 2: `TradeForm.tsx` (modal: create / edit / close)**

```tsx
"use client";

import { useEffect, useState } from "react";
import { journalApi } from "@/lib/api";
import type { ExitReason, LinkCandidate, TradeDirection } from "@/lib/api";
import type { FormState } from "./TradeJournalSection";

const EXIT_REASONS: { value: ExitReason; label: string }[] = [
  { value: "thesis_played_out", label: "Thesis played out" },
  { value: "kill_criterion", label: "Kill criterion" },
  { value: "stop_loss", label: "Stop loss" },
  { value: "better_opportunity", label: "Better opportunity" },
  { value: "rebalance", label: "Rebalance" },
  { value: "mistake", label: "Mistake" },
  { value: "other", label: "Other" },
];

const inputCls =
  "w-full rounded-md border border-[var(--border)] bg-[var(--bg)] px-2 py-1 text-sm";
const labelCls = "block text-[11px] uppercase tracking-wide text-[var(--text-muted)] mb-1";

export function TradeForm({
  state,
  onDone,
  onCancel,
}: {
  state: FormState;
  onDone: () => void;
  onCancel: () => void;
}) {
  const editing = state.mode !== "create" ? state.trade : null;
  const closing = state.mode === "close";

  const [ticker, setTicker] = useState(
    state.mode === "create" ? (state.ticker ?? "") : state.trade.ticker
  );
  const [direction, setDirection] = useState<TradeDirection>(editing?.direction ?? "long");
  const [entryDate, setEntryDate] = useState(editing?.entry_date ?? "");
  const [entryPrice, setEntryPrice] = useState(editing?.entry_price ?? "");
  const [quantity, setQuantity] = useState(editing?.quantity ?? "");
  const [rationale, setRationale] = useState(editing?.entry_rationale ?? "");
  const [outcomeId, setOutcomeId] = useState(editing?.outcome_id ?? "");
  const [exitDate, setExitDate] = useState(editing?.exit_date ?? "");
  const [exitPrice, setExitPrice] = useState(editing?.exit_price ?? "");
  const [exitReason, setExitReason] = useState<ExitReason | "">(editing?.exit_reason ?? "");
  const [exitNote, setExitNote] = useState(editing?.exit_note ?? "");

  const [candidates, setCandidates] = useState<LinkCandidate[]>([]);
  const [priceHint, setPriceHint] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Auto-fill hint: entry price for create, exit price for close.
  const hintDate = closing ? exitDate : entryDate;
  const hintSetter = closing ? setExitPrice : setEntryPrice;
  useEffect(() => {
    if (!ticker || !hintDate) return;
    let alive = true;
    journalApi
      .pricePreview(ticker, hintDate)
      .then((p) => {
        if (!alive) return;
        hintSetter((prev) => (prev ? prev : p.price));
        setPriceHint(
          p.price_date === hintDate
            ? `EOD close ${p.price}`
            : `EOD close ${p.price} (session ${p.price_date})`
        );
      })
      .catch(() => alive && setPriceHint("no price found — enter manually"));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ticker, hintDate]);

  // Link candidates for the ticker (create/edit only).
  useEffect(() => {
    if (closing || !ticker || ticker.length < 1) return;
    let alive = true;
    journalApi
      .linkCandidates(ticker)
      .then((c) => alive && setCandidates(c))
      .catch(() => alive && setCandidates([]));
    return () => {
      alive = false;
    };
  }, [ticker, closing]);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      if (state.mode === "create") {
        await journalApi.create({
          ticker,
          entry_date: entryDate,
          entry_price: entryPrice || undefined,
          quantity: quantity || undefined,
          direction,
          outcome_id: outcomeId || undefined,
          entry_rationale: rationale || undefined,
        });
      } else if (state.mode === "close") {
        await journalApi.update(state.trade.id, {
          exit_date: exitDate,
          exit_price: exitPrice || undefined,
          exit_reason: (exitReason || undefined) as ExitReason | undefined,
          exit_note: exitNote || undefined,
        });
      } else {
        await journalApi.update(state.trade.id, {
          entry_date: entryDate,
          entry_price: entryPrice || undefined,
          quantity: quantity || undefined,
          direction,
          outcome_id: outcomeId || undefined,
          entry_rationale: rationale || undefined,
        });
      }
      onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : "request failed");
    } finally {
      setBusy(false);
    }
  }

  const title =
    state.mode === "create" ? "Log trade" : state.mode === "close" ? `Close ${ticker}` : `Edit ${ticker}`;

  return (
    <div
      data-print-hide="true"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={onCancel}
    >
      <div
        className="w-full max-w-md rounded-xl border border-[var(--border)] bg-[var(--bg)] p-4 space-y-3"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-sm font-semibold">{title}</h3>

        {!closing && (
          <>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className={labelCls}>Ticker</label>
                <input
                  className={inputCls}
                  value={ticker}
                  onChange={(e) => setTicker(e.target.value.toUpperCase())}
                  disabled={state.mode !== "create"}
                />
              </div>
              <div>
                <label className={labelCls}>Direction</label>
                <select
                  className={inputCls}
                  value={direction}
                  onChange={(e) => setDirection(e.target.value as TradeDirection)}
                >
                  <option value="long">Long</option>
                  <option value="short">Short</option>
                </select>
              </div>
              <div>
                <label className={labelCls}>Entry date</label>
                <input
                  type="date"
                  className={inputCls}
                  value={entryDate}
                  onChange={(e) => setEntryDate(e.target.value)}
                />
              </div>
              <div>
                <label className={labelCls}>Entry price</label>
                <input
                  className={inputCls}
                  value={entryPrice}
                  onChange={(e) => setEntryPrice(e.target.value)}
                  placeholder="auto-fill"
                />
              </div>
              <div>
                <label className={labelCls}>Quantity (optional)</label>
                <input
                  className={inputCls}
                  value={quantity}
                  onChange={(e) => setQuantity(e.target.value)}
                />
              </div>
              <div>
                <label className={labelCls}>Linked thesis</label>
                <select
                  className={inputCls}
                  value={outcomeId}
                  onChange={(e) => setOutcomeId(e.target.value)}
                >
                  <option value="">— none —</option>
                  {candidates.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.verdict} · {c.source_type === "research_run" ? "research" : "workspace"} ·{" "}
                      {c.verdict_emitted_at.slice(0, 10)}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <div>
              <label className={labelCls}>Rationale</label>
              <textarea
                className={inputCls}
                rows={2}
                value={rationale}
                onChange={(e) => setRationale(e.target.value)}
              />
            </div>
          </>
        )}

        {closing && (
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={labelCls}>Exit date</label>
              <input
                type="date"
                className={inputCls}
                value={exitDate}
                onChange={(e) => setExitDate(e.target.value)}
              />
            </div>
            <div>
              <label className={labelCls}>Exit price</label>
              <input
                className={inputCls}
                value={exitPrice}
                onChange={(e) => setExitPrice(e.target.value)}
                placeholder="auto-fill"
              />
            </div>
            <div>
              <label className={labelCls}>Exit reason</label>
              <select
                className={inputCls}
                value={exitReason}
                onChange={(e) => setExitReason(e.target.value as ExitReason | "")}
              >
                <option value="">— select —</option>
                {EXIT_REASONS.map((r) => (
                  <option key={r.value} value={r.value}>
                    {r.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="col-span-2">
              <label className={labelCls}>Exit note</label>
              <textarea
                className={inputCls}
                rows={2}
                value={exitNote}
                onChange={(e) => setExitNote(e.target.value)}
              />
            </div>
          </div>
        )}

        {priceHint && <p className="text-xs text-[var(--text-muted)]">{priceHint}</p>}
        {error && <p className="text-xs text-rose-400">{error}</p>}

        <div className="flex justify-end gap-2 pt-1">
          <button
            onClick={onCancel}
            className="px-3 py-1 rounded-md text-xs text-[var(--text-muted)] hover:text-[var(--text)]"
          >
            Cancel
          </button>
          <button
            onClick={submit}
            disabled={busy || !ticker || (closing ? !exitDate : !entryDate)}
            className="px-3 py-1 rounded-md border border-[var(--border)] text-xs font-semibold hover:bg-[var(--surface-alt)] disabled:opacity-50"
          >
            {busy ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}
```

**Watch out:** `hintSetter((prev) => (prev ? prev : p.price))` requires the React setter functional form — both `setEntryPrice` and `setExitPrice` are `useState<string>` setters, so this works; it ensures auto-fill never clobbers a user-typed price.

- [ ] **Step 3: `TradeList.tsx`**

```tsx
"use client";

import Link from "next/link";
import { journalApi } from "@/lib/api";
import type { TradeDetail } from "@/lib/api";
import { ReturnCell } from "@/components/performance/ReturnCell";

function runHref(t: TradeDetail): string | null {
  if (!t.linked_outcome) return null;
  return t.linked_outcome.source_type === "research_run"
    ? `/pipeline/${t.linked_outcome.source_id}`
    : `/workspace/${t.linked_outcome.source_id}`;
}

function Row({
  t,
  onEdit,
  onCloseTrade,
  onChanged,
}: {
  t: TradeDetail;
  onEdit: (t: TradeDetail) => void;
  onCloseTrade: (t: TradeDetail) => void;
  onChanged: () => void;
}) {
  const href = runHref(t);
  return (
    <tr className="border-t border-[var(--border)]">
      <td className="px-2 py-1.5 font-semibold">
        {t.ticker}
        {t.direction === "short" && (
          <span className="ml-1 text-[10px] text-amber-400 uppercase">short</span>
        )}
      </td>
      <td className="px-2 py-1.5 text-[var(--text-muted)]">
        {t.entry_date} @ {Number(t.entry_price).toFixed(2)}
      </td>
      <td className="px-2 py-1.5 text-[var(--text-muted)]">
        {t.exit_date ? `${t.exit_date} @ ${Number(t.exit_price).toFixed(2)}` : "open"}
      </td>
      <td className="px-2 py-1.5 text-right">
        <ReturnCell value={t.returns?.return_pct ?? null} />
        {t.returns?.unrealized && (
          <span className="ml-1 text-[10px] text-[var(--text-muted)]">unrlzd</span>
        )}
      </td>
      <td className="px-2 py-1.5 text-right">
        <ReturnCell value={t.returns?.spy_excess_pct ?? null} />
      </td>
      <td className="px-2 py-1.5">
        {href ? (
          <Link href={href} className="text-xs underline decoration-dotted">
            {t.linked_outcome!.verdict}
          </Link>
        ) : (
          <span className="text-xs text-[var(--text-muted)]">—</span>
        )}
      </td>
      <td className="px-2 py-1.5 text-right" data-print-hide="true">
        <span className="inline-flex gap-2 text-xs">
          {t.status === "open" && (
            <button onClick={() => onCloseTrade(t)} className="underline decoration-dotted">
              close
            </button>
          )}
          <button onClick={() => onEdit(t)} className="underline decoration-dotted">
            edit
          </button>
          <button
            onClick={async () => {
              if (!window.confirm(`Delete ${t.ticker} trade?`)) return;
              await journalApi.remove(t.id).catch(() => {});
              onChanged();
            }}
            className="underline decoration-dotted text-rose-400"
          >
            delete
          </button>
        </span>
      </td>
    </tr>
  );
}

export function TradeList({
  trades,
  onEdit,
  onCloseTrade,
  onChanged,
}: {
  trades: TradeDetail[];
  onEdit: (t: TradeDetail) => void;
  onCloseTrade: (t: TradeDetail) => void;
  onChanged: () => void;
}) {
  if (trades.length === 0) {
    return (
      <p className="text-sm text-[var(--text-muted)] py-4">
        No trades logged yet. Decisions you log here get compared against the verdicts that
        motivated them.
      </p>
    );
  }
  const open = trades.filter((t) => t.status === "open");
  const closed = trades.filter((t) => t.status === "closed");
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-[11px] uppercase tracking-wide text-[var(--text-muted)]">
            <th className="px-2 py-1">Ticker</th>
            <th className="px-2 py-1">Entry</th>
            <th className="px-2 py-1">Exit</th>
            <th className="px-2 py-1 text-right">Return</th>
            <th className="px-2 py-1 text-right">vs SPY</th>
            <th className="px-2 py-1">Thesis</th>
            <th className="px-2 py-1" />
          </tr>
        </thead>
        <tbody>
          {[...open, ...closed].map((t) => (
            <Row key={t.id} t={t} onEdit={onEdit} onCloseTrade={onCloseTrade} onChanged={onChanged} />
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 4: `DecisionVsOutcomePanel.tsx`**

```tsx
"use client";

import type { JournalSummary, TradeDetail } from "@/lib/api";
import { ReturnCell } from "@/components/performance/ReturnCell";

function Stat({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-alt)] px-3 py-2">
      <div className="text-[11px] uppercase tracking-wide text-[var(--text-muted)]">{label}</div>
      <div className="text-sm font-semibold">{children}</div>
    </div>
  );
}

export function DecisionVsOutcomePanel({
  summary,
  trades,
}: {
  summary: JournalSummary;
  trades: TradeDetail[];
}) {
  const compared = trades.filter((t) => t.comparison != null);
  return (
    <div className="mb-4 space-y-3">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        <Stat label="Hit rate (vs SPY)">
          {summary.hit_rate == null ? "—" : `${(summary.hit_rate * 100).toFixed(0)}%`}
        </Stat>
        <Stat label="Avg excess">
          <ReturnCell value={summary.avg_spy_excess_pct} />
        </Stat>
        <Stat label="Execution vs paper">
          {summary.execution_vs_paper.n === 0 ? (
            "—"
          ) : (
            <ReturnCell value={summary.execution_vs_paper.avg_delta_pct} />
          )}
        </Stat>
        <Stat label="Theses traded">
          {summary.coverage.outcomes_total === 0
            ? "—"
            : `${summary.coverage.outcomes_traded}/${summary.coverage.outcomes_total}`}
        </Stat>
      </div>

      {compared.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-[var(--border)]">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[11px] uppercase tracking-wide text-[var(--text-muted)]">
                <th className="px-2 py-1">Ticker</th>
                <th className="px-2 py-1 text-right">Trade return</th>
                <th className="px-2 py-1 text-right">Trade vs SPY</th>
                <th className="px-2 py-1 text-right">Paper</th>
                <th className="px-2 py-1 text-right">Paper vs SPY</th>
                <th className="px-2 py-1 text-right">Execution Δ</th>
              </tr>
            </thead>
            <tbody>
              {compared.map((t) => (
                <tr key={t.id} className="border-t border-[var(--border)]">
                  <td className="px-2 py-1.5 font-semibold">{t.ticker}</td>
                  <td className="px-2 py-1.5 text-right">
                    <ReturnCell value={t.comparison!.trade_return_pct} />
                  </td>
                  <td className="px-2 py-1.5 text-right">
                    <ReturnCell value={t.comparison!.trade_spy_excess_pct} />
                  </td>
                  <td className="px-2 py-1.5 text-right">
                    <ReturnCell value={t.comparison!.paper_return_pct} />
                    <span className="ml-1 text-[10px] text-[var(--text-muted)]">
                      @{t.comparison!.offset}
                    </span>
                  </td>
                  <td className="px-2 py-1.5 text-right">
                    <ReturnCell value={t.comparison!.paper_spy_excess_pct} />
                  </td>
                  <td className="px-2 py-1.5 text-right">
                    <ReturnCell value={t.comparison!.execution_delta_pct} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 5: `ExitReasonTable.tsx`**

```tsx
"use client";

import type { ExitReasonStat } from "@/lib/api";
import { ReturnCell } from "@/components/performance/ReturnCell";

const LABELS: Record<string, string> = {
  thesis_played_out: "Thesis played out",
  kill_criterion: "Kill criterion",
  stop_loss: "Stop loss",
  better_opportunity: "Better opportunity",
  rebalance: "Rebalance",
  mistake: "Mistake",
  other: "Other",
  unspecified: "Unspecified",
};

export function ExitReasonTable({ rows }: { rows: ExitReasonStat[] }) {
  return (
    <div className="mt-4">
      <h3 className="text-[11px] uppercase tracking-wide text-[var(--text-muted)] mb-1">
        By exit reason
      </h3>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-[11px] uppercase tracking-wide text-[var(--text-muted)]">
            <th className="px-2 py-1">Reason</th>
            <th className="px-2 py-1 text-right">Trades</th>
            <th className="px-2 py-1 text-right">Avg return</th>
            <th className="px-2 py-1 text-right">Avg vs SPY</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.exit_reason} className="border-t border-[var(--border)]">
              <td className="px-2 py-1.5">{LABELS[r.exit_reason] ?? r.exit_reason}</td>
              <td className="px-2 py-1.5 text-right">{r.count}</td>
              <td className="px-2 py-1.5 text-right">
                <ReturnCell value={r.avg_return_pct} />
              </td>
              <td className="px-2 py-1.5 text-right">
                <ReturnCell value={r.avg_spy_excess_pct} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 6: Wire into `/performance`**

In `frontend/app/performance/page.tsx`, add the import:

```tsx
import { TradeJournalSection } from "@/components/journal/TradeJournalSection";
```

and render it after `<OutcomeList outcomes={outcomes} />`:

```tsx
      <OutcomeList outcomes={outcomes} />
      <TradeJournalSection />
```

- [ ] **Step 7: Build + lint**

```bash
cd frontend && npm run build && npm run lint
```

Expected: clean build, no lint errors. With the backend up (`uvicorn backend.app.main:app --reload` from project root, frontend on `NEXT_PUBLIC_API_URL=http://127.0.0.1:8000`), visit `/performance`: empty-journal copy renders; "Log trade" opens the modal; picking a date fills the price hint.

- [ ] **Step 8: Commit**

```bash
git add frontend/components/journal/ frontend/app/performance/page.tsx
git commit -m "feat(journal): trade-journal section on /performance"
```

---

### Task 7: Entry-point buttons (status board + company header)

**Files:**
- Modify: `frontend/app/status/page.tsx` (~line 637, next to `<WorkspaceButton …/>`)
- Modify: `frontend/components/company/CompanyHeader.tsx`

- [ ] **Step 1: Status board button**

In `frontend/app/status/page.tsx`, immediately before `<WorkspaceButton ticker={e.ticker} researchRunId={e.run_id} />` (line ~637), add:

```tsx
                      <Link
                        href={`/performance?log_trade=${e.ticker}`}
                        data-print-hide="true"
                        className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full border border-[var(--border)] text-[11px] font-semibold text-[var(--text-muted)] hover:text-[var(--text)]"
                      >
                        Log trade
                      </Link>
```

Check the top of the file for `import Link from "next/link";` — add it if missing.

- [ ] **Step 2: Company header button**

In `frontend/components/company/CompanyHeader.tsx`, add `import Link from "next/link";` at the top, then replace the trailing `<LensSelector />` with:

```tsx
      <div className="flex items-center gap-2">
        <Link
          href={`/performance?log_trade=${ticker}`}
          data-print-hide="true"
          className="px-2 py-0.5 rounded-md border border-[var(--border)] text-[11px] font-semibold text-[var(--text-muted)] hover:text-[var(--text)]"
        >
          Log trade
        </Link>
        <LensSelector />
      </div>
```

- [ ] **Step 3: Build + lint + visual check**

```bash
cd frontend && npm run build && npm run lint
```

Expected: clean. Visit `/status` and `/company/NVDA` — both show the button; clicking lands on `/performance` with the form pre-opened and ticker prefilled (one-shot: refresh doesn't reopen).

- [ ] **Step 4: Commit**

```bash
git add frontend/app/status/page.tsx frontend/components/company/CompanyHeader.tsx
git commit -m "feat(journal): Log-trade entry points on status board + company header"
```

---

### Task 8: Verification sweep + docs

**Files:**
- Modify: `TODO.md` (Done-recent entry)
- Modify: `CLAUDE.md` (short "Trade journal" architecture note)

- [ ] **Step 1: Full backend suite**

```bash
backend/venv/bin/python -m unittest $(ls backend/tests/test_*.py | sed 's|/|.|g; s|\.py$||' | tr '\n' ' ')
```

Expected: all green (323 pre-existing + ~25 new).

- [ ] **Step 2: Frontend build + lint**

```bash
cd frontend && npm run build && npm run lint
```

Expected: clean.

- [ ] **Step 3: End-to-end smoke (live backend + DB)**

With uvicorn running and the migration applied:

```bash
curl -s -X POST http://127.0.0.1:8000/api/journal/trades \
  -H 'Content-Type: application/json' \
  -d '{"ticker": "NVDA", "entry_date": "2026-06-01"}' | python3 -m json.tool
curl -s http://127.0.0.1:8000/api/journal/summary | python3 -m json.tool
curl -s "http://127.0.0.1:8000/api/journal/price-preview?ticker=NVDA&date=2026-06-07" | python3 -m json.tool
```

Expected: 201 trade with `entry_price_source: "fmp_eod_adjusted"` and non-null `spy_entry_price`; summary with `open_count: 1`; preview returning the 2026-06-05 Friday close (the 7th was a Sunday). Delete the smoke trade afterwards via the API.

- [ ] **Step 4: Update TODO.md**

Add to "Done (recent)" summarizing: trade journal table/service/API, decision-vs-outcome comparison on /performance, entry points, test counts, migration id.

- [ ] **Step 5: Update CLAUDE.md**

Add a short section after the "Status board, catalysts, and questions" block:

```markdown
### Trade journal (read this before touching `backend/app/services/journal*.py` or `frontend/components/journal/`)

Manual entry/exit trade log linked to `verdict_outcomes` (nullable FK, SET NULL). One row = one entry + one exit; null `exit_date` = open. `services/journal.py` is **commit-free** (callers own the session); `services/journal_comparison.py` is pure math — fractional returns, direction-aware (short = −long), SPY excess = trade − SPY over the holding period. Decision-vs-paper comparison picks the outcome snapshot at the offset nearest the holding period (`nearest_offset` midpoint thresholds 4/18/60/136 days) — labeled, never interpolated. `/api/journal`: trades CRUD (PATCH closes; explicit `exit_date: null` reopens + clears exit fields), `summary`, `price-preview` (FMP adjusted close on-or-before, 7-day lookback), `link-candidates` (non-superseded outcomes by ticker — lives here because `/api/outcomes` has no ticker filter). Price auto-fill is editable (`*_price_source`: `manual` | `fmp_eod_adjusted`); FMP failures degrade (SPY columns null, preview 404, no 500s). Frontend: journal section on `/performance` (`components/journal/`), "Log trade" buttons on status board + company header deep-link `/performance?log_trade=TICKER` (one-shot). Open-trade marks use live quotes (unadjusted vs adjClose entry — accepted approximation).
```

- [ ] **Step 6: Commit**

```bash
git add TODO.md CLAUDE.md
git commit -m "docs(journal): TODO done-log + CLAUDE.md trade-journal section"
```

---

## Out of scope (do not build)

Position-sizing analytics, Sharpe/drawdown, multi-leg lots, broker import, status-board open-trade badge, dividend-adjusting unrealized marks. Recorded in the spec.

"""Tests for backend.app.services.outcome_tracker."""
from __future__ import annotations

import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

from backend.app.services.outcome_tracker import (
    all_offset_keys,
    calendar_target,
)


class TestOffsetMath(unittest.TestCase):
    def test_calendar_target_known_offsets(self):
        base = date(2026, 1, 1)
        self.assertEqual(calendar_target(base, "1d"), date(2026, 1, 2))
        self.assertEqual(calendar_target(base, "1w"), date(2026, 1, 8))
        self.assertEqual(calendar_target(base, "1m"), date(2026, 1, 31))
        self.assertEqual(calendar_target(base, "3m"), date(2026, 4, 1))
        self.assertEqual(calendar_target(base, "6m"), date(2026, 6, 30))

    def test_calendar_target_unknown_raises(self):
        with self.assertRaises(ValueError):
            calendar_target(date(2026, 1, 1), "9999")

    def test_all_offset_keys_ordered(self):
        self.assertEqual(all_offset_keys(), ["1d", "1w", "1m", "3m", "6m"])


import asyncio
from unittest.mock import AsyncMock, MagicMock

from backend.app.services.outcome_tracker import _resolve_entry_prices


def _mock_fmp_price_series(prices_by_ticker_by_date: dict[str, dict[date, Decimal]]):
    """Build an FMPClient mock whose get_historical_price_adjusted returns OHLCV rows.

    prices_by_ticker_by_date: {ticker: {date: close}}
    Mirrors the real FMPClient.get_historical_price_adjusted(ticker, from_date: str, to_date: str)
    which returns tuple[list[dict], Citation] with rows having {date: str, close: ...}
    where close is split + dividend adjusted.
    """
    mock = MagicMock()

    async def get_historical_price_adjusted(symbol: str, from_date: str, to_date: str):
        start = date.fromisoformat(from_date)
        end = date.fromisoformat(to_date)
        rows = []
        for d, px in sorted(prices_by_ticker_by_date.get(symbol, {}).items()):
            if start <= d <= end:
                rows.append({"date": d.isoformat(), "close": float(px)})
        return rows, None  # tuple[list, Citation | None]

    mock.get_historical_price_adjusted = AsyncMock(side_effect=get_historical_price_adjusted)
    return mock


class TestResolveEntryPrices(unittest.TestCase):
    def test_resolves_to_next_trading_day(self):
        # Verdict emitted Friday 2026-01-02; Monday 2026-01-05 is the first trading day
        prices = {
            "NVDA": {date(2026, 1, 5): Decimal("850.00"), date(2026, 1, 6): Decimal("855.00")},
            "SPY":  {date(2026, 1, 5): Decimal("550.00"), date(2026, 1, 6): Decimal("552.00")},
        }
        fmp = _mock_fmp_price_series(prices)

        bundle = asyncio.run(_resolve_entry_prices(
            ticker="NVDA",
            verdict_emitted_at=datetime(2026, 1, 2, 22, 0, tzinfo=timezone.utc),
            theme_seed_tickers=None,
            sector_etf_ticker=None,
            fmp=fmp,
        ))
        self.assertEqual(bundle.entry_price_at, date(2026, 1, 5))
        self.assertEqual(bundle.ticker_price, Decimal("850.00"))
        self.assertEqual(bundle.spy_price, Decimal("550.00"))
        self.assertIsNone(bundle.sector_etf_ticker)
        self.assertEqual(bundle.theme_basket_constituents, [])

    def test_includes_theme_constituents(self):
        prices = {
            "NVDA": {date(2026, 1, 5): Decimal("850.00")},
            "SPY":  {date(2026, 1, 5): Decimal("550.00")},
            "AMD":  {date(2026, 1, 5): Decimal("180.00")},
            "TSM":  {date(2026, 1, 5): Decimal("110.00")},
        }
        fmp = _mock_fmp_price_series(prices)
        bundle = asyncio.run(_resolve_entry_prices(
            ticker="NVDA",
            verdict_emitted_at=datetime(2026, 1, 2, 22, 0, tzinfo=timezone.utc),
            theme_seed_tickers=["NVDA", "AMD", "TSM"],
            sector_etf_ticker=None,
            fmp=fmp,
        ))
        tickers = {c.ticker for c in bundle.theme_basket_constituents}
        self.assertEqual(tickers, {"NVDA", "AMD", "TSM"})

    def test_raises_when_ticker_has_no_price_in_lookahead(self):
        prices = {"SPY": {date(2026, 1, 5): Decimal("550.00")}}
        fmp = _mock_fmp_price_series(prices)
        with self.assertRaises(LookupError):
            asyncio.run(_resolve_entry_prices(
                ticker="NVDA",
                verdict_emitted_at=datetime(2026, 1, 2, 22, 0, tzinfo=timezone.utc),
                theme_seed_tickers=None,
                sector_etf_ticker=None,
                fmp=fmp,
            ))


from backend.app.services.outcome_tracker import _resolve_sector_etf


class TestResolveSectorEtf(unittest.TestCase):
    def test_returns_etf_for_mapped_sector(self):
        async def _run():
            db = MagicMock()
            db.execute = AsyncMock(return_value=MagicMock(
                scalar_one_or_none=MagicMock(return_value="XLK")
            ))
            return await _resolve_sector_etf(sector="Technology", db=db)

        self.assertEqual(asyncio.run(_run()), "XLK")

    def test_returns_none_for_unmapped_or_null(self):
        async def _run(sector):
            db = MagicMock()
            db.execute = AsyncMock(return_value=MagicMock(
                scalar_one_or_none=MagicMock(return_value=None)
            ))
            return await _resolve_sector_etf(sector=sector, db=db)

        self.assertIsNone(asyncio.run(_run(None)))
        self.assertIsNone(asyncio.run(_run("Cryptocurrency")))


from backend.app.services.outcome_tracker import (
    build_research_run_signal_snapshot,
    build_workspace_run_signal_snapshot,
    compute_basket_value,
)


class TestComputeBasketValue(unittest.TestCase):
    def test_equal_weighted_basket(self):
        # NVDA: 850 → 935 (+10%); AMD: 180 → 198 (+10%); TSM: 110 → 110 (0%) → basket value 106.67
        constituents = [
            {"ticker": "NVDA", "entry_price": Decimal("850.00")},
            {"ticker": "AMD",  "entry_price": Decimal("180.00")},
            {"ticker": "TSM",  "entry_price": Decimal("110.00")},
        ]
        current_prices = {
            "NVDA": Decimal("935.00"),
            "AMD":  Decimal("198.00"),
            "TSM":  Decimal("110.00"),
        }
        value = compute_basket_value(constituents, current_prices)
        # mean of (935/850, 198/180, 110/110) * 100 = mean(1.1, 1.1, 1.0) * 100 = 106.6667
        self.assertAlmostEqual(float(value), 106.6667, places=3)

    def test_drops_missing_constituent(self):
        constituents = [
            {"ticker": "NVDA", "entry_price": Decimal("100.00")},
            {"ticker": "AMD",  "entry_price": Decimal("100.00")},
        ]
        # AMD has no current price → only NVDA averaged. (110/100)*100 = 110.
        value = compute_basket_value(constituents, {"NVDA": Decimal("110.00")})
        self.assertAlmostEqual(float(value), 110.0, places=3)

    def test_returns_none_when_all_missing(self):
        constituents = [{"ticker": "NVDA", "entry_price": Decimal("100.00")}]
        self.assertIsNone(compute_basket_value(constituents, {}))


class TestSignalSnapshotBuilders(unittest.TestCase):
    def test_research_run_snapshot_shape(self):
        state = MagicMock()
        state.deep_dive_results = {
            "Business Quality": MagicMock(score=72),
            "Risk Assessment":  MagicMock(score=58),
        }
        signals_row = {"velocity": 12.3, "fundamental": 0.78, "discovery": 0.65, "surprise": None}
        kill_states = [{"ordinal": 1, "state": "armed"}]

        snap = build_research_run_signal_snapshot(
            state=state, signals_row=signals_row, kill_states=kill_states
        )
        self.assertEqual(snap["signals_row"], signals_row)
        self.assertEqual(snap["deep_dive_scores"]["Business Quality"], 72)
        self.assertEqual(snap["kill_criterion_state"], kill_states)
        self.assertNotIn("workspace_step_verdicts", snap)

    def test_workspace_run_snapshot_shape(self):
        run = MagicMock()
        run.step_outputs = {
            "update_refresh": {"verdict": "healthy"},
            "challenge":      {"proposed_verdict": "imminent"},
        }
        signals_row = {"velocity": 5.0, "fundamental": 0.5, "discovery": 0.3, "surprise": None}
        model_assumptions = {"discount_rate": 0.10, "terminal_growth": 0.025}

        snap = build_workspace_run_signal_snapshot(
            run=run, signals_row=signals_row, kill_states=[],
            model_assumptions=model_assumptions,
        )
        self.assertEqual(snap["signals_row"], signals_row)
        self.assertEqual(snap["workspace_step_verdicts"]["challenge"], "imminent")
        self.assertEqual(snap["model_assumptions"], model_assumptions)
        self.assertNotIn("deep_dive_scores", snap)


from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession as SAAsyncSession
from sqlalchemy.orm import sessionmaker
from backend.app.models.outcome import VerdictOutcome, SectorEtfMapping
from backend.app.services.outcome_tracker import record_verdict

# Raw DDL for the two tables needed in outcome tests.
# We bypass Base.metadata.create_all for two reasons:
#   1. counterparty_aliases has a duplicate-index bug (index=True + explicit Index()),
#      which causes OperationalError on every new sqlite engine.
#   2. VerdictOutcome has a FK to themes.id — SQLAlchemy tries to resolve this during
#      DDL sort even on sqlite, so we'd need themes in the metadata too (pulling in
#      more transitive deps). Raw DDL sidesteps all of this cleanly.
_DDL_SECTOR_ETF = """
CREATE TABLE IF NOT EXISTS sector_etf_mapping (
    fmp_sector TEXT PRIMARY KEY,
    etf_ticker TEXT NOT NULL,
    notes TEXT
)
"""

_DDL_VERDICT_OUTCOMES = """
CREATE TABLE IF NOT EXISTS verdict_outcomes (
    id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,
    source_id TEXT NOT NULL,
    ticker TEXT NOT NULL,
    theme_id TEXT,
    verdict TEXT NOT NULL,
    verdict_emitted_at TEXT NOT NULL,
    entry_price_at TEXT NOT NULL,
    entry_price NUMERIC NOT NULL,
    entry_price_source TEXT NOT NULL DEFAULT 'fmp_historical_eod_adjusted',
    spy_entry_price NUMERIC,
    sector_etf_ticker TEXT,
    sector_etf_entry_price NUMERIC,
    theme_basket_entry_value NUMERIC,
    theme_basket_constituents TEXT,
    signal_snapshot TEXT,
    superseded_at TEXT,
    superseded_by_outcome_id TEXT,
    realized_ticker_return_pct NUMERIC,
    realized_spy_excess_pct NUMERIC,
    realized_sector_excess_pct NUMERIC,
    realized_theme_basket_excess_pct NUMERIC,
    closed_at TEXT,
    created_at TEXT,
    UNIQUE (source_type, source_id)
)
"""


def _build_async_test_session():
    """Spin up an in-memory async sqlite engine + session for ORM tests.

    Uses raw DDL to avoid two problems with Base.metadata.create_all:
    - counterparty_aliases duplicate-index bug causes OperationalError.
    - VerdictOutcome FK to themes.id requires themes table in metadata.

    JSONB columns become TEXT in sqlite; ORM round-trip preserves dict values.
    SQLite doesn't enforce FK constraints, so the theme_id FK is safe to omit.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)

    async def _setup():
        async with engine.begin() as conn:
            await conn.execute(text(_DDL_SECTOR_ETF))
            await conn.execute(text(_DDL_VERDICT_OUTCOMES))

    asyncio.run(_setup())
    Session = sessionmaker(engine, class_=SAAsyncSession, expire_on_commit=False)
    return engine, Session


class TestRecordVerdict(unittest.TestCase):
    def test_creates_outcome_with_all_three_benchmark_entries(self):
        engine, Session = _build_async_test_session()

        async def _run():
            async with Session() as db:
                db.add(SectorEtfMapping(fmp_sector="Technology", etf_ticker="XLK"))
                await db.commit()

                prices = {
                    "NVDA": {date(2026, 1, 5): Decimal("850.00")},
                    "SPY":  {date(2026, 1, 5): Decimal("550.00")},
                    "XLK":  {date(2026, 1, 5): Decimal("200.00")},
                    "AMD":  {date(2026, 1, 5): Decimal("180.00")},
                }
                fmp = _mock_fmp_price_series(prices)

                outcome = await record_verdict(
                    source_type="research_run",
                    source_id=str(uuid4()),
                    ticker="NVDA",
                    theme_id=None,
                    theme_seed_tickers=["NVDA", "AMD"],
                    sector="Technology",
                    verdict="completed",
                    verdict_emitted_at=datetime(2026, 1, 2, 22, 0, tzinfo=timezone.utc),
                    signal_snapshot={"signals_row": {"velocity": 12.3}},
                    fmp=fmp,
                    db=db,
                )
                await db.commit()
                return outcome

        outcome = asyncio.run(_run())
        self.assertEqual(outcome.ticker, "NVDA")
        self.assertEqual(outcome.entry_price_at, date(2026, 1, 5))
        self.assertEqual(outcome.entry_price, Decimal("850.00"))
        self.assertEqual(outcome.spy_entry_price, Decimal("550.00"))
        self.assertEqual(outcome.sector_etf_ticker, "XLK")
        self.assertEqual(outcome.sector_etf_entry_price, Decimal("200.00"))
        self.assertEqual(outcome.theme_basket_entry_value, Decimal("100"))
        self.assertEqual(len(outcome.theme_basket_constituents), 2)

    def test_idempotent_on_source_id(self):
        engine, Session = _build_async_test_session()
        source_id = str(uuid4())

        async def _run():
            async with Session() as db:
                prices = {"NVDA": {date(2026, 1, 5): Decimal("850.00")},
                          "SPY": {date(2026, 1, 5): Decimal("550.00")}}
                fmp = _mock_fmp_price_series(prices)

                first = await record_verdict(
                    source_type="research_run", source_id=source_id, ticker="NVDA",
                    theme_id=None, theme_seed_tickers=None, sector=None,
                    verdict="completed",
                    verdict_emitted_at=datetime(2026, 1, 2, 22, 0, tzinfo=timezone.utc),
                    signal_snapshot=None, fmp=fmp, db=db,
                )
                await db.commit()
                second = await record_verdict(
                    source_type="research_run", source_id=source_id, ticker="NVDA",
                    theme_id=None, theme_seed_tickers=None, sector=None,
                    verdict="completed",
                    verdict_emitted_at=datetime(2026, 1, 2, 22, 0, tzinfo=timezone.utc),
                    signal_snapshot=None, fmp=fmp, db=db,
                )
                return first.id, second.id

        first_id, second_id = asyncio.run(_run())
        self.assertEqual(first_id, second_id)

    def test_unmapped_sector_leaves_sector_columns_null(self):
        engine, Session = _build_async_test_session()

        async def _run():
            async with Session() as db:
                prices = {"NVDA": {date(2026, 1, 5): Decimal("850.00")},
                          "SPY": {date(2026, 1, 5): Decimal("550.00")}}
                fmp = _mock_fmp_price_series(prices)
                outcome = await record_verdict(
                    source_type="research_run", source_id=str(uuid4()), ticker="NVDA",
                    theme_id=None, theme_seed_tickers=None, sector="Cryptocurrency",
                    verdict="completed",
                    verdict_emitted_at=datetime(2026, 1, 2, 22, 0, tzinfo=timezone.utc),
                    signal_snapshot=None, fmp=fmp, db=db,
                )
                await db.commit()
                return outcome

        outcome = asyncio.run(_run())
        self.assertIsNone(outcome.sector_etf_ticker)
        self.assertIsNone(outcome.sector_etf_entry_price)

    def test_no_supersede_when_no_prior(self):
        engine, Session = _build_async_test_session()

        async def _run():
            async with Session() as db:
                prices = {"NVDA": {date(2026, 1, 5): Decimal("850.00")},
                          "SPY": {date(2026, 1, 5): Decimal("550.00")}}
                fmp = _mock_fmp_price_series(prices)
                outcome = await record_verdict(
                    source_type="research_run", source_id=str(uuid4()), ticker="NVDA",
                    theme_id=None, theme_seed_tickers=None, sector=None,
                    verdict="completed",
                    verdict_emitted_at=datetime(2026, 1, 2, 22, 0, tzinfo=timezone.utc),
                    signal_snapshot=None, fmp=fmp, db=db,
                )
                await db.commit()
                return outcome

        outcome = asyncio.run(_run())
        self.assertIsNone(outcome.superseded_at)


if __name__ == "__main__":
    unittest.main()

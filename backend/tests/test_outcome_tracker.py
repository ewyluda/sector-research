"""Tests for backend.app.services.outcome_tracker."""
from __future__ import annotations

import unittest
from datetime import date, datetime, timezone
from decimal import Decimal

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


if __name__ == "__main__":
    unittest.main()

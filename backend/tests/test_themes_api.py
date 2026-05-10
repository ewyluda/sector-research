"""Pins themes-endpoint contract: ticker normalization on POST/PUT and
atomic add/remove sub-routes that idempotently mutate ``seed_tickers``."""

import os
import unittest
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("SEC_USER_AGENT", "test")
os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

from fastapi import HTTPException

from backend.app.api.themes import (
    TickerPayload,
    ThemeCreate,
    _normalize_tickers,
    add_theme_ticker,
    create_theme,
    remove_theme_ticker,
    update_theme,
)
from backend.app.models.theme import Theme


def _theme(tickers: list | None = None) -> Theme:
    return Theme(
        id="t1",
        name="AI Infra",
        description=None,
        parent_theme_id=None,
        seed_tickers=tickers if tickers is not None else [],
        screener_criteria={},
        x_search_terms=[],
        signal_weights={
            "x_velocity": 0.40,
            "fundamental_quality": 0.40,
            "discovery": 0.20,
        },
    )


def _mock_db_returning(theme: Theme | None) -> MagicMock:
    db = MagicMock()
    scalar_result = MagicMock()
    scalar_result.scalar_one_or_none.return_value = theme
    db.execute = AsyncMock(return_value=scalar_result)
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock()
    return db


class NormalizeTickersTests(unittest.TestCase):
    def test_uppercase_strip_dedupe_preserves_order(self):
        self.assertEqual(
            _normalize_tickers(["nvda", " AMD", "nvda ", "msft"]),
            ["NVDA", "AMD", "MSFT"],
        )

    def test_drops_empties_and_whitespace_only(self):
        self.assertEqual(
            _normalize_tickers(["NVDA", "", "  ", "AMD"]), ["NVDA", "AMD"]
        )

    def test_handles_none_and_empty(self):
        self.assertEqual(_normalize_tickers(None), [])
        self.assertEqual(_normalize_tickers([]), [])

    def test_tolerates_legacy_dict_shape(self):
        self.assertEqual(
            _normalize_tickers([{"ticker": "nvda"}, "AMD", {"other": "x"}]),
            ["NVDA", "AMD"],
        )


class CreateThemeNormalizationTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_normalizes_seed_tickers(self):
        db = _mock_db_returning(None)
        payload = ThemeCreate(name="X", seed_tickers=["nvda", " AMD ", "nvda"])
        await create_theme(payload, db=db)
        added = db.add.call_args.args[0]
        self.assertEqual(added.seed_tickers, ["NVDA", "AMD"])


class UpdateThemeNormalizationTests(unittest.IsolatedAsyncioTestCase):
    async def test_update_normalizes_seed_tickers(self):
        theme = _theme(["NVDA"])
        db = _mock_db_returning(theme)
        payload = ThemeCreate(name="X", seed_tickers=["msft", "AMD", "msft "])
        result = await update_theme("t1", payload, db=db)
        self.assertEqual(result.seed_tickers, ["MSFT", "AMD"])

    async def test_update_404_when_missing(self):
        db = _mock_db_returning(None)
        payload = ThemeCreate(name="X")
        with self.assertRaises(HTTPException) as ctx:
            await update_theme("missing", payload, db=db)
        self.assertEqual(ctx.exception.status_code, 404)


class AddTickerEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_appends_new_ticker(self):
        theme = _theme(["NVDA"])
        db = _mock_db_returning(theme)
        result = await add_theme_ticker(
            "t1", TickerPayload(ticker="amd"), db=db
        )
        self.assertEqual(result.seed_tickers, ["NVDA", "AMD"])
        db.commit.assert_awaited_once()

    async def test_idempotent_on_duplicate(self):
        theme = _theme(["NVDA", "AMD"])
        db = _mock_db_returning(theme)
        result = await add_theme_ticker(
            "t1", TickerPayload(ticker="nvda"), db=db
        )
        self.assertEqual(result.seed_tickers, ["NVDA", "AMD"])
        db.commit.assert_not_awaited()

    async def test_404_when_theme_missing(self):
        db = _mock_db_returning(None)
        with self.assertRaises(HTTPException) as ctx:
            await add_theme_ticker(
                "missing", TickerPayload(ticker="NVDA"), db=db
            )
        self.assertEqual(ctx.exception.status_code, 404)

    async def test_400_when_ticker_empty(self):
        db = _mock_db_returning(_theme())
        with self.assertRaises(HTTPException) as ctx:
            await add_theme_ticker("t1", TickerPayload(ticker="   "), db=db)
        self.assertEqual(ctx.exception.status_code, 400)


class RemoveTickerEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_removes_present_ticker(self):
        theme = _theme(["NVDA", "AMD", "MSFT"])
        db = _mock_db_returning(theme)
        result = await remove_theme_ticker("t1", "amd", db=db)
        self.assertEqual(result.seed_tickers, ["NVDA", "MSFT"])
        db.commit.assert_awaited_once()

    async def test_idempotent_on_absent(self):
        theme = _theme(["NVDA", "AMD"])
        db = _mock_db_returning(theme)
        result = await remove_theme_ticker("t1", "TSLA", db=db)
        self.assertEqual(result.seed_tickers, ["NVDA", "AMD"])
        db.commit.assert_not_awaited()

    async def test_404_when_theme_missing(self):
        db = _mock_db_returning(None)
        with self.assertRaises(HTTPException) as ctx:
            await remove_theme_ticker("missing", "NVDA", db=db)
        self.assertEqual(ctx.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()

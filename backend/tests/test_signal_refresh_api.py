"""Pins POST /api/themes/{theme_id}/signals/refresh contract: 404 unknown
theme, delegates to refresh_theme_signals with app.state clients, returns
the summary dict."""

import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("SEC_USER_AGENT", "test")
os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

from fastapi import HTTPException

from backend.app.api.discovery import refresh_theme_signals_endpoint
from backend.app.models.theme import Theme


def _theme(id_: str = "t1", name: str = "AI Infra") -> Theme:
    return Theme(id=id_, name=name, x_search_terms=[], seed_tickers=[])


def _request_with_clients() -> MagicMock:
    request = MagicMock()
    request.app.state.fmp = MagicMock(name="fmp")
    request.app.state.x_client = MagicMock(name="x_client")
    return request


class RefreshThemeSignalsEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_404_when_theme_missing(self):
        db = MagicMock()
        scalar_result = MagicMock()
        scalar_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=scalar_result)

        with self.assertRaises(HTTPException) as ctx:
            await refresh_theme_signals_endpoint(
                theme_id="missing",
                request=_request_with_clients(),
                db=db,
            )
        self.assertEqual(ctx.exception.status_code, 404)

    async def test_delegates_and_returns_summary(self):
        theme = _theme()
        db = MagicMock()
        scalar_result = MagicMock()
        scalar_result.scalar_one_or_none.return_value = theme
        db.execute = AsyncMock(return_value=scalar_result)

        request = _request_with_clients()
        expected_summary = {
            "theme": theme.name,
            "processed": 3,
            "errors": 1,
            "surprises_fired": 0,
        }

        with patch(
            "backend.app.api.discovery.refresh_theme_signals",
            new=AsyncMock(return_value=expected_summary),
        ) as mock_refresh:
            result = await refresh_theme_signals_endpoint(
                theme_id=str(theme.id),
                request=request,
                db=db,
            )

        self.assertEqual(result, expected_summary)
        mock_refresh.assert_awaited_once()
        kwargs = mock_refresh.await_args.kwargs
        self.assertIs(kwargs["theme"], theme)
        self.assertIs(kwargs["fmp"], request.app.state.fmp)
        self.assertIs(kwargs["x_client"], request.app.state.x_client)
        self.assertIs(kwargs["db"], db)


if __name__ == "__main__":
    unittest.main()

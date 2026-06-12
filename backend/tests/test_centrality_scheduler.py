"""Pins refresh_theme_centrality in signal_scheduler.py.

Covers:
  - build_theme_graph returns None → no persist, skip reason in summary
  - build_theme_graph returns too_dense graph → no persist, skip reason
  - graph passes density gate but compute returns {} → no persist, skip reason
  - normal path → _persist_signal_set called once per scored ticker with
    {"centrality": <dict with "modifier">} and the SAME computed_at for all
    tickers; db.commit() called exactly once after the loop
  - build_theme_graph raises RuntimeError → error captured in summary, no raise
"""

import os
import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("SEC_USER_AGENT", "test")
os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

from backend.app.services.graph_centrality import CentralityScores

# ── Helpers ─────────────────────────────────────────────────────────────────


def _theme(name="Neo-clouds", theme_id="00000000-0000-0000-0000-000000000001"):
    t = MagicMock()
    t.id = theme_id
    t.name = name
    return t


def _theme_graph(too_dense=False, nodes=None, edges=None):
    """Minimal ThemeGraph mock — ThemeGraph is a dataclass, so we use a
    real-ish object that carries the right attributes."""
    tg = MagicMock()
    tg.too_dense = too_dense
    tg.nodes = nodes or []
    tg.edges = edges or []
    return tg


def _db():
    db = MagicMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


# Map two scored tickers for the normal-path test.
_SCORES = {
    "AAPL": CentralityScores(
        ticker="AAPL", betweenness=0.8, eigenvector=0.9, degree=5,
        is_hub=True, is_broker=False,
    ),
    "MSFT": CentralityScores(
        ticker="MSFT", betweenness=0.4, eigenvector=0.5, degree=3,
        is_hub=False, is_broker=True,
    ),
}


class RefreshThemeCentralityTests(unittest.IsolatedAsyncioTestCase):
    """Unit-level tests — patch build_theme_graph + _persist_signal_set so no
    DB, no networkx, no FMP calls are needed."""

    # ── build returns None ──────────────────────────────────────────────────

    async def test_build_none_skips_persist(self):
        theme = _theme()
        db = _db()

        with patch(
            "backend.app.services.signal_scheduler.build_theme_graph",
            new=AsyncMock(return_value=None),
        ), patch(
            "backend.app.services.signal_scheduler._persist_signal_set",
            new=AsyncMock(),
        ) as mock_persist:
            from backend.app.services.signal_scheduler import refresh_theme_centrality
            summary = await refresh_theme_centrality(theme=theme, db=db)

        mock_persist.assert_not_awaited()
        db.commit.assert_not_awaited()
        self.assertEqual(summary["tickers_scored"], 0)
        self.assertEqual(summary["persisted"], 0)
        self.assertIn("skipped", summary)
        self.assertIsNotNone(summary["skipped"])

    # ── too_dense ───────────────────────────────────────────────────────────

    async def test_too_dense_skips_persist(self):
        theme = _theme()
        db = _db()

        with patch(
            "backend.app.services.signal_scheduler.build_theme_graph",
            new=AsyncMock(return_value=_theme_graph(too_dense=True)),
        ), patch(
            "backend.app.services.signal_scheduler._persist_signal_set",
            new=AsyncMock(),
        ) as mock_persist:
            from backend.app.services.signal_scheduler import refresh_theme_centrality
            summary = await refresh_theme_centrality(theme=theme, db=db)

        mock_persist.assert_not_awaited()
        db.commit.assert_not_awaited()
        self.assertEqual(summary["persisted"], 0)
        self.assertIn("skipped", summary)
        self.assertIsNotNone(summary["skipped"])

    # ── compute returns empty (below MIN_EDGES density gate) ────────────────

    async def test_empty_scores_skips_persist(self):
        theme = _theme()
        db = _db()

        with patch(
            "backend.app.services.signal_scheduler.build_theme_graph",
            new=AsyncMock(return_value=_theme_graph()),  # valid, not dense
        ), patch(
            "backend.app.services.signal_scheduler.compute_theme_centrality",
            return_value={},  # sync function — plain MagicMock return
        ), patch(
            "backend.app.services.signal_scheduler._persist_signal_set",
            new=AsyncMock(),
        ) as mock_persist:
            from backend.app.services.signal_scheduler import refresh_theme_centrality
            summary = await refresh_theme_centrality(theme=theme, db=db)

        mock_persist.assert_not_awaited()
        db.commit.assert_not_awaited()
        self.assertEqual(summary["tickers_scored"], 0)
        self.assertIn("skipped", summary)

    # ── normal path ─────────────────────────────────────────────────────────

    async def test_normal_path_persists_all_tickers(self):
        theme = _theme()
        db = _db()

        with patch(
            "backend.app.services.signal_scheduler.build_theme_graph",
            new=AsyncMock(return_value=_theme_graph()),
        ), patch(
            "backend.app.services.signal_scheduler.compute_theme_centrality",
            return_value=_SCORES,
        ), patch(
            "backend.app.services.signal_scheduler._persist_signal_set",
            new=AsyncMock(),
        ) as mock_persist:
            from backend.app.services.signal_scheduler import refresh_theme_centrality
            summary = await refresh_theme_centrality(theme=theme, db=db)

        # One call per scored ticker.
        self.assertEqual(mock_persist.await_count, 2)
        db.commit.assert_awaited_once()

        self.assertEqual(summary["tickers_scored"], 2)
        self.assertEqual(summary["persisted"], 2)
        self.assertIsNone(summary["skipped"])
        self.assertIsNone(summary["error"])

    async def test_normal_path_payload_shape(self):
        """_persist_signal_set must receive {"centrality": {..., "modifier": <int>}}
        and all calls must share the same computed_at datetime."""
        theme = _theme()
        db = _db()

        with patch(
            "backend.app.services.signal_scheduler.build_theme_graph",
            new=AsyncMock(return_value=_theme_graph()),
        ), patch(
            "backend.app.services.signal_scheduler.compute_theme_centrality",
            return_value=_SCORES,
        ), patch(
            "backend.app.services.signal_scheduler._persist_signal_set",
            new=AsyncMock(),
        ) as mock_persist:
            from backend.app.services.signal_scheduler import refresh_theme_centrality
            await refresh_theme_centrality(theme=theme, db=db)

        calls = mock_persist.await_args_list
        self.assertEqual(len(calls), 2)

        # All calls share the same computed_at instance.
        computed_ats = [c.kwargs["computed_at"] for c in calls]
        self.assertEqual(computed_ats[0], computed_ats[1])
        self.assertIsInstance(computed_ats[0], datetime)
        self.assertEqual(computed_ats[0].tzinfo, timezone.utc)

        # Each results payload has the centrality key with a modifier field.
        for c in calls:
            results = c.kwargs["results"]
            self.assertIn("centrality", results)
            payload = results["centrality"]
            self.assertIn("modifier", payload)
            self.assertIsInstance(payload["modifier"], int)

        # db and theme_id wired correctly.
        for c in calls:
            self.assertIs(c.kwargs["db"], db)
            self.assertEqual(c.kwargs["theme_id"], theme.id)

    # ── fault isolation ─────────────────────────────────────────────────────

    async def test_build_exception_captured_no_raise(self):
        theme = _theme()
        db = _db()

        with patch(
            "backend.app.services.signal_scheduler.build_theme_graph",
            new=AsyncMock(side_effect=RuntimeError("graph DB down")),
        ), patch(
            "backend.app.services.signal_scheduler._persist_signal_set",
            new=AsyncMock(),
        ) as mock_persist:
            from backend.app.services.signal_scheduler import refresh_theme_centrality
            # Must NOT raise.
            summary = await refresh_theme_centrality(theme=theme, db=db)

        mock_persist.assert_not_awaited()
        db.commit.assert_not_awaited()
        db.rollback.assert_awaited_once()
        self.assertIsNotNone(summary["error"])
        self.assertEqual(summary["persisted"], 0)

    async def test_mid_persist_exception_rolls_back(self):
        """_persist_signal_set raises on the second ticker → rollback awaited,
        commit NOT called, error captured, no raise."""
        theme = _theme()
        db = _db()

        with patch(
            "backend.app.services.signal_scheduler.build_theme_graph",
            new=AsyncMock(return_value=_theme_graph()),
        ), patch(
            "backend.app.services.signal_scheduler.compute_theme_centrality",
            return_value=_SCORES,  # 2 tickers
        ), patch(
            "backend.app.services.signal_scheduler._persist_signal_set",
            new=AsyncMock(side_effect=[None, RuntimeError("boom")]),
        ) as mock_persist:
            from backend.app.services.signal_scheduler import refresh_theme_centrality
            # Must NOT raise.
            summary = await refresh_theme_centrality(theme=theme, db=db)

        # Two _persist calls were attempted (first succeeded, second raised).
        self.assertEqual(mock_persist.await_count, 2)
        db.rollback.assert_awaited_once()
        db.commit.assert_not_awaited()
        self.assertIsNotNone(summary["error"])


if __name__ == "__main__":
    unittest.main()

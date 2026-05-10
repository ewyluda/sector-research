"""Pins the bounded-eviction behaviour of FanoutService._statuses.

The dict was unbounded across the process lifetime. We cap it and evict the
oldest entry on overflow. These tests exercise the eviction directly via
`_record()` so the assertions don't depend on the actual ingest/extract/
resolve work that `start_*()` schedules under `asyncio.create_task`.
"""
import os
import unittest

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("SEC_USER_AGENT", "test")
os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

from backend.app.services.fanout import (
    FanoutScope,
    FanoutService,
    FanoutStatus,
)


def _make_service(max_statuses: int) -> FanoutService:
    # edgar/fmp aren't touched by `_record()`; pass `None` cast to satisfy
    # the constructor signature (the typing.cast isn't needed at runtime).
    return FanoutService(edgar=None, fmp=None, max_statuses=max_statuses)  # type: ignore[arg-type]


def _stub_status(fanout_id: str) -> FanoutStatus:
    return FanoutStatus(
        fanout_id=fanout_id,
        status="completed",
        scope=FanoutScope(kind="ticker", ticker="X"),
        total_tickers=1,
        completed_tickers=1,
    )


class FanoutEvictionTests(unittest.TestCase):
    def test_under_cap_keeps_all(self):
        svc = _make_service(max_statuses=3)
        for i in range(3):
            svc._record(_stub_status(f"fo_{i}"))
        for i in range(3):
            self.assertIsNotNone(svc.get(f"fo_{i}"))
        self.assertEqual(len(svc._statuses), 3)

    def test_overflow_evicts_oldest(self):
        svc = _make_service(max_statuses=3)
        for i in range(3):
            svc._record(_stub_status(f"fo_{i}"))
        # 4th insertion evicts the first.
        svc._record(_stub_status("fo_3"))
        self.assertIsNone(svc.get("fo_0"))
        for i in (1, 2, 3):
            self.assertIsNotNone(svc.get(f"fo_{i}"))
        self.assertEqual(len(svc._statuses), 3)

    def test_repeated_overflow_keeps_only_last_n(self):
        svc = _make_service(max_statuses=2)
        for i in range(5):
            svc._record(_stub_status(f"fo_{i}"))
        self.assertEqual(len(svc._statuses), 2)
        for i in (0, 1, 2):
            self.assertIsNone(svc.get(f"fo_{i}"))
        for i in (3, 4):
            self.assertIsNotNone(svc.get(f"fo_{i}"))

    def test_default_cap_is_generous(self):
        # Sanity check on the production default — a personal tool should
        # not be evicting anything in normal use.
        from backend.app.services.fanout import DEFAULT_MAX_STATUSES
        self.assertGreaterEqual(DEFAULT_MAX_STATUSES, 64)


if __name__ == "__main__":
    unittest.main()

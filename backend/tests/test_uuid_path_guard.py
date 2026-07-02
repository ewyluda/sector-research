"""models/uuid_path guards: malformed (non-UUID) resource ids must 404 at
the param boundary, never 500 at the asyncpg UUID cast (pre-existing bug
class observed during the PR #63 smoke; guards applied across pipeline,
status, journal, and events routers in PR #64)."""
import os
import unittest
import uuid

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("SEC_USER_AGENT", "test")
os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

from fastapi import HTTPException

from backend.app.models.uuid_path import (
    EventIdPath,
    OutcomeIdOr404,
    RunIdPath,
    TradeIdPath,
)

_GUARDS = (RunIdPath, TradeIdPath, EventIdPath, OutcomeIdOr404)


class UuidGuardTests(unittest.TestCase):
    def test_valid_uuid_passes_through_unchanged(self):
        rid = str(uuid.uuid4())
        for guard in _GUARDS:
            self.assertEqual(guard(rid), rid, guard.__name__)

    def test_malformed_id_raises_404(self):
        for guard in _GUARDS:
            for bad in ("smoke-nonexistent", "not-a-uuid", "", "12345"):
                with self.assertRaises(HTTPException) as ctx:
                    guard(bad)
                self.assertEqual(ctx.exception.status_code, 404, guard.__name__)

    def test_details_match_each_resources_existing_404_copy(self):
        expected = {
            RunIdPath: "Run not found",
            TradeIdPath: "trade not found",
            EventIdPath: "Event not found",
            OutcomeIdOr404: "outcome not found",
        }
        for guard, detail in expected.items():
            with self.assertRaises(HTTPException) as ctx:
                guard("bad")
            self.assertEqual(ctx.exception.detail, detail)


class RoutesGuardedTests(unittest.TestCase):
    """Every UUID-keyed path param must depend on its guard — a new route
    added without one re-opens the 500."""

    def _assert_guarded(self, fn, param_name, guard):
        import inspect
        from fastapi.params import Depends as DependsParam

        sig = inspect.signature(fn)
        param = sig.parameters.get(param_name)
        self.assertIsNotNone(param, fn.__name__)
        self.assertIsInstance(param.default, DependsParam, fn.__name__)
        self.assertIs(param.default.dependency, guard, fn.__name__)

    def test_pipeline_run_id_routes(self):
        from backend.app.api import pipeline as mod

        for fn in (mod.get_run, mod.advance_run, mod.abandon_run,
                   mod.stream_run, mod.get_report):
            self._assert_guarded(fn, "run_id", RunIdPath)

    def test_status_run_id_routes(self):
        from backend.app.api import status as mod

        for fn in (mod.archive_run, mod.unarchive_run,
                   mod.list_kill_criterion_states,
                   mod.upsert_kill_criterion_state_endpoint):
            self._assert_guarded(fn, "run_id", RunIdPath)

    def test_journal_trade_id_routes(self):
        from backend.app.api import journal as mod

        for fn in (mod.patch_trade, mod.delete_trade):
            self._assert_guarded(fn, "trade_id", TradeIdPath)

    def test_events_event_id_route(self):
        from backend.app.api import events as mod

        self._assert_guarded(mod.dismiss_event, "event_id", EventIdPath)


if __name__ == "__main__":
    unittest.main()

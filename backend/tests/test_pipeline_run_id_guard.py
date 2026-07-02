"""RunIdPath guard on api/pipeline.py `{run_id}` routes: a malformed
(non-UUID) run_id must 404 at the route boundary, never 500 at the asyncpg
UUID-cast (pre-existing bug observed during the PR #63 smoke)."""
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

from backend.app.api.pipeline import RunIdPath


class RunIdPathTests(unittest.TestCase):
    def test_valid_uuid_passes_through_unchanged(self):
        rid = str(uuid.uuid4())
        self.assertEqual(RunIdPath(rid), rid)

    def test_malformed_id_raises_404(self):
        for bad in ("smoke-nonexistent", "not-a-uuid", "", "12345"):
            with self.assertRaises(HTTPException) as ctx:
                RunIdPath(bad)
            self.assertEqual(ctx.exception.status_code, 404)


class RunIdRoutesGuardedTests(unittest.TestCase):
    def test_every_run_id_route_uses_the_guard(self):
        """All five `{run_id}` handlers must depend on RunIdPath — a new
        route added without it re-opens the 500."""
        from fastapi.params import Depends as DependsParam
        import inspect

        from backend.app.api import pipeline as mod

        handlers = [mod.get_run, mod.advance_run, mod.abandon_run,
                    mod.stream_run, mod.get_report]
        for fn in handlers:
            sig = inspect.signature(fn)
            param = sig.parameters.get("run_id")
            self.assertIsNotNone(param, fn.__name__)
            default = param.default
            self.assertIsInstance(default, DependsParam, fn.__name__)
            self.assertIs(default.dependency, mod.RunIdPath, fn.__name__)


if __name__ == "__main__":
    unittest.main()

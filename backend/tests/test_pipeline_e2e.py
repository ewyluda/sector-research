"""End to end: a research run through every phase against a real, migrated
Postgres, with recorded FMP responses and a fake LLM.

Pins what unit tests can't: phases chain and persist, a risk loop-back re-runs
only the named category and reuses the transcript analysis, the deep dive
warms the cache before fanning out, every LLM call lands in llm_calls with the
run's scope, and the report API serves the finished run.

Needs its own process so DATABASE_URL is set before the app modules import:

    PIPELINE_E2E=1 DATABASE_URL=postgresql+asyncpg://…/sector_research_ci \
      python -m unittest backend.tests.test_pipeline_e2e

Re-record the fixture with backend/scripts/record_pipeline_fixture.py.
"""
import asyncio
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

ENABLED = os.environ.get("PIPELINE_E2E") == "1"


@unittest.skipUnless(ENABLED, "set PIPELINE_E2E=1 and point DATABASE_URL at a migrated Postgres")
class PipelineEndToEndTests(unittest.IsolatedAsyncioTestCase):
    async def test_a_run_completes_every_phase_with_one_loop_back(self):
        import httpx
        from sqlalchemy import select

        from backend.app.db import async_session
        from backend.app.graph import llm
        from backend.app.graph.prompts import DEEP_DIVE_CATEGORIES
        from backend.app.graph.state import ResearchState
        from backend.app.main import app
        from backend.app.models.llm_call import LLMCall
        from backend.app.models.research_run import ResearchRun
        from backend.app.models.theme import Theme
        from backend.app.services import llm_usage
        from backend.app.services.pipeline import PipelineService
        from backend.tests.pipeline_harness import FIXTURES, FakeAnthropic, ReplayFMP

        fmp = ReplayFMP(FIXTURES / "fmp_VRT.json")
        profile, _ = await fmp.get_company_profile("VRT")
        price = float((profile[0] if isinstance(profile, list) else profile)["price"])
        fake = FakeAnthropic(price=price, risk_loops=1)

        live_calls: list[str] = []

        async def no_network(_transport, request, *_args, **_kwargs):
            live_calls.append(f"{request.method} {request.url.host}{request.url.path}")
            raise AssertionError("the pipeline made a live HTTP call — inject the client instead")

        with patch.object(llm, "get_client", return_value=fake), \
                patch.object(llm, "usage_sink", llm_usage.record), \
                patch.object(httpx.AsyncHTTPTransport, "handle_async_request", no_network):
            svc = PipelineService(fmp=fmp)
            async with async_session() as db:
                theme = Theme(name="E2E theme", description="End-to-end test theme.")
                db.add(theme)
                await db.commit()
                run = await svc.create_run("VRT", theme.id, db)
            await svc._run_phase(run.id, ResearchState.from_dict(run.state))
            pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
            await asyncio.gather(*pending, return_exceptions=True)

        async with async_session() as db:
            row = (await db.execute(select(ResearchRun).where(ResearchRun.id == run.id))).scalar_one()
            calls = (await db.execute(select(LLMCall).where(LLMCall.run_id == run.id))).scalars().all()

        # Offline: callers that swallow errors would hide the guard's exception.
        self.assertEqual(live_calls, [])

        # Every phase ran and persisted; one loop-back happened and then the run finished.
        self.assertEqual(row.status, "completed", row.state.get("phase_outputs", {}).get("risk"))
        self.assertEqual(row.loop_count, 1)
        outputs = row.state["phase_outputs"]
        for key in ["quick_screen", "thesis", "risk", *DEEP_DIVE_CATEGORIES]:
            self.assertIn(key, outputs)
            self.assertNotEqual(outputs[key].get("__type__"), "PhaseError", key)
            self.assertNotEqual(outputs[key].get("__type__"), "CategoryError", key)
        self.assertEqual(row.state["conviction_score"], 58)
        self.assertEqual(outputs["risk"]["rr_source"], "thesis_targets")  # R/R computed from price + targets

        # The loop re-ran only the named category, and transcript passes ran once.
        deep_dive = [r for r in fake.requests
                     if r.get("output_config", {}).get("format", {}).get("schema", {}).get("title") == "DeepDiveCategoryOutput"]
        self.assertEqual(len(deep_dive), len(DEEP_DIVE_CATEGORIES) + 1)
        text_calls = [r for r in fake.requests if "format" not in r.get("output_config", {})]
        self.assertLessEqual(len(text_calls), 6)
        # Warm-then-fan-out: exactly one streamed call per deep-dive batch, and
        # every category shares one cached prefix block.
        self.assertEqual(sum(1 for r in deep_dive if r.get("_streamed")), 2)
        prefixes = {r["messages"][0]["content"][0]["text"] for r in deep_dive}
        self.assertEqual(len(prefixes), 1)

        # Telemetry: every call recorded under this run with its phase.
        self.assertEqual(len(calls), len(fake.requests))
        self.assertEqual({c.phase for c in calls} >= {"quick_screen", "deep_dive", "thesis_construction",
                                                       "risk_stress_test"}, True)
        self.assertTrue(all(c.cost_usd is not None for c in calls))

        # The report API serves the finished run.
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
            report = (await client.get(f"/api/runs/{run.id}/report")).json()
            usage = (await client.get(f"/api/runs/{run.id}/usage")).json()
        self.assertEqual(report["status"], "completed")
        self.assertEqual(report["phases"]["thesis"]["structured"]["stance"], "long")
        self.assertEqual(usage["calls"], len(calls))
        self.assertEqual(fmp.misses and [m for m in fmp.misses if m.startswith("get_income")], [])


if __name__ == "__main__":
    unittest.main()

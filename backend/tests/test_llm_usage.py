"""LLM telemetry: per-call cost, run attribution through asyncio tasks, the
usage sink, and the per-run rollup behind GET /api/runs/{id}/usage."""
import asyncio
import os
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

from backend.app.graph import llm  # noqa: E402
from backend.app.services import llm_usage  # noqa: E402


class CostTests(unittest.TestCase):
    def test_opus_cost_prices_each_token_class(self):
        # 1M uncached in ($4) + 1M write ($5) + 1M read ($0.20) + 1M out ($20)
        cost = llm_usage.cost_usd("claude-opus-5-5", input_tokens=1_000_000, output_tokens=1_000_000,
                                  cache_read_tokens=1_000_000, cache_write_tokens=1_000_000)
        self.assertAlmostEqual(cost, 29.20)

    def test_unknown_model_is_unpriced_not_zero(self):
        self.assertIsNone(llm_usage.cost_usd("claude-unknown", input_tokens=1, output_tokens=1,
                                             cache_read_tokens=0, cache_write_tokens=0))


class ScopeTests(unittest.IsolatedAsyncioTestCase):
    async def test_parallel_calls_inherit_the_run_scope(self):
        async def runner():
            llm_usage.set_scope("research", "run-1", "deep_dive")
            return await asyncio.gather(*(_read() for _ in range(3)))  # gather wraps each in a task

        async def _read():
            return llm_usage.current_scope()

        scopes = await asyncio.create_task(runner())
        self.assertEqual(scopes, [{"run_kind": "research", "run_id": "run-1", "phase": "deep_dive"}] * 3)
        self.assertIsNone(llm_usage.current_scope())  # the runner's task didn't leak its scope

    async def test_set_phase_keeps_the_run(self):
        async def runner():
            llm_usage.set_scope("workspace", "w-1", "research")
            llm_usage.set_phase("challenge")
            return llm_usage.current_scope()

        self.assertEqual(await asyncio.create_task(runner()),
                         {"run_kind": "workspace", "run_id": "w-1", "phase": "challenge"})


class SinkTests(unittest.IsolatedAsyncioTestCase):
    async def test_every_call_reaches_the_sink_with_tokens_and_prompt_version(self):
        usage = SimpleNamespace(input_tokens=100, output_tokens=50,
                                cache_read_input_tokens=2000, cache_creation_input_tokens=0)
        message = SimpleNamespace(stop_reason="end_turn", usage=usage,
                                  content=[SimpleNamespace(type="text", text="ok")])
        client = MagicMock()
        client.messages.create = AsyncMock(return_value=message)
        sink = AsyncMock()
        with patch.object(llm, "get_client", return_value=client), patch.object(llm, "usage_sink", sink):
            await llm.complete("system prompt", "u", model="claude-opus-5-5")
        call = sink.call_args.args[0]
        self.assertEqual((call.input_tokens, call.output_tokens, call.cache_read_tokens), (100, 50, 2000))
        self.assertEqual(call.prompt_version, llm_usage.prompt_version("system prompt"))
        self.assertAlmostEqual(call.cost_usd, (100 * 4 + 2000 * 0.20 + 50 * 20) / 1e6)


def _row(phase, cost, *, inp=100, read=0, write=0, out=10, t=0, latency=1000):
    return SimpleNamespace(phase=phase, cost_usd=cost, input_tokens=inp, output_tokens=out,
                           cache_read_tokens=read, cache_write_tokens=write, latency_ms=latency,
                           created_at=datetime(2026, 9, 28, tzinfo=timezone.utc) + timedelta(seconds=t))


class SummarizeTests(unittest.TestCase):
    def test_rollup_totals_phases_and_span(self):
        rows = [_row("quick_screen", 0.01, t=10, latency=10_000),
                _row("deep_dive", 0.50, inp=100, read=900, t=60),
                _row("deep_dive", None, t=70)]
        out = llm_usage.summarize(rows)
        self.assertEqual(out["calls"], 3)
        self.assertAlmostEqual(out["cost_usd"], 0.51)
        self.assertEqual(out["unpriced_calls"], 1)
        self.assertEqual(out["wall_clock_s"], 70.0)  # first call started at t=0
        dd = next(p for p in out["by_phase"] if p["phase"] == "deep_dive")
        self.assertEqual(dd["calls"], 2)
        self.assertAlmostEqual(dd["cache_hit_rate"], 900 / 1100, places=3)

    def test_no_calls(self):
        self.assertEqual(llm_usage.summarize([])["calls"], 0)


if __name__ == "__main__":
    unittest.main()

"""Harness for running the research pipeline end to end without live services.

- ReplayFMP serves recorded FMP responses (or records them from a live client).
- FakeAnthropic stands in for the Anthropic client: every structured call gets
  canned, schema-valid JSON chosen by the output schema's title; text calls
  (transcript passes) get an empty JSON array.

Used by test_pipeline_e2e.py and scripts/record_pipeline_fixture.py. No
`test_` prefix, so the unittest enumeration glob skips it.
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from types import SimpleNamespace

from backend.app.clients.fmp import FMPClientError
from backend.app.models.citation import Citation
from backend.app.models.phase_schemas import QUICK_SCREEN_DIMENSIONS

FIXTURES = Path(__file__).parent / "fixtures"
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
# Recorded transcripts are cut to this length: enough to exercise the passes,
# small enough to commit.
TRANSCRIPT_CHARS = 6000


def _key(method: str, args: tuple, kwargs: dict) -> str:
    """Call signature with ISO dates masked, so a 1-year price window recorded
    today still matches next month."""
    raw = json.dumps([args, kwargs], sort_keys=True, default=str)
    return f"{method}:{_DATE.sub('<date>', raw)}"


def _trim(method: str, data):
    if method == "get_earnings_transcript" and isinstance(data, list):
        return [{**row, "content": (row.get("content") or "")[:TRANSCRIPT_CHARS]} for row in data]
    return data


class ReplayFMP:
    """Stands in for FMPClient. With `record_from`, calls go to that live client
    and responses are kept for `save()`; otherwise they come from the file,
    and an unrecorded call raises FMPClientError — the same failure a live
    endpoint outage produces, so tier-2 calls degrade exactly as in production."""

    def __init__(self, path: Path, record_from=None) -> None:
        self._path = path
        self._live = record_from
        self._store: dict = {} if record_from else json.loads(path.read_text())
        self.misses: list[str] = []

    def save(self) -> None:
        text = json.dumps(self._store, indent=1, sort_keys=True, default=str)
        if "apikey" in text.lower():
            raise RuntimeError("refusing to write a fixture containing an API key")
        self._path.write_text(text)

    async def close(self) -> None:
        if self._live is not None:
            await self._live.close()

    def __getattr__(self, method: str):
        async def call(*args, **kwargs):
            key = _key(method, args, kwargs)
            if self._live is not None:
                data, citation = await getattr(self._live, method)(*args, **kwargs)
                self._store[key] = _trim(method, data)
                return self._store[key], citation
            if key not in self._store:
                self.misses.append(key)
                raise FMPClientError(f"no recording for {key}")
            citation = Citation(value="", metric=method, source_name=f"FMP {method} (recorded)",
                                source_url=f"https://financialmodelingprep.com/stable/{method}", tier=1)
            return copy.deepcopy(self._store[key]), citation
        return call


# ── Fake LLM ──────────────────────────────────────────────────────────────────

def _findings(n: int) -> list[dict]:
    return [{"finding": f"Finding {i}", "evidence": "[Source: FMP /income-statement]"} for i in range(n)]


def _points(n: int, side: str) -> list[dict]:
    return [{"title": f"{side} point {i}", "evidence": "[Source: FMP]"} for i in range(n)]


CANNED: dict[str, dict] = {
    "QuickScreenOutput": {
        "overall_score": 0, "recommendation": "PASS",  # both recomputed in code from the dimensions
        "dimensions": [{"name": d, "score": 14, "rationale": "Adequate."} for d in QUICK_SCREEN_DIMENSIONS],
        "thesis": "Fixture thesis.", "key_risk": "Fixture risk.",
    },
    "DeepDiveCategoryOutput": {
        "score": 62, "score_rationale": "Mixed.", "key_findings": _findings(3),
        "analysis": "Fixture analysis [Source: FMP /income-statement].", "data_gaps": [],
        "questions": [{"question_text": "What is backlog conversion?", "priority": 2, "auto_answerable": False}],
    },
    "ThesisLLMOutput": {
        "core_thesis": "Fixture core thesis.", "bull_case": _points(2, "bull"), "bear_case": _points(2, "bear"),
        "variant_perception": "Fixture variant view.",
        "catalysts": [{"timeframe": "Q4 2026", "description": f"Catalyst {i}", "type": "earnings"} for i in range(3)],
        "conviction_score": 58, "conviction_rationale": "Fixture rationale.",
        "stance": "long", "time_horizon": "12 months",
        "valuation_basis": "Fixture: 20x forward EBITDA.",
        "kill_criteria": [{"condition": "Margin falls", "threshold": "GM < 30% two quarters", "monitoring_source": "10-Q"}],
        "pre_mortem": {"framing": "Imagine it's 18 months from now and this thesis is dead. What killed it?",
                       "failure_modes": [{"mode": f"Mode {i}", "leading_indicator": "Signal", "probability": "Low"}
                                         for i in range(3)]},
        # Targets are relative to the recorded price at request time; see FakeAnthropic.
        "price_targets": {"bear": 1.0, "base": 1.0, "bull": 1.0},
    },
    "PositionMonitorOutput": {
        "entry_price_low": "$230", "entry_price_high": "$245", "entry_rationale": "Fixture.",
        "position_size_pct": 2.0, "sizing_rationale": "Fixture.", "add_triggers": ["Margin beat"],
        "stop_loss_level": "$200", "stop_loss_rationale": "Fixture.", "invalidation_conditions": ["Guide cut"],
        "monitoring": [{"metric": "Gross margin", "cadence": "quarterly", "threshold": "< 30%"},
                       {"metric": "Backlog", "cadence": "quarterly", "threshold": "down QoQ"}],
        "exit_conditions": ["Target reached"], "time_horizon": "12 months",
    },
    "RiskStressTestOutput": {
        "risks": [{"risk": f"Risk {i}", "category": "Financial Health", "probability": "Medium",
                   "impact": "Moderate", "mitigation": "Monitor."} for i in range(3)],
        "rr_ratio": 1.5, "rr_verdict": "Thin.", "loop_required": False, "loop_categories": [], "loop_reason": "",
    },
}


class FakeAnthropic:
    """Minimal async Anthropic client. Records every request in `requests`.

    `risk_loops` makes the first N risk stress tests ask to re-run Financial
    Health, exercising the loop-back path. `price` scales the thesis targets
    (bear -30%, base +15%, bull +50% → reward/risk 0.5, below the 2.0 loop
    threshold, so a requested loop is honoured)."""

    def __init__(self, *, price: float, risk_loops: int = 0, fail_once: set[str] | None = None) -> None:
        self.messages = self
        self.requests: list[dict] = []
        self._price = price
        self._risk_loops = risk_loops
        # Schema titles whose first call fails, like an API error mid-run.
        self._fail_once = set(fail_once or ())

    def _body(self, request: dict) -> str:
        fmt = (request.get("output_config") or {}).get("format")
        if fmt is None:
            return "[]"  # transcript passes: valid, empty JSON
        title = fmt["schema"].get("title")
        body = copy.deepcopy(CANNED[title])
        if title == "ThesisLLMOutput":
            p = self._price
            body["price_targets"] = {"bear": round(p * 0.7, 2), "base": round(p * 1.15, 2), "bull": round(p * 1.5, 2)}
        if title == "RiskStressTestOutput" and self._risk_loops > 0:
            self._risk_loops -= 1
            body.update(loop_required=True, loop_categories=["Financial Health"], loop_reason="Leverage unclear.")
        return json.dumps(body)

    def _message(self, request: dict):
        title = ((request.get("output_config") or {}).get("format") or {}).get("schema", {}).get("title")
        if title in self._fail_once:
            self._fail_once.discard(title)
            raise RuntimeError("Your credit balance is too low to access the Anthropic API.")
        self.requests.append(request)
        usage = SimpleNamespace(input_tokens=1000, output_tokens=500,
                                cache_read_input_tokens=0, cache_creation_input_tokens=0)
        return SimpleNamespace(stop_reason="end_turn", usage=usage,
                               content=[SimpleNamespace(type="text", text=self._body(request))])

    async def create(self, **request):
        return self._message(request)

    def stream(self, **request):
        message = self._message({**request, "_streamed": True})
        return _FakeStream(message)


class _FakeStream:
    def __init__(self, message) -> None:
        self._message = message

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def __aiter__(self):
        async def events():
            yield SimpleNamespace(type="message_start")
        return events()

    async def get_final_message(self):
        return self._message

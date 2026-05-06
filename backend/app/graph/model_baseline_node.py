"""Sonnet pass that generates a baseline ForecastDrivers payload from deep-dive context."""
from __future__ import annotations
import asyncio
from pydantic import BaseModel

from backend.app.graph import llm


class DriverProposal(BaseModel):
    value: float | None = None
    reason: str = ""
    source_citation_id: str | None = None


class BaselineDriversResponse(BaseModel):
    drivers: dict[str, dict[str, DriverProposal]]   # {period_label: {driver_key: proposal}}


SYSTEM_PROMPT = """You are building a baseline financial forecast for a 3-statement model. \
Use the deep-dive findings, analyst consensus, and historical trends to produce structured driver \
assumptions for each forecast period. For each driver, give a numeric value, a one-line reason, and \
optionally a source_citation_id pointing back to a deep-dive finding ID, an analyst estimate label, \
or a historical-trend note. Anchor near consensus estimates unless the deep-dive findings explicitly \
contradict them — in which case explain why in `reason`. Use percentages as decimals (10% = 0.10). \
Days drivers (DSO/DIO/DPO) in days. Dollar drivers in same units as revenue. \
Output JSON ONLY — no preamble. Schema: {"drivers": {<period_label>: {<driver_key>: {"value": <num|null>, "reason": <str>, "source_citation_id": <str|null>}}}}"""


async def generate_baseline_drivers(
    *,
    ticker: str,
    historicals_payload: str,
    deep_dive_summary: str,
    consensus_estimates: str,
    forecast_period_labels: list[str],
) -> BaselineDriversResponse:
    user = (
        f"Ticker: {ticker}\n\n"
        f"Forecast periods (in order): {', '.join(forecast_period_labels)}\n\n"
        f"=== Historical financials (8 quarters) ===\n{historicals_payload}\n\n"
        f"=== Analyst consensus estimates ===\n{consensus_estimates}\n\n"
        f"=== Deep-dive summary (verdict, scores, key findings per category) ===\n{deep_dive_summary}\n\n"
        f"Produce the BaselineDriversResponse JSON now."
    )
    raw = await llm.complete(
        system=SYSTEM_PROMPT,
        user=user,
        assistant_prefill='{"drivers":',
    )
    return BaselineDriversResponse.model_validate_json(raw)

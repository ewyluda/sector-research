# backend/app/services/model_baseline.py
"""Orchestrate AI baseline seeding into a ModelState."""
from __future__ import annotations
from datetime import datetime
from typing import Any

from backend.app.graph.model_baseline_node import generate_baseline_drivers, BaselineDriversResponse
from backend.app.models.model_state import (
    ModelState, ModelCell, Period, ModelAssumptions,
    DRIVER_KEYS, LINE_ITEMS_PNL, LINE_ITEMS_BS, LINE_ITEMS_CF,
)
from backend.app.services.model_balancing import recompute


async def _load_seeding_context(ticker: str) -> dict[str, Any]:
    """Load latest completed research_run state for ticker."""
    from backend.app.db import async_session
    from backend.app.models.research_run import ResearchRun
    from sqlalchemy import select
    async with async_session() as db:
        stmt = (select(ResearchRun)
                .where(ResearchRun.ticker == ticker, ResearchRun.status == "completed")
                .order_by(ResearchRun.created_at.desc()).limit(1))
        run = (await db.execute(stmt)).scalar_one_or_none()
        if run is None:
            raise ValueError(f"No completed research_run found for ticker {ticker}")
        return run.state or {}


async def _get_risk_free_rate() -> float:
    """Latest 10Y treasury from FRED. Returns 0.045 fallback on any error."""
    try:
        from backend.app.clients.fred import FREDClient
        client = FREDClient()
        series, _citation = await client.get_series("DGS10")
        if not series or not series[-1].get("value"):
            return 0.045
        return float(series[-1]["value"]) / 100.0
    except Exception:
        return 0.045


def _build_periods() -> list[Period]:
    """8 historical Q + 8 forecast Q + 5 forecast Y."""
    today = datetime.utcnow()
    year, q = today.year, (today.month - 1) // 3 + 1
    periods: list[Period] = []
    # 8 historical quarters
    for i in range(8, 0, -1):
        ny, nq = year, q - i
        while nq <= 0:
            ny -= 1
            nq += 4
        periods.append(Period(label=f"{ny}Q{nq}", kind="Q", is_historical=True, quarter_index=nq))
    # 8 forecast quarters
    for i in range(0, 8):
        ny, nq = year, q + i
        while nq > 4:
            ny += 1
            nq -= 4
        periods.append(Period(label=f"{ny}Q{nq}", kind="Q", is_historical=False, quarter_index=nq))
    # 5 forecast years (calendar years following the last forecast quarter)
    last_q = periods[-1]
    start_y = last_q.label.split("Q")[0]
    base = int(start_y) + 1
    for i in range(5):
        periods.append(Period(label=f"{base + i}Y", kind="Y", is_historical=False))
    return periods


def _seed_historicals(state: ModelState, ctx: dict[str, Any]) -> None:
    """Map curated_financials onto historical period cells."""
    cf = ctx.get("curated_financials") or {}
    for stmt_key, lines in [
        ("income_statements", LINE_ITEMS_PNL),
        ("balance_sheets",    LINE_ITEMS_BS),
        ("cash_flows",        LINE_ITEMS_CF),
    ]:
        target = {
            "income_statements": state.income_statement,
            "balance_sheets":    state.balance_sheet,
            "cash_flows":        state.cash_flow,
        }[stmt_key]
        for record in cf.get(stmt_key, []):
            period = record.get("period")
            if period is None:
                continue
            for line in lines:
                if line in record and record[line] is not None:
                    target.setdefault(line, {})[period] = ModelCell(
                        value=float(record[line]), source="historical",
                        last_edited_by="system",
                    )


def _apply_baseline_drivers(state: ModelState, response: BaselineDriversResponse) -> None:
    """Inject Sonnet-generated drivers into state.drivers, source='ai_baseline'."""
    for period_label, drvs in response.drivers.items():
        if period_label not in state.drivers:
            state.drivers[period_label] = {}
        for k, proposal in drvs.items():
            state.drivers[period_label][k] = ModelCell(
                value=proposal.value,
                source="ai_baseline",
                citation_id=proposal.source_citation_id,
                last_edited_at=datetime.utcnow().isoformat(),
                last_edited_by="ai_baseline",
                formula=proposal.reason or None,
            )


async def build_baseline_state(*, ticker: str, forecast_period_labels: list[str] | None = None) -> ModelState:
    ctx = await _load_seeding_context(ticker)
    periods = _build_periods()
    if forecast_period_labels is not None:
        periods = [p for p in periods if p.is_historical or p.label in forecast_period_labels]
    forecast = [p.label for p in periods if not p.is_historical]
    if forecast_period_labels is None:
        forecast_period_labels = forecast
    # Empty cells everywhere; will be filled by seed/recompute
    drivers = {p.label: {k: ModelCell(value=None, source="driver") for k in DRIVER_KEYS} for p in periods}
    income_statement = {li: {} for li in LINE_ITEMS_PNL}
    balance_sheet = {li: {} for li in LINE_ITEMS_BS}
    cash_flow = {li: {} for li in LINE_ITEMS_CF}
    rf = await _get_risk_free_rate()
    beta = float(ctx.get("curated_financials", {}).get("profile", {}).get("beta") or 1.0)
    state = ModelState(
        periods=periods, drivers=drivers,
        income_statement=income_statement, balance_sheet=balance_sheet, cash_flow=cash_flow,
        assumptions=ModelAssumptions(
            discount_rate=ModelCell(value=rf + beta * 0.055, source="driver",
                                    formula=f"= rf + β × ERP = {rf:.4f} + {beta:.2f} × 0.055"),
            terminal_method="exit_multiple",
            terminal_multiple=ModelCell(value=12.0, source="driver"),
            perpetuity_growth=ModelCell(value=0.025, source="driver"),
            tax_rate=ModelCell(value=0.21, source="driver"),
            plug_priority=["debt_paydown", "buyback", "dividend", "cash"],
        ),
    )
    _seed_historicals(state, ctx)

    # Build seed strings for the LLM
    historicals_str = (ctx.get("curated_financials") or {}).get("income_statements", [])
    deep_dive_summary = str(ctx.get("deep_dive_results") or "(no findings)")
    consensus = (ctx.get("curated_financials") or {}).get("estimates", "(no estimates)")
    response = await generate_baseline_drivers(
        ticker=ticker,
        historicals_payload=str(historicals_str),
        deep_dive_summary=deep_dive_summary,
        consensus_estimates=str(consensus),
        forecast_period_labels=forecast_period_labels,
    )
    _apply_baseline_drivers(state, response)

    state = recompute(state)
    return state

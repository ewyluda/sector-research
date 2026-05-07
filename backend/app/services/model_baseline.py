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
    """Map curated_financials onto historical period cells.

    CuratedFinancials stores quarterly series as flat arrays (newest-first)
    like quarterly_revenue, quarterly_gross_margin, etc. We map index-0 of
    each series to the most-recent historical period, index-1 to the second
    most-recent, etc.  Only revenue is strictly required for recompute() to
    work (so prior_rev is non-None); other metrics are best-effort.
    """
    cf = ctx.get("curated_financials") or {}
    hist = [p for p in state.periods if p.is_historical]
    # hist is oldest-first; quarterly arrays are newest-first
    hist_newest_first = list(reversed(hist))

    # Map of curated_financials key → (statement dict, line_item name)
    series_map: list[tuple[str, dict, str]] = [
        ("quarterly_revenue",          state.income_statement, "revenue"),
        ("quarterly_gross_margin",     state.income_statement, "gross_profit"),    # pct → will be recalculated; skip
        ("quarterly_net_margin",       state.income_statement, "net_income"),      # pct → skip
        ("quarterly_operating_margin", state.income_statement, "ebit"),            # pct → skip
        ("quarterly_free_cf",          state.cash_flow,        "free_cash_flow"),
        ("quarterly_operating_cf",     state.cash_flow,        "operating_cash_flow"),
        ("quarterly_capex",            state.cash_flow,        "capex"),
        ("quarterly_total_debt",       state.balance_sheet,    "total_debt"),
        ("quarterly_current_ratio",    state.balance_sheet,    "current_ratio"),   # ratio → skip
        ("quarterly_shareholders_equity", state.balance_sheet, "shareholders_equity"),
    ]
    # Only seed dollar-value series (not ratios/margins which are percentages)
    dollar_keys = {
        "quarterly_revenue", "quarterly_free_cf", "quarterly_operating_cf",
        "quarterly_capex", "quarterly_total_debt", "quarterly_shareholders_equity",
        "quarterly_cash", "quarterly_eps",
    }
    for cf_key, target, line_item in series_map:
        if cf_key not in dollar_keys:
            continue
        series = cf.get(cf_key, [])
        for i, record in enumerate(series):
            if i >= len(hist_newest_first):
                break
            period_label = hist_newest_first[i].label
            raw = record.get("value") if isinstance(record, dict) else record
            if raw is not None:
                try:
                    target.setdefault(line_item, {})[period_label] = ModelCell(
                        value=float(raw), source="historical", last_edited_by="system",
                    )
                except (TypeError, ValueError):
                    pass

    market_cap = cf.get("market_cap")
    current_price = cf.get("current_price")
    try:
        inferred_shares = float(market_cap) / float(current_price)
    except (TypeError, ValueError, ZeroDivisionError):
        inferred_shares = 0.0
    if inferred_shares > 0:
        for period in hist:
            state.income_statement.setdefault("shares_diluted", {}).setdefault(
                period.label,
                ModelCell(value=inferred_shares, source="historical", last_edited_by="system"),
            )


def _apply_baseline_drivers(state: ModelState, response: BaselineDriversResponse) -> None:
    """Inject Sonnet-generated drivers into state.drivers, source='ai_baseline'.

    Fallback: if Sonnet omits some forecast periods (common when the model only
    returns annual labels but the model has quarterly forecast periods), clone
    drivers from the most-recently-specified period to fill any gaps. This
    prevents recompute() from failing with "no prior revenue" on the first
    unspecified period.
    """
    now = datetime.utcnow().isoformat()
    for period_label, drvs in response.drivers.items():
        if period_label not in state.drivers:
            state.drivers[period_label] = {}
        for k, proposal in drvs.items():
            state.drivers[period_label][k] = ModelCell(
                value=proposal.value,
                source="ai_baseline",
                citation_id=proposal.source_citation_id,
                last_edited_at=now,
                last_edited_by="ai_baseline",
                formula=proposal.reason or None,
            )

    # --- Fallback: fill missing forecast periods from the last specified period ---
    forecast_labels = [p.label for p in state.periods if not p.is_historical]
    # Find the first forecast period with at least one non-None driver value
    template_label: str | None = None
    for lbl in forecast_labels:
        period_drvs = state.drivers.get(lbl, {})
        if any(cell.value is not None for cell in period_drvs.values()):
            template_label = lbl
            break

    if template_label is None:
        return  # Nothing to clone from — recompute will surface its own error

    template_drivers = state.drivers[template_label]
    for lbl in forecast_labels:
        if lbl == template_label:
            continue
        period_drvs = state.drivers.setdefault(lbl, {})
        for k, tmpl_cell in template_drivers.items():
            existing = period_drvs.get(k)
            if existing is None or existing.value is None:
                # Fill missing / None-valued key from template
                period_drvs[k] = ModelCell(
                    value=tmpl_cell.value,
                    source="ai_baseline",
                    citation_id=tmpl_cell.citation_id,
                    last_edited_at=now,
                    last_edited_by="ai_baseline",
                    formula=f"[cloned from {template_label}] {tmpl_cell.formula or ''}".strip(),
                )


async def build_baseline_state(*, ticker: str, forecast_period_labels: list[str] | None = None) -> ModelState:
    ctx = await _load_seeding_context(ticker)
    periods = _build_periods()
    if forecast_period_labels is not None:
        periods = [p for p in periods if p.is_historical or p.label in forecast_period_labels]
    forecast = [p.label for p in periods if not p.is_historical]
    if forecast_period_labels is None:
        # Only ask Sonnet for annual periods — quarterly ones are filled by the
        # fallback in _apply_baseline_drivers (clone from nearest annual).
        # This keeps the LLM output comfortably under 8K tokens.
        forecast_period_labels = [lbl for lbl in forecast if lbl.endswith("Y")]
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


async def initialize_or_get_model(ticker: str, *, force: bool = False):
    """Returns the latest TickerModel row for ticker, building one if missing or force=True.
    The returned object is a TickerModel ORM row (state already a dict via Pydantic round-trip)."""
    from backend.app.db import async_session
    from backend.app.models.ticker_model import TickerModel
    from sqlalchemy import select, desc
    async with async_session() as db:
        stmt = select(TickerModel).where(TickerModel.ticker == ticker).order_by(desc(TickerModel.version)).limit(1)
        latest = (await db.execute(stmt)).scalar_one_or_none()
        if latest is not None and not force:
            return latest
        next_version = 1 if latest is None else latest.version + 1
        state = await build_baseline_state(ticker=ticker)
        row = TickerModel(
            ticker=ticker, version=next_version,
            state=state.model_dump(),
            label=("AI baseline" if latest is None else "AI reseed"),
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row

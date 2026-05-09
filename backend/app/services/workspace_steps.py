"""Five workspace step functions. Stubs for Phase 1; real implementations land in Phases 2-6."""
from __future__ import annotations
import copy
import json
from datetime import datetime, timezone
from typing import Callable

from backend.app.services.workspace_context import WorkspaceContext
from backend.app.models.workspace_schemas import (
    UpdateRefreshOutput, ChangedCell, FilingRef,
    ResearchOutput, ValidationOutput,
    ChallengeOutput, DifferentiationOutput,
    Highlight, OpenQuestionDelta,
    ImpliedDriver, SensitivityGrid as WSSensitivityGrid, ThesisVsPriced,
)
from backend.app.graph.llm import complete as anthropic_complete, HAIKU, SONNET
from backend.app.graph.workspace_prompts import (
    RESEARCH_SYSTEM, RESEARCH_USER_TEMPLATE,
    CHALLENGE_SYSTEM, CHALLENGE_USER_TEMPLATE,
)
from backend.app.services.reverse_dcf import (
    solve_implied_driver,
    solve_implied_irr,
    sensitivity_grid,
    thesis_vs_priced_in,
)
from backend.app.services.peer_comp import build_peer_comp_table


def _fmp_period_label(row: dict) -> str | None:
    """Combine FMP 'period' (e.g. 'Q1') + 'calendarYear' (e.g. '2026') → '2026Q1'.

    Annual rows use 'FY' or similar; we skip those (historical patching is
    quarterly-only in this step).
    """
    period = row.get("period", "")
    year = str(row.get("calendarYear", ""))
    if not period or not year:
        return None
    # Quarterly: period like "Q1", "Q2", "Q3", "Q4"
    if period.startswith("Q") and period[1:].isdigit():
        return f"{year}{period}"
    return None


def _make_cell(value: float, source: str, citation_id: str | None):
    """Construct a ModelCell with the given value and source."""
    from backend.app.models.model_state import ModelCell
    return ModelCell(value=value, source=source, formula=None, citation_id=citation_id)


def _patch_statement(
    statement: dict,
    rows: list[dict],
    field_map: dict[str, str],
    citation_id: str | None,
    historical_labels: set[str],
) -> None:
    """Patch historical cells in a statement dict from FMP rows.

    Only writes cells whose period is in the model's historical periods
    AND whose existing source is 'historical' or the cell is missing.
    Forecast cells and user overrides are never touched.
    """
    for row in rows:
        period = _fmp_period_label(row)
        if not period or period not in historical_labels:
            continue
        for fmp_key, line_item in field_map.items():
            raw = row.get(fmp_key)
            if raw is None:
                continue
            try:
                value = float(raw)
            except (TypeError, ValueError):
                continue
            line_dict = statement.setdefault(line_item, {})
            existing = line_dict.get(period)
            # Only write if cell is missing or was a previous historical value
            if existing is None or existing.source == "historical":
                line_dict[period] = _make_cell(value, "historical", citation_id)


# FMP income statement field → ModelState line_item
_INCOME_FIELD_MAP: dict[str, str] = {
    "revenue": "revenue",
    "grossProfit": "gross_profit",
    "operatingIncome": "ebit",
    "netIncome": "net_income",
    "eps": "eps_diluted",
    "weightedAverageShsOutDil": "shares_diluted",
}

# FMP balance sheet field → ModelState line_item
_BALANCE_FIELD_MAP: dict[str, str] = {
    "cashAndCashEquivalents": "cash_and_equivalents",
    "totalDebt": "long_term_debt",   # best available single-field proxy
    "totalAssets": "total_assets",
    "totalEquity": "total_equity",
}

# FMP cash flow field → ModelState line_item
_CF_FIELD_MAP: dict[str, str] = {
    "operatingCashFlow": "operating_cash_flow",
    "capitalExpenditure": "capex",
    "freeCashFlow": "free_cash_flow",
}


async def _fetch_live_price(fmp, ticker: str) -> float:
    """Pull current price from FMP. Returns 0.0 on any error so callers can fall back gracefully."""
    try:
        quote, _citation = await fmp.get_quote(ticker)
        return float((quote.get("price") if quote else 0.0) or 0.0)
    except Exception:
        return 0.0


def _baseline_value_for_dim(state, dim: str) -> float:
    """Return the average forecast value for dim, or 0.0 if unavailable."""
    from backend.app.models.model_state import ModelState
    forecast = [p for p in state.periods if not p.is_historical]
    if dim == "terminal_multiple":
        cell = state.assumptions.terminal_multiple
        return cell.value or 0.0 if cell is not None else 0.0
    vals = [
        state.drivers.get(p.label, {}).get(dim, None)
        for p in forecast
    ]
    nums = [c.value for c in vals if c is not None and c.value is not None]
    return sum(nums) / len(nums) if nums else 0.0


async def step_update_refresh(ctx: WorkspaceContext) -> UpdateRefreshOutput:
    from backend.app.models.model_state import ModelState
    from backend.app.services.model_balancing import recompute
    from backend.app.services.model_diff import diff_states
    from backend.app.models.ticker_model import TickerModel

    prior_state = ModelState.model_validate(ctx.prior_ticker_model.state)

    # ── 1. Pull latest quarterly data from FMP ───────────────────────────────
    income_rows, fmp_cit_income = await ctx.fmp.get_income_statement(
        ctx.ticker, period="quarter", limit=2
    )
    balance_rows, fmp_cit_balance = await ctx.fmp.get_balance_sheet(
        ctx.ticker, period="quarter", limit=2
    )
    cf_rows, fmp_cit_cf = await ctx.fmp.get_cash_flow(
        ctx.ticker, period="quarter", limit=2
    )
    # analyst estimates fetched but deferred to future step (consensus_delta=None in v1)
    await ctx.fmp.get_analyst_estimates(ctx.ticker, limit=8)

    # ── 2. Fetch latest 10-Q / 10-K index from EDGAR (best-effort) ──────────
    # EdgarClient has no get_latest_filing() helper; call get_ticker_to_cik +
    # get_submissions and replicate the _latest_per_form logic from edgar_sections_ingest.
    new_filings: list[FilingRef] = []
    cik, _ = await ctx.edgar.get_ticker_to_cik(ctx.ticker)
    if cik:
        try:
            submissions, _ = await ctx.edgar.get_submissions(cik)
            recent = submissions.get("filings", {}).get("recent", {}) or {}
            forms = recent.get("form", [])
            accessions = recent.get("accessionNumber", [])
            filing_dates = recent.get("filingDate", [])
            for i, form in enumerate(forms):
                if form in ("10-Q", "10-K"):
                    accession = accessions[i] if i < len(accessions) else ""
                    filed_date = filing_dates[i] if i < len(filing_dates) else ""
                    new_filings.append(FilingRef(
                        form=form,
                        accession=accession,
                        fetched_at=filed_date,
                    ))
                    break  # only the most recent 10-Q or 10-K
        except Exception:  # noqa: BLE001 — EDGAR is best-effort
            pass

    # ── 3. Patch new_state with fresh actuals (forecast/override cells preserved) ──
    new_state = copy.deepcopy(prior_state)

    income_cit_id = fmp_cit_income.id if fmp_cit_income and hasattr(fmp_cit_income, "id") else None
    balance_cit_id = fmp_cit_balance.id if fmp_cit_balance and hasattr(fmp_cit_balance, "id") else None
    cf_cit_id = fmp_cit_cf.id if fmp_cit_cf and hasattr(fmp_cit_cf, "id") else None

    historical_labels: set[str] = {p.label for p in new_state.periods if p.is_historical}

    _patch_statement(new_state.income_statement, income_rows, _INCOME_FIELD_MAP, income_cit_id, historical_labels)
    _patch_statement(new_state.balance_sheet, balance_rows, _BALANCE_FIELD_MAP, balance_cit_id, historical_labels)
    _patch_statement(new_state.cash_flow, cf_rows, _CF_FIELD_MAP, cf_cit_id, historical_labels)

    # ── 4. Recompute derived cells on both states so that computed-only cells
    #       cancel out in the diff; only genuinely new/changed actuals remain. ──
    prior_recomputed = recompute(copy.deepcopy(prior_state))
    new_state = recompute(new_state)

    # ── 5. Diff ──────────────────────────────────────────────────────────────
    diff = diff_states(prior_recomputed, new_state)

    # "changed" = value/source shifted on existing cells
    # "added"   = brand-new cells (new quarter actuals land here)
    # "removed" = ignored (we never remove cells in a refresh)
    changed_cells: list[ChangedCell] = []
    for entry in diff.get("changed", []):
        changed_cells.append(ChangedCell(
            cell_path=entry["cell_path"],
            prior_value=entry["before"]["value"],
            new_value=entry["after"]["value"],
            source=entry["after"]["source"],
            citation_id=None,
        ))

    # Walk new_state to get value/source for each newly-added cell path
    from backend.app.services.model_diff import _walk_cells as _walk
    new_cell_map = {p: c for p, c in _walk(new_state)}
    for path in diff.get("added", []):
        cell = new_cell_map.get(path)
        changed_cells.append(ChangedCell(
            cell_path=path,
            prior_value=None,
            new_value=cell.value if cell else None,
            source=cell.source if cell else "historical",
            citation_id=cell.citation_id if cell else None,
        ))

    # ── 6. Persist new version only when something changed ───────────────────
    version_after: int | None = None
    if changed_cells:
        new_row = TickerModel(
            ticker=ctx.ticker.upper(),
            version=ctx.prior_ticker_model.version + 1,
            state=new_state.model_dump(mode="json"),
            parent_research_run_id=ctx.prior_ticker_model.parent_research_run_id,
        )
        ctx.db.add(new_row)
        await ctx.db.flush()
        version_after = new_row.version

    # ── 7. Build summary ─────────────────────────────────────────────────────
    if new_filings:
        f = new_filings[0]
        summary = (
            f"loaded latest {f.form} (filed {f.fetched_at}); "
            f"{len(changed_cells)} cells updated"
        )
    else:
        summary = (
            f"no new EDGAR filing detected; "
            f"{len(changed_cells)} cells updated from FMP quarterly refresh"
        )

    return UpdateRefreshOutput(
        version_before=ctx.prior_ticker_model.version,
        version_after=version_after,
        changed_cells=changed_cells,
        new_filings=new_filings,
        consensus_delta=None,
        summary=summary,
    )


async def haiku_complete(*, system: str, user: str, anthropic) -> str:
    """Thin wrapper around graph.llm.complete; named for easy patching in tests."""
    return await anthropic_complete(
        system=system, user=user, model=HAIKU,
        max_tokens=2048,
    )


async def sonnet_complete(*, system: str, user: str, anthropic) -> str:
    """Thin wrapper around graph.llm.complete using Sonnet; named for easy patching in tests."""
    return await anthropic_complete(
        system=system, user=user, model=SONNET,
        max_tokens=4096,
    )


async def upsert_kill_criterion_state(db, run_id: str, ordinal: int, status: str, note: str | None) -> None:
    """Re-exports the canonical helper so tests can patch this name directly."""
    from backend.app.services.status_board import upsert_kill_criterion_state as impl
    await impl(db, run_id=run_id, ordinal=ordinal, status=status, note=note)


def _parse_json_lenient(raw: str) -> dict:
    """Strip code fences and parse. Returns {} on parse failure rather than raising."""
    txt = raw.strip()
    if txt.startswith("```"):
        # Trim leading fence
        idx = txt.find("\n")
        if idx >= 0:
            txt = txt[idx + 1:]
        if txt.endswith("```"):
            txt = txt[:-3]
    try:
        return json.loads(txt)
    except json.JSONDecodeError:
        return {}


def _gather_new_sources_text(ctx: WorkspaceContext) -> str:
    """Best-effort concatenation of new filing excerpts pulled by Step 1.
    Reads from the ticker_model's state if Step 1 stashed text there;
    otherwise returns an empty string and the prompt operates on prior thesis only."""
    # v1: rely on whatever Step 1 already pulled into the new ticker_model.
    # Step 1 doesn't currently stash filing text; this is a slot for v1.5.
    return ""


async def step_research(ctx: WorkspaceContext) -> ResearchOutput:
    # Pull prior thesis
    prior_state = ctx.prior_research_run.state or {}
    phase_outputs = prior_state.get("phase_outputs") or {}
    prior_thesis = (phase_outputs.get("thesis") or {}).get("content") or "(no prior thesis available)"

    # Pull existing open questions (Tier 1.2)
    existing_qs = prior_state.get("questions_extracted") or []
    existing_qs_text = "\n".join(
        f"- {q.get('question', q) if isinstance(q, dict) else q}"
        for q in existing_qs[:20]
    ) or "(none)"

    # New sources: latest filing section excerpts + transcript paragraphs
    # For v1, pass the prior research_run's own filing-excerpt summary (lightweight).
    # Real ingest happens in Step 1; here we just summarize what Step 1 surfaced.
    new_sources = _gather_new_sources_text(ctx)[:8000]

    user = RESEARCH_USER_TEMPLATE.format(
        prior_thesis=prior_thesis,
        new_sources=new_sources or "(no new filing/transcript text available)",
        existing_open_questions=existing_qs_text,
    )

    raw = await haiku_complete(system=RESEARCH_SYSTEM, user=user, anthropic=ctx.anthropic)
    payload = _parse_json_lenient(raw)

    highlights = [Highlight.model_validate(h) for h in payload.get("highlights", [])]
    open_qs = [
        OpenQuestionDelta(
            question=q.get("question", ""),
            surfaced_by=ctx.run_id,
            classification=q.get("classification", "general"),
        )
        for q in payload.get("new_open_questions", [])
    ]

    return ResearchOutput(
        highlights=highlights,
        new_open_questions=open_qs,
        summary=payload.get("summary", "(no summary returned)"),
    )


async def step_validation(ctx: WorkspaceContext) -> ValidationOutput:
    """Step 3: re-run reverse-DCF against the freshly updated model (post-Step-1 version)."""
    from backend.app.models.model_state import ModelState
    from backend.app.models.ticker_model import TickerModel
    from sqlalchemy import select, desc

    # 1. Load the LATEST ticker_models row (post-Step-1 if it created a new version).
    row = (
        await ctx.db.execute(
            select(TickerModel)
            .where(TickerModel.ticker == ctx.ticker)
            .order_by(desc(TickerModel.version))
            .limit(1)
        )
    ).scalar_one_or_none()

    if row is None:
        return ValidationOutput(current_price=0.0)

    state = ModelState.model_validate(row.state)

    # 2. Fetch live price.
    price = await _fetch_live_price(ctx.fmp, ctx.ticker)
    if not price:
        return ValidationOutput(current_price=0.0)

    # 3. Implied drivers (safe — returns 0.0 on ValueError).
    _DIMS = ["revenue_growth_pct", "ebit_margin_pct", "terminal_multiple"]

    def _safe_solve_driver(dim: str) -> float:
        try:
            return solve_implied_driver(state, dimension=dim, target_per_share=price)
        except (ValueError, Exception):
            return 0.0

    implied_drivers = [
        ImpliedDriver(
            dimension=dim,
            implied_value=_safe_solve_driver(dim),
            baseline_value=_baseline_value_for_dim(state, dim),
        )
        for dim in _DIMS
    ]

    # 4. Implied IRR.
    try:
        implied_irr: float | None = solve_implied_irr(state, target_per_share=price)
    except (ValueError, Exception):
        implied_irr = None

    # 5. Sensitivity grids — same axes as the model page.
    _GRID_SPECS = [
        ("revenue_growth_pct", (-0.05, 0.20), "ebit_margin_pct",   (-0.10, 0.40)),
        ("revenue_growth_pct", (-0.05, 0.20), "terminal_multiple", (5.0,  25.0)),
        ("ebit_margin_pct",    (-0.10, 0.40), "terminal_multiple", (5.0,  25.0)),
    ]
    grids: list[WSSensitivityGrid] = []
    for x_dim, x_range, y_dim, y_range in _GRID_SPECS:
        raw = sensitivity_grid(
            state,
            x_dim=x_dim,
            x_range=x_range,
            y_dim=y_dim,
            y_range=y_range,
        )
        grids.append(WSSensitivityGrid(
            dim_x=raw["x_dim"],
            dim_y=raw["y_dim"],
            x_axis=raw["x_values"],
            y_axis=raw["y_values"],
            values=raw["values"],
        ))

    # 6. Thesis-vs-priced-in rows.
    # reverse_dcf returns {dimension, thesis, priced_in, delta}; schema wants metric/thesis_value/…
    raw_thesis = thesis_vs_priced_in(state, target_per_share=price)
    thesis_rows: list[ThesisVsPriced] = []
    for row_t in raw_thesis:
        priced_in = row_t.get("priced_in") or 0.0
        thesis_val = row_t.get("thesis") or 0.0
        delta = thesis_val - priced_in if priced_in else 0.0
        delta_pct = delta / abs(priced_in) if priced_in else 0.0
        thesis_rows.append(ThesisVsPriced(
            metric=row_t["dimension"],
            thesis_value=thesis_val,
            priced_in_value=priced_in,
            delta_pct=delta_pct,
        ))

    return ValidationOutput(
        implied_drivers=implied_drivers,
        implied_irr=implied_irr,
        sensitivity_grids=grids,
        thesis_vs_priced_in=thesis_rows,
        current_price=price,
    )


async def step_challenge(ctx: WorkspaceContext) -> ChallengeOutput:
    import logging
    from sqlalchemy import select
    from backend.app.models.workspace_schemas import KillCriterionWrite, CatalystUpdate, WorkspaceVerdict
    from backend.app.models.kill_criterion_state import KillCriterionState
    from backend.app.models.catalyst import Catalyst

    log = logging.getLogger(__name__)

    prior_state = ctx.prior_research_run.state or {}
    phase_outputs = prior_state.get("phase_outputs") or {}
    thesis_block = phase_outputs.get("thesis") or {}
    prior_thesis = thesis_block.get("content") or "(no prior thesis)"

    # Kill criteria DEFINITIONS from thesis structured output
    kc_defs = (thesis_block.get("structured") or {}).get("kill_criteria") or []
    # Current states from ORM
    states_rows = (await ctx.db.execute(
        select(KillCriterionState).where(KillCriterionState.run_id == ctx.prior_research_run.id)
    )).scalars().all()
    states_by_ordinal = {s.ordinal: s.status for s in states_rows}

    kill_criteria_payload = []
    for i, kc in enumerate(kc_defs):
        if isinstance(kc, dict):
            desc = kc.get("condition") or kc.get("criterion") or kc.get("description") or kc.get("text") or str(kc)
        else:
            desc = str(kc)
        ordinal = i + 1
        kill_criteria_payload.append({
            "ordinal": ordinal,
            "description": desc,
            "current_status": states_by_ordinal.get(ordinal, "armed"),
        })

    # Catalysts from ORM
    cats_rows = (await ctx.db.execute(
        select(Catalyst).where(Catalyst.run_id == ctx.prior_research_run.id)
    )).scalars().all()
    catalysts_payload = [
        {
            "id": str(c.id),
            "type": c.type,
            "description": c.description,
            "expected_window_start": str(c.expected_window_start) if c.expected_window_start else None,
            "expected_window_end": str(c.expected_window_end) if c.expected_window_end else None,
        }
        for c in cats_rows
    ]

    kill_text = "\n".join(
        f"  ordinal {kc['ordinal']} [{kc['current_status']}]: {kc['description']}"
        for kc in kill_criteria_payload
    ) or "(none)"
    cat_text = "\n".join(
        f"  id {c['id']} [{c['type'] or 'other'}]: {c['description']} "
        f"(window: {c['expected_window_start'] or '?'} → {c['expected_window_end'] or '?'})"
        for c in catalysts_payload
    ) or "(none)"

    user = CHALLENGE_USER_TEMPLATE.format(
        prior_thesis=prior_thesis,
        kill_criteria=kill_text,
        catalysts=cat_text,
        model_deltas="(see step_outputs.update_refresh.changed_cells)",
        new_sources="(no new excerpts)",
    )

    raw = await sonnet_complete(system=CHALLENGE_SYSTEM, user=user, anthropic=ctx.anthropic)
    payload = _parse_json_lenient(raw)

    writes = [KillCriterionWrite(**w) for w in payload.get("kill_criterion_writes", [])]
    updates = [CatalystUpdate(**u) for u in payload.get("catalyst_updates", [])]

    verdict_str = payload.get("proposed_verdict", "healthy")
    try:
        verdict = WorkspaceVerdict(verdict_str)
    except ValueError:
        verdict = WorkspaceVerdict.HEALTHY

    # Apply kill-criterion writebacks (best-effort per row).
    for w in writes:
        try:
            await upsert_kill_criterion_state(
                ctx.db,
                run_id=ctx.prior_research_run.id,
                ordinal=w.ordinal,
                status=w.status,
                note=w.note,
            )
        except Exception as exc:  # noqa: BLE001
            log.exception("kill_criterion writeback failed for ordinal %s: %s", w.ordinal, exc)

    # Catalyst writebacks deferred to v1.5 (Catalyst.status column not yet present);
    # recommendations surface in catalyst_updates output for UI.

    return ChallengeOutput(
        stress_test_summary=payload.get("stress_test_summary", "(no summary)"),
        kill_criterion_writes=writes,
        catalyst_updates=updates,
        proposed_verdict=verdict,
    )


# ── Step 5: Differentiation ────────────────────────────────────────────

PEER_CAP = 8


async def _fetch_resolved_peers(ctx: WorkspaceContext) -> list[str]:
    """Pull resolved competitor tickers from competitor_landscape for this ticker.
    Cap at PEER_CAP. De-dup. Excludes the focus ticker itself."""
    from sqlalchemy import select
    from backend.app.models.filing import CompetitorLandscape

    rows = (await ctx.db.execute(
        select(CompetitorLandscape).where(CompetitorLandscape.ticker == ctx.ticker)
    )).scalars().all()

    seen: set[str] = set()
    peers: list[str] = []
    for row in rows:
        for c in (row.competitors or []):
            t = (c.get("resolved_to_ticker") or "").upper()
            if t and t != ctx.ticker.upper() and t not in seen:
                seen.add(t)
                peers.append(t)
                if len(peers) >= PEER_CAP:
                    return peers
    return peers


async def _fetch_read_throughs_for_ticker(ctx: WorkspaceContext) -> list[dict]:
    """Use the existing read-through service, filtered to this ticker's research run."""
    from datetime import timedelta
    from backend.app.services.read_through import resolve_read_throughs, compute_peer_events

    now = datetime.now(timezone.utc)
    events = await compute_peer_events(ctx.db, since=now - timedelta(days=30), until=now + timedelta(days=30))
    run_id = ctx.prior_research_run.id
    result = await resolve_read_throughs(ctx.db, status_run_ids=[run_id], peer_events=events)
    items = result.get(run_id, [])
    # Serialize each ReadThroughItem to dict.
    return [i.model_dump(mode="json") if hasattr(i, "model_dump") else dict(i) for i in items]


async def step_differentiation(ctx: WorkspaceContext) -> DifferentiationOutput:
    peers = await _fetch_resolved_peers(ctx)
    table, errors = await build_peer_comp_table(
        focus_ticker=ctx.ticker, peer_tickers=peers, fmp=ctx.fmp,
    ) if peers else (None, [])
    read_throughs = await _fetch_read_throughs_for_ticker(ctx)
    return DifferentiationOutput(
        peer_comp=table,
        read_throughs=read_throughs,
        per_peer_errors=errors,
    )


STEP_NAMES = ["update_refresh", "research", "validation", "challenge", "differentiation"]
STEP_FUNCTIONS = {
    "update_refresh": step_update_refresh,
    "research": step_research,
    "validation": step_validation,
    "challenge": step_challenge,
    "differentiation": step_differentiation,
}


async def run_steps_in_sequence(ctx: WorkspaceContext, emit: Callable[[dict], None]) -> dict:
    """Run all 5 steps in order. Per-step errors do NOT abort; output dict is keyed by step name."""
    outputs: dict = {}
    for name in STEP_NAMES:
        emit({"type": "step_start", "step": name})
        try:
            result = await STEP_FUNCTIONS[name](ctx)
            outputs[name] = result.model_dump(mode="json")
            emit({"type": "step_complete", "step": name, "output": outputs[name]})
        except NotImplementedError as e:
            outputs[name] = {"error": f"not_implemented: {e}"}
            emit({"type": "step_failed", "step": name, "error": str(e)})
        except Exception as e:  # noqa: BLE001 - intentional broad catch per spec
            outputs[name] = {"error": str(e)}
            emit({"type": "step_failed", "step": name, "error": str(e)})
    return outputs

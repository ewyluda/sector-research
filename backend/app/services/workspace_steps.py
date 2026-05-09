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
)
from backend.app.graph.llm import complete as anthropic_complete, HAIKU
from backend.app.graph.workspace_prompts import RESEARCH_SYSTEM, RESEARCH_USER_TEMPLATE


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
    prior_thesis = (prior_state.get("thesis") or {}).get("summary_markdown") or "(no prior thesis available)"

    # Pull existing open questions (Tier 1.2)
    existing_qs = (prior_state.get("question_log") or {}).get("questions", [])
    existing_qs_text = "\n".join(f"- {q.get('question', '')}" for q in existing_qs[:20]) or "(none)"

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
    raise NotImplementedError("Phase 4")


async def step_challenge(ctx: WorkspaceContext) -> ChallengeOutput:
    raise NotImplementedError("Phase 5")


async def step_differentiation(ctx: WorkspaceContext) -> DifferentiationOutput:
    raise NotImplementedError("Phase 6")


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

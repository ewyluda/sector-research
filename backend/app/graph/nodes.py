"""Phase node implementations for the research pipeline (see graph/routing.py).

Each node receives ResearchState, does work, mutates state, and returns it.
Every node is a pure async function — no side effects except state mutation.

Phase assignments:
  quick_screen      → Haiku
  deep_dive (×9)    → Sonnet, parallel subgraph
  thesis            → Sonnet
  risk_stress_test  → Sonnet
  position_monitor  → Haiku

Formatting helpers, curated-financials builders, transcript analysis, and
question-lifecycle helpers were split out in M2.2:
  - backend.app.graph.formatters  (data formatters)
  - backend.app.services.transcript_analysis
  - backend.app.services.question_lifecycle
All moved symbols are re-exported here so existing importers keep working.
New code should import from the destination modules directly; the re-exports
are a transitional shim deletable once the remaining consumers migrate
(backend/tests/test_output_parsing.py, test_quant_fingerprint.py,
test_deep_dive_valuation_ratios.py, scripts/smoke_question_log.py,
services/questions.py).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date

from backend.app.clients.fmp import FMPClient, recent_13f_quarters
from backend.app.clients.fred import FREDClient
from backend.app.db import unit_of_work
from backend.app.logging_filters import redact_secrets
from backend.app.graph.deep_dive_context import DeepDiveContext, build_all_contexts
from backend.app.graph.deep_dive_helpers import (
    unwrap_gather_citation,
    unwrap_gather_result as _unwrap,
)
from backend.app.graph.formatters import (  # noqa: F401  re-exported for backwards compat
    _build_curated_financials,
    _build_technical_data,
    _first_metric,
    _fmt_fundamentals,
)
from backend.app.graph.llm import complete_structured, DEEP_MODEL, FAST_MODEL
from backend.app.graph.routing import MAX_RISK_LOOPS, should_loop
from backend.app.graph.prompts import (
    QUICK_SCREEN_SYSTEM, QUICK_SCREEN_USER,
    DEEP_DIVE_SYSTEM, DEEP_DIVE_SHARED, DEEP_DIVE_USER, DEEP_DIVE_CATEGORIES,
    THESIS_SYSTEM, THESIS_USER,
    RISK_SYSTEM, RISK_USER,
    POSITION_SYSTEM, POSITION_USER,
)
from backend.app.graph.state import (
    ResearchState, CategoryResult, CategoryError, StateCitation, StateQuestion, StateResolvedQuestion
)
from backend.app.models.phase_schemas import (
    QuickScreenOutput, ThesisLLMOutput, RiskStressTestOutput, PositionMonitorOutput,
    DeepDiveCategoryOutput, reward_risk,
    quick_screen_recommendation, quick_screen_score,
)
from backend.app.services.catalyst_promotion import promote_catalysts
from backend.app.services.edgar_transcripts_relationships import (
    TRANSCRIPT_QUARTER_LIMIT,
    fetch_recent_transcripts,
)
from backend.app.services.question_lifecycle import (  # noqa: F401  re-exported for backwards compat
    _apply_resurfaced_resolutions,
    _fetch_prior_open_questions,
    _persist_extracted_questions,
    _render_prior_questions_slot,
    _render_questions_resolved,
)
from backend.app.services.transcript_analysis import run_transcript_analysis  # noqa: F401  re-exported for backwards compat

logger = logging.getLogger(__name__)

# Seconds per deep-dive category. Sized for a thinking model (Opus 5.5 at
# medium effort); the llm_call log lines report the real latency per call.
CATEGORY_TIMEOUT = 300

# Theme descriptions are free text pasted by the user and can run to several
# thousand characters; the prompt gets the name plus a bounded excerpt.
THEME_DESCRIPTION_BUDGET_CHARS = 1200


def _theme_context(state: ResearchState) -> str:
    """The investment theme as the model should see it: name + description."""
    if not state.theme_name:
        return "(theme not recorded for this run)"
    desc = " ".join(state.theme_description.split())[:THEME_DESCRIPTION_BUDGET_CHARS]
    return f"{state.theme_name} — {desc}" if desc else state.theme_name


def _market_data_block(state: ResearchState) -> str:
    """Price context for steps that talk about levels or reward/risk. Without
    it the model invents a price (VRT plan assumed ~$100; actual ~$300)."""
    cf = state.curated_financials or {}
    price = cf.get("current_price")
    if not isinstance(price, (int, float)) or price <= 0:
        return "(no current price available)"
    lines = [f"Current price: ${price:,.2f}"]
    lo, hi = cf.get("fifty_two_week_low"), cf.get("fifty_two_week_high")
    if isinstance(lo, (int, float)) and isinstance(hi, (int, float)):
        lines.append(f"52-week range: ${lo:,.2f} – ${hi:,.2f}")
    last = (cf.get("daily_prices") or [{}])[-1] or {}
    tech = [
        f"{label} ${last[key]:,.2f}" for key, label in (("sma_50", "SMA50"), ("sma_200", "SMA200"))
        if isinstance(last.get(key), (int, float))
    ]
    if isinstance(last.get("rsi"), (int, float)):
        tech.append(f"RSI14 {last['rsi']:.0f}")
    if tech:
        lines.append("Technicals: " + ", ".join(tech))
    dcf = cf.get("dcf_intrinsic_value")
    if isinstance(dcf, (int, float)):
        # A non-positive DCF value (negative FCF) makes a "gap" meaningless.
        lines.append(f"FMP DCF value: ${dcf:,.2f}" if dcf > 0 else "FMP DCF value: n/m (non-positive)")
    return "\n".join(lines)


def _category_analysis_text(result: CategoryResult) -> str:
    """What the thesis step reads per category: the rationale, the analysis
    and the stated data gaps. (It used to get content[:800] — the head of the
    raw JSON, which ends before the analysis field starts.)"""
    st = result.structured or {}
    if not st.get("analysis"):
        return result.content[:3000]
    parts = [st.get("score_rationale", ""), st["analysis"]]
    gaps = st.get("data_gaps") or []
    if gaps:
        parts.append("Data gaps: " + "; ".join(gaps))
    return "\n\n".join(p for p in parts if p)


def _reward_risk_line(thesis_struct: dict, computed_rr: float | None) -> str:
    """The thesis's call as the risk step should see it."""
    stance = thesis_struct.get("stance")
    targets = thesis_struct.get("price_targets") or {}
    if not stance:
        return "(no directional call on this thesis)"
    line = f"Stance: {stance}"
    if targets:
        line += (f"; targets ({thesis_struct.get('time_horizon') or 'horizon n/a'}): "
                 f"bear ${targets.get('bear')}, base ${targets.get('base')}, bull ${targets.get('bull')}")
    if computed_rr is not None:
        line += f"; reward/risk computed from these targets: {computed_rr}:1"
    return line


def _as_of() -> str:
    """Today's date, so catalyst timing and 'within N days' rules have an anchor."""
    return date.today().isoformat()
TARGETED_FOLLOWUP_CONTEXT_BUDGET_CHARS = 14000


# ── Tier-2 degradable helpers ─────────────────────────────────────────────────

async def _fetch_institutional(
    fmp: FMPClient, ticker: str
) -> tuple[tuple[dict | None, list], list]:
    """13F summary + top holders for the latest filed quarter.

    Walks back up to 4 quarters (a 13F for the in-progress quarter cannot
    exist). Degradable: any failure or no-data returns empty — the
    fundamentals section simply doesn't render.
    Returns ((summary | None, holders: list), citations: list[Citation]).
    """
    try:
        citations = []
        for year, quarter in recent_13f_quarters(date.today()):
            summary, sum_cit = await fmp.get_institutional_summary(ticker, year, quarter)
            if summary is None:
                continue
            # Found a quarter with data — also fetch holders (degrade independently)
            citations.append(sum_cit)
            try:
                holders, hld_cit = await fmp.get_institutional_holders(ticker, year, quarter)
                citations.append(hld_cit)
            except Exception as e:
                logger.warning("[%s] _fetch_institutional holders failed: %s", ticker, e)
                holders = []
            return (summary, holders), citations
        # All quarters returned empty
        return (None, []), []
    except Exception as e:
        logger.warning("[%s] _fetch_institutional failed: %s", ticker, e)
        return (None, []), []


# ── Phase 1+2: quick_screen ───────────────────────────────────────────────────

async def node_quick_screen(state: ResearchState, fmp: FMPClient) -> ResearchState:
    """Phases 1+2: pull FMP data, score 5 dimensions, produce GO/WATCHLIST/PASS."""
    logger.info("[%s] quick_screen starting", state.ticker)
    state.phase = "quick_screen"

    try:
        # Fetch fundamentals
        (income, inc_cit), (balance, bal_cit), (cashflow, cf_cit), (profile, prof_cit) = (
            await asyncio.gather(
                fmp.get_income_statement(state.ticker, limit=4),
                fmp.get_balance_sheet(state.ticker, limit=2),
                fmp.get_cash_flow(state.ticker, limit=2),
                fmp.get_company_profile(state.ticker),
            )
        )

        for cit in [inc_cit, bal_cit, cf_cit, prof_cit]:
            state.add_citation(StateCitation.from_citation(cit))

        fundamentals_text = _fmt_fundamentals(
            state.ticker,
            income if isinstance(income, list) else [],
            balance if isinstance(balance, list) else [],
            cashflow if isinstance(cashflow, list) else [],
            profile[0] if isinstance(profile, list) and profile else profile or {},
        )

        parsed = await complete_structured(
            system=QUICK_SCREEN_SYSTEM,
            user=QUICK_SCREEN_USER.format(
                ticker=state.ticker,
                theme=_theme_context(state),
                as_of=_as_of(),
                fundamental_data=fundamentals_text,
            ),
            output_model=QuickScreenOutput,
            model=FAST_MODEL,
            max_tokens=2500,
        )

        # Score and verdict are derived in code from the dimension scores;
        # the model's own totals are kept only for auditing disagreement.
        score = quick_screen_score(parsed.dimensions)
        recommendation = quick_screen_recommendation(score)
        if (score, recommendation) != (parsed.overall_score, parsed.recommendation):
            logger.info(
                "[%s] quick_screen model said %d/%s; dimensions sum to %d/%s",
                state.ticker, parsed.overall_score, parsed.recommendation,
                score, recommendation,
            )
        structured = parsed.model_copy(
            update={"overall_score": score, "recommendation": recommendation}
        ).model_dump()

        state.phase_outputs["quick_screen"] = {
            "__type__": "PhaseOutput",
            "content": parsed.model_dump_json(),
            "structured": structured,
            "score": score,
            "recommendation": recommendation,
            "model_overall_score": parsed.overall_score,
            "model_recommendation": parsed.recommendation,
            "parse_error": None,
        }
        state.scores["quick_screen"] = score

        logger.info(
            "[%s] quick_screen complete: %d/100 → %s (structured=%s)",
            state.ticker, score, recommendation, structured is not None,
        )
        state.status = "in_progress"

    except Exception as e:
        logger.exception("[%s] quick_screen failed", state.ticker)
        # Stored state is served by /api/runs — redacted message only; the
        # traceback stays in the server log.
        state.phase_outputs["quick_screen"] = {
            "__type__": "PhaseError",
            "reason": redact_secrets(str(e)),
        }
        state.status = "error"

    return state


# ── Phase 3: deep_dive (parallel subgraph) ────────────────────────────────────

async def warm_then_fan_out(run, items: list) -> list:
    """Run `run(item)` for every item in parallel, except that the first call
    goes alone until its response begins (it gets an Event to set) or it
    finishes. The calls share a cached prompt prefix, and a parallel request
    can't read a cache entry another request is still writing — so without
    this, every call pays the cache write and none reads it."""
    if not items:
        return []
    warmed = asyncio.Event()
    first = asyncio.create_task(run(items[0], warmed))
    waiter = asyncio.create_task(warmed.wait())
    await asyncio.wait({first, waiter}, return_when=asyncio.FIRST_COMPLETED)
    waiter.cancel()
    rest = await asyncio.gather(*(run(item) for item in items[1:]))
    return [await first, *rest]


async def _run_one_category(
    category: str,
    ticker: str,
    theme: str,
    data: str,
    loop_context: str,
    transcript_context: str = "",
    macro_context: str = "",
    technical_context: str = "",
    sentiment_context: str = "",
    edgar_context: str = "",
    filing_excerpts_context: str = "",
    counterparty_context_text: str = "",
    quant_context: str = "",
    prior_questions_text: str = "",
    first_event: asyncio.Event | None = None,
) -> CategoryResult | CategoryError:
    """Run a single deep-dive category with a timeout."""
    try:
        parsed = await asyncio.wait_for(
            complete_structured(
                system=DEEP_DIVE_SYSTEM.format(),
                shared_prefix=DEEP_DIVE_SHARED.format(ticker=ticker, theme=theme, as_of=_as_of(), data=data),
                first_event=first_event,
                user=DEEP_DIVE_USER.format(
                    category=category,
                    transcript_data=transcript_context,
                    macro_data=macro_context,
                    technical_data=technical_context,
                    sentiment_data=sentiment_context,
                    edgar_data=edgar_context,
                    filing_excerpts=filing_excerpts_context,
                    counterparty_context=counterparty_context_text,
                    quant_data=quant_context,
                    prior_questions=prior_questions_text,
                    loop_context=loop_context,
                ),
                output_model=DeepDiveCategoryOutput,
                model=DEEP_MODEL,
                max_tokens=3000,
            ),
            timeout=CATEGORY_TIMEOUT,
        )
        # Failures (truncation, refusal, validation) land in the except below
        # as a CategoryError — the old regex fallback invented a score.
        return CategoryResult(
            category=category, content=parsed.model_dump_json(), score=parsed.score,
            key_findings=[f.finding for f in parsed.key_findings],
            structured=parsed.model_dump(),
        )

    except asyncio.TimeoutError:
        logger.warning("[%s] Category '%s' timed out after %ds", ticker, category, CATEGORY_TIMEOUT)
        return CategoryError(category=category, reason=f"Timeout after {CATEGORY_TIMEOUT}s")
    except Exception as e:
        logger.exception("[%s] Category '%s' failed", ticker, category)
        return CategoryError(category=category, reason=redact_secrets(str(e)))


async def node_deep_dive(
    state: ResearchState,
    fmp: FMPClient,
    fred: FREDClient | None = None,
    signals: dict | None = None,
    edgar_facts: dict | None = None,
    filing_sections: dict | None = None,
    counterparty_context=None,  # CounterpartyContext | None — typed loosely to avoid import cycle risk
) -> ResearchState:
    """Phase 3: run all 9 categories in parallel. Partial success is OK.

    `signals` is an optional dict of {signal_type: value} pre-fetched by the
    caller (typically PipelineService) from the signals table, used to route
    X sentiment/velocity data into the Sentiment & Narrative prompt.

    `edgar_facts` is an optional {concept: [fact_dict, ...]} dict of XBRL
    facts pre-fetched by the caller from the xbrl_facts table, used to
    route filings data (RPO, debt maturity, credit metrics) into the
    relevant category prompts. Customer concentration is NOT routed here
    — the SEC `companyfacts` endpoint only returns un-dimensioned parent
    facts and `ConcentrationRiskPercentage1` is always disclosed with
    axes (`CustomerAxis`, `ProductAxis`), so structured concentration
    intel arrives via Phase B narrative extraction (`Relationship`
    rows with `unnamed=true`).

    `filing_sections` is an optional {section_key: {text, heading, form_type,
    filing_date, accession_number}} dict pre-fetched from filing_sections
    (Phase A narrative sections). When present, excerpts are routed into
    Business Quality, Risk Assessment, Growth & Earnings, Management &
    Governance, and Future Durability per FILING_EXCERPT_ROUTING.

    `counterparty_context` is an optional CounterpartyContext pre-fetched
    from the relationships table. When present, the outbound + inbound
    counterparty graph is routed into Business Quality, Risk Assessment,
    and Future Durability prompts per RELATIONSHIP_ROUTING. Rendered as
    a structured anchor list — the prompt instructs the LLM to cite
    these entities by name rather than re-quoting filing text.
    """
    logger.info("[%s] deep_dive starting (loop %d)", state.ticker, state.loop_count)
    state.phase = "deep_dive"

    # Which categories to run (all on first pass, only flagged on loop-back)
    if state.loop_context and state.loop_context.get("categories"):
        categories_to_run = state.loop_context["categories"]
        logger.info("[%s] Loop-back: re-running %s", state.ticker, categories_to_run)
    else:
        categories_to_run = DEEP_DIVE_CATEGORIES

    # Fetch fresh fundamentals for the data payload
    try:
        from datetime import date, timedelta
        today = date.today()
        one_year_ago = (today - timedelta(days=365)).isoformat()
        today_str = today.isoformat()

        (income, income_cit), (balance, balance_cit), (cashflow, cashflow_cit), (profile, profile_cit), (dcf, dcf_cit), (estimates, estimates_cit), (hist_prices, hist_cit), (transcripts, transcript_cit), (key_metrics, km_cit), (ratios_ttm, ratios_cit), (fin_growth, growth_cit) = (
            await asyncio.gather(
                fmp.get_income_statement(state.ticker, period="quarter", limit=8),
                fmp.get_balance_sheet(state.ticker, period="quarter", limit=8),
                fmp.get_cash_flow(state.ticker, period="quarter", limit=8),
                fmp.get_company_profile(state.ticker),
                fmp.get_dcf(state.ticker),
                fmp.get_analyst_estimates(state.ticker, period="quarter", limit=8),
                fmp.get_historical_price(state.ticker, one_year_ago, today_str),
                fetch_recent_transcripts(fmp, state.ticker, limit=TRANSCRIPT_QUARTER_LIMIT),
                fmp.get_key_metrics_ttm(state.ticker),
                fmp.get_ratios_ttm(state.ticker),
                fmp.get_financial_growth(state.ticker, period="quarter", limit=8),
            )
        )

        # Persist the FMP citations alongside the data (previously discarded).
        # transcript_cit is handled separately below, gated on transcript
        # analysis succeeding. Note: a risk-loop re-run of this node appends
        # again — same convention as the FRED/transcript citations.
        for _cit in (income_cit, balance_cit, cashflow_cit, profile_cit, dcf_cit,
                     estimates_cit, hist_cit, km_cit, ratios_cit, growth_cit):
            if _cit is not None:
                state.add_citation(StateCitation.from_citation(_cit))

        # Tier 2 secondary fetch: analyst ratings + price targets + insider Form 4s.
        # Each call degrades independently via return_exceptions — a single 404
        # or rate-limit doesn't collapse the whole set. _unwrap is imported
        # from deep_dive_helpers (lifted out for unit-test reach).
        secondary = await asyncio.gather(
            fmp.get_analyst_grades_consensus(state.ticker),
            fmp.get_price_target_consensus(state.ticker),
            fmp.get_ratings_snapshot(state.ticker),
            fmp.get_analyst_grades(state.ticker, limit=10),
            fmp.get_analyst_grades_historical(state.ticker, limit=6),
            fmp.get_insider_trading(state.ticker, limit=20),
            _fetch_institutional(fmp, state.ticker),
            return_exceptions=True,
        )
        grade_consensus = _unwrap(secondary[0], {}) or {}
        price_target = _unwrap(secondary[1], {}) or {}
        ratings_snap = _unwrap(secondary[2], {}) or {}
        grades_recent = _unwrap(secondary[3], []) or []
        grades_hist = _unwrap(secondary[4], []) or []
        insider_tx = _unwrap(secondary[5], []) or []
        # _fetch_institutional returns ((summary, holders), [citations]) — not a
        # (data, citation) pair, so unwrap manually; exceptions degrade to empty.
        _inst_slot = secondary[6]
        if isinstance(_inst_slot, BaseException):
            inst_summary, inst_holders = None, []
            _inst_citations: list = []
        else:
            (inst_summary, inst_holders), _inst_citations = _inst_slot

        # Persist tier-2 citations: the first 6 slots are standard (data, cit) pairs
        for _slot in secondary[:6]:
            _t2_cit = unwrap_gather_citation(_slot)
            if _t2_cit is not None:
                state.add_citation(StateCitation.from_citation(_t2_cit))
        # Persist institutional citations (list, not a single Citation)
        for _cit in _inst_citations:
            if _cit is not None:
                state.add_citation(StateCitation.from_citation(_cit))

        data_text = _fmt_fundamentals(
            state.ticker,
            income if isinstance(income, list) else [],
            balance if isinstance(balance, list) else [],
            cashflow if isinstance(cashflow, list) else [],
            profile[0] if isinstance(profile, list) and profile else profile or {},
            dcf=dcf if isinstance(dcf, dict) else None,
            estimates=estimates if isinstance(estimates, list) else [],
            key_metrics=key_metrics if isinstance(key_metrics, dict) else None,
            ratios=ratios_ttm if isinstance(ratios_ttm, dict) else None,
            fin_growth=fin_growth if isinstance(fin_growth, list) else [],
            grade_consensus=grade_consensus if isinstance(grade_consensus, dict) else {},
            price_target=price_target if isinstance(price_target, dict) else {},
            ratings_snap=ratings_snap if isinstance(ratings_snap, dict) else {},
            grades_recent=grades_recent if isinstance(grades_recent, list) else [],
            grades_hist=grades_hist if isinstance(grades_hist, list) else [],
            insider_tx=insider_tx if isinstance(insider_tx, list) else [],
            inst_summary=inst_summary if isinstance(inst_summary, dict) else None,
            inst_holders=inst_holders if isinstance(inst_holders, list) else [],
        )

        # Build curated financials for frontend dashboard
        prof = profile[0] if isinstance(profile, list) and profile else profile or {}
        curated = _build_curated_financials(
            ticker=state.ticker,
            income=income if isinstance(income, list) else [],
            balance=balance if isinstance(balance, list) else [],
            cashflow=cashflow if isinstance(cashflow, list) else [],
            profile=prof,
            dcf=dcf if isinstance(dcf, dict) else None,
            estimates=estimates if isinstance(estimates, list) else [],
            key_metrics=key_metrics if isinstance(key_metrics, dict) else None,
            ratios=ratios_ttm if isinstance(ratios_ttm, dict) else None,
        )
        curated.daily_prices = _build_technical_data(
            hist_prices if isinstance(hist_prices, list) else []
        )
        state.curated_financials = curated.to_dict()

        # Run transcript analysis (6 passes). A loop-back re-runs a few
        # categories against the same transcripts, so reuse the first result.
        if state.loop_count > 0 and state.transcript_analysis is not None:
            logger.info("[%s] Reusing transcript analysis from the first pass", state.ticker)
        elif transcripts and isinstance(transcripts, list) and len(transcripts) > 0:
            logger.info("[%s] Running transcript analysis (%d transcripts)", state.ticker, len(transcripts))
            ta_result = await run_transcript_analysis(state.ticker, transcripts, fmp)
            if ta_result.status == "ok":
                state.transcript_analysis = ta_result.value
                if transcript_cit is not None:
                    state.add_citation(StateCitation.from_citation(transcript_cit))
            elif ta_result.status == "error":
                logger.warning("[%s] Transcript analysis failed: %s", state.ticker, ta_result.error)
                state.transcript_analysis = None
            else:  # status == "no_data" — unreachable from this guarded call site; kept for exhaustiveness
                state.transcript_analysis = None
        else:
            logger.info("[%s] No transcripts available, skipping analysis", state.ticker)
            state.transcript_analysis = None

        # Fetch FRED macro indicators
        if fred and fred.available:
            try:
                macro_data, macro_citations = await fred.get_all_macro()
                curated_dict = state.curated_financials or {}
                curated_dict["macro_indicators"] = macro_data
                state.curated_financials = curated_dict
                for cit in macro_citations:
                    state.add_citation(StateCitation.from_citation(cit))
                logger.info("[%s] FRED macro data fetched (%d series)", state.ticker, len(macro_data))
            except Exception as e:
                logger.warning("[%s] FRED fetch failed, skipping macro data: %s", state.ticker, e)
        else:
            logger.info("[%s] FRED client not available, skipping macro data", state.ticker)

    except Exception as e:
        logger.warning("[%s] Data fetch failed, proceeding with partial data: %s", state.ticker, e)
        data_text = f"Note: data fetch partially failed ({e}). Analyze based on available information."
        state.curated_financials = None
        state.transcript_analysis = None

    loop_ctx_str = ""
    if state.loop_context:
        loop_ctx_str = f"\n\nNOTE: This is a loop-back run (attempt {state.loop_count}/2). Focus particularly on: {state.loop_context.get('reason', '')}"

    # Per-category context builders live in deep_dive_context; the seven
    # nested closures that used to be here were a hidden dependency surface
    # on state/signals/edgar_facts/filing_sections/counterparty_context.
    # Build the dataclass AFTER the FRED block above — that block mutates
    # state.curated_financials which two of the builders read.
    deep_dive_ctx = DeepDiveContext(
        ticker=state.ticker,
        categories=categories_to_run,
        transcript_analysis=state.transcript_analysis,
        curated_financials=state.curated_financials,
        signals=signals,
        edgar_facts=edgar_facts,
        filing_sections=filing_sections,
        counterparty_context=counterparty_context,
    )
    category_contexts = build_all_contexts(deep_dive_ctx)

    def _build_targeted_context_for_category(category: str) -> str:
        parts = [f"Fundamental data:\n{data_text}"]
        ctx = category_contexts.get(category, {})
        for label, text in [
            ("Transcript context", ctx.get("transcript", "")),
            ("Macro context", ctx.get("macro", "")),
            ("Technical context", ctx.get("technical", "")),
            ("Sentiment context", ctx.get("sentiment", "")),
            ("EDGAR XBRL context", ctx.get("edgar", "")),
            ("Filing excerpt context", ctx.get("filing", "")),
            ("Counterparty context", ctx.get("counterparty", "")),
            ("Quant context", ctx.get("quant", "")),
        ]:
            if text:
                parts.append(f"{label}:\n{text}")
        return "\n\n".join(parts)[:TARGETED_FOLLOWUP_CONTEXT_BUDGET_CHARS]

    # Fetch prior open questions for each category (cross-run resurfacing)
    prior_q_lists = await asyncio.gather(
        *[_fetch_prior_open_questions(state.ticker, cat) for cat in categories_to_run],
        return_exceptions=True,
    )
    prior_q_map: dict[str, list[dict]] = {}
    for cat, pq in zip(categories_to_run, prior_q_lists):
        prior_q_map[cat] = pq if isinstance(pq, list) else []

    def run(cat: str, first_event: asyncio.Event | None = None):
        return _run_one_category(
            cat, state.ticker, _theme_context(state), data_text, loop_ctx_str,
            category_contexts[cat]["transcript"], category_contexts[cat]["macro"],
            category_contexts[cat]["technical"], category_contexts[cat]["sentiment"],
            category_contexts[cat]["edgar"],
            category_contexts[cat]["filing"],
            category_contexts[cat]["counterparty"],
            category_contexts[cat]["quant"],
            _render_prior_questions_slot(prior_q_map[cat]),
            first_event=first_event,
        )

    results = await warm_then_fan_out(run, categories_to_run)

    for result in results:
        state.set_category_result(result)

    failed = state.failed_categories()
    succeeded = len(results) - len(failed)
    logger.info("[%s] deep_dive complete: %d/%d succeeded, failed: %s",
                state.ticker, succeeded, len(results), failed)

    # Tier 1.2 — stage extracted questions for DB persistence
    question_categories: set[str] = set()
    for result in results:
        if not isinstance(result, CategoryResult):
            continue
        structured = result.structured or {}
        for raw_q in structured.get("questions", []) or []:
            question_categories.add(result.category)
            state.questions_extracted.append(StateQuestion(
                category=result.category,
                question_text=raw_q["question_text"],
                priority=int(raw_q["priority"]),
                auto_answerable=bool(raw_q["auto_answerable"]),
            ).to_dict())
        for raw_rq in structured.get("resolved_questions", []) or []:
            qid = raw_rq.get("question_id")
            # Look up original question text from this category's prior set
            original_text = qid  # fallback to the id if lookup fails
            for prior_entry in prior_q_map.get(result.category, []) or []:
                if prior_entry.get("id") == qid:
                    original_text = prior_entry.get("question_text") or qid
                    break
            state.questions_resolved_this_run.append(StateResolvedQuestion(
                question_text=original_text,
                answer_text=raw_rq["answer_text"],
                source="deep_dive_resurfaced",
            ).to_dict())

    state.targeted_followup_context = {
        cat: _build_targeted_context_for_category(cat)
        for cat in sorted(question_categories)
    }

    await _persist_extracted_questions(state)
    await _apply_resurfaced_resolutions(state)

    state.status = "in_progress"
    return state


# ── Tier 1.2 targeted followup ────────────────────────────────────────────────

def _build_targeted_followup_user_msg(
    *,
    question_text: str,
    category: str,
    key_findings: list[str],
    analysis: str,
    routed_context: str = "",
) -> str:
    findings_block = "\n".join(f"- {f}" for f in key_findings or []) or "(none)"
    parts = [
        f"Question: {question_text}",
        f"Originating category: {category}",
        f"Key findings from that category's deep-dive:\n{findings_block}",
        f"Full category analysis:\n{analysis}",
    ]
    if routed_context:
        parts.append(f"Original data payload and routed context:\n{routed_context}")
    return "\n\n".join(parts)


# ── Phase 4: thesis_construction ─────────────────────────────────────────────

async def node_thesis_construction(state: ResearchState, fmp: FMPClient | None = None) -> ResearchState:
    """Phase 4: synthesise all Phase 3 outputs into a structured thesis."""
    logger.info("[%s] thesis_construction starting", state.ticker)
    state.phase = "thesis_construction"

    # Format category results
    results = state.get_deep_dive_results()

    # Build concise summary (scores + top 2 findings per category)
    summary_lines = []
    results_text = ""
    for cat, result in results.items():
        if isinstance(result, CategoryResult):
            top_findings = "; ".join(result.key_findings[:2]) if result.key_findings else "No key findings"
            summary_lines.append(f"- {cat}: {result.score}/100 — {top_findings}")
            results_text += f"\n\n## {cat} (Score: {result.score}/100)\n{_category_analysis_text(result)}"
        else:
            summary_lines.append(f"- {cat}: FAILED — {result.reason}")
            results_text += f"\n\n## {cat}\n[FAILED: {result.reason}]"

    category_summary = "\n".join(summary_lines)

    # Extract quick screen context
    qs_output = state.phase_outputs.get("quick_screen", {})
    qs_structured = qs_output.get("structured") if isinstance(qs_output, dict) else None
    qs_verdict = "N/A"
    qs_score = qs_output.get("score", "N/A") if isinstance(qs_output, dict) else "N/A"
    qs_thesis = "N/A"
    qs_risk = "N/A"
    if qs_structured and isinstance(qs_structured, dict):
        qs_verdict = qs_structured.get("recommendation", "N/A")
        qs_thesis = qs_structured.get("thesis", "N/A")
        qs_risk = qs_structured.get("key_risk", "N/A")

    failed = state.failed_categories()
    loop_ctx = str(state.loop_context) if state.loop_context else "None"

    try:
        parsed = await complete_structured(
            system=THESIS_SYSTEM,
            user=THESIS_USER.format(
                ticker=state.ticker,
                theme=_theme_context(state),
                as_of=_as_of(),
                market_data=_market_data_block(state),
                quick_screen_verdict=qs_verdict,
                quick_screen_score=qs_score,
                quick_screen_thesis=qs_thesis,
                quick_screen_risk=qs_risk,
                category_summary=category_summary,
                category_results=results_text,
                failed_categories=", ".join(failed) if failed else "None",
                loop_context=loop_ctx,
                questions_resolved=_render_questions_resolved(state.questions_resolved_this_run),
            ),
            output_model=ThesisLLMOutput,
            model=DEEP_MODEL,
            max_tokens=6000,
        )
        # A failed or truncated thesis raises into the except below — no
        # regex fallback that invents a conviction score (it recorded 50 for
        # a model-stated 68 on CORZ).
        conviction = parsed.conviction_score
        structured = parsed.model_dump()

        state.phase_outputs["thesis"] = {
            "__type__": "PhaseOutput",
            "content": parsed.model_dump_json(),
            "structured": structured,
            "conviction_score": conviction,
            "stance": parsed.stance,
            "parse_error": None,
        }
        state.conviction_score = conviction
        state.thesis_status = "ON TRACK"
        state.scores["thesis"] = conviction

        # Tier 1.3: promote parsed catalysts into first-class DB rows.
        # Failure here is non-fatal — JSONB still has the canonical copy.
        try:
            client = fmp or FMPClient()  # the pipeline passes its shared client
            try:
                async with unit_of_work() as cat_db:
                    await promote_catalysts(state, parsed, client, cat_db)
            finally:
                if fmp is None:
                    await client.close()
        except Exception as cat_err:
            logger.warning(
                "[%s] catalyst promotion failed: %s", state.ticker, cat_err
            )

        logger.info(
            "[%s] thesis complete: %s, conviction %d/100",
            state.ticker, parsed.stance, conviction,
        )
        state.status = "in_progress"

    except Exception as e:
        logger.error("[%s] thesis_construction failed: %s", state.ticker, e)
        state.phase_outputs["thesis"] = {"__type__": "PhaseError", "reason": str(e)}
        state.status = "error"

    return state


# ── Phase 5: risk_stress_test ─────────────────────────────────────────────────

async def node_risk_stress_test(state: ResearchState) -> ResearchState:
    """Phase 5: stress-test the thesis. Returns loop decision in state."""
    logger.info("[%s] risk_stress_test starting (loop %d)", state.ticker, state.loop_count)
    state.phase = "risk_stress_test"

    thesis_output = state.phase_outputs.get("thesis", {})
    thesis_text = thesis_output.get("content", "No thesis available") if isinstance(thesis_output, dict) else ""

    scores_text = "\n".join(f"  {k}: {v}/100" for k, v in state.scores.items())

    try:
        thesis_struct = thesis_output.get("structured") if isinstance(thesis_output, dict) else None
        thesis_struct = thesis_struct or {}
        price = (state.curated_financials or {}).get("current_price")
        computed_rr = reward_risk(thesis_struct.get("stance"), price, thesis_struct.get("price_targets"))

        parsed = await complete_structured(
            system=RISK_SYSTEM,
            user=RISK_USER.format(
                ticker=state.ticker,
                theme=_theme_context(state),
                as_of=_as_of(),
                loop_count=state.loop_count,
                market_data=_market_data_block(state),
                reward_risk=_reward_risk_line(thesis_struct, computed_rr),
                # Full thesis: bear case, catalysts and kill criteria sit past
                # the first ~2.5K chars, and the stress test must see them.
                thesis=thesis_text,
                scores=scores_text,
            ),
            output_model=RiskStressTestOutput,
            model=DEEP_MODEL,
            max_tokens=3000,
        )

        # Reward/risk comes from the thesis's own targets when it can be
        # computed; the model's estimate is kept for comparison only.
        rr_ratio = computed_rr if computed_rr is not None else parsed.rr_ratio
        loop_cats = [c for c in parsed.loop_categories if c in DEEP_DIVE_CATEGORIES]
        loop = should_loop(
            model_wants_loop=parsed.loop_required, categories=loop_cats,
            loop_count=state.loop_count, rr=rr_ratio,
        )
        structured = parsed.model_dump()

        state.phase_outputs["risk"] = {
            "__type__": "PhaseOutput",
            "content": parsed.model_dump_json(),
            "structured": structured,
            "rr_ratio": rr_ratio,
            "rr_source": "thesis_targets" if computed_rr is not None else "model_estimate",
            "model_rr_ratio": parsed.rr_ratio,
            "loop_required": loop,
            "loop_categories": loop_cats,
            "loop_reason": parsed.loop_reason,
            "parse_error": None,
        }

        if loop:
            state.loop_count += 1
            state.loop_context = {
                "categories": loop_cats,
                "reason": parsed.loop_reason,
                "rr_ratio": rr_ratio,
            }
            # Auto-advance back to deep_dive; _next_phase() routes
            # back when loop_context is set.
            state.status = "in_progress"
            logger.info("[%s] Loop-back triggered (count %d): %s", state.ticker, state.loop_count, loop_cats)
        elif parsed.loop_required and loop_cats and state.loop_count >= MAX_RISK_LOOPS:
            # Gaps the model still wants investigated after the loop cap:
            # finish the run, but flag it rather than calling it on track.
            state.status = "watchlist"
            state.thesis_status = "DRIFTING"
            logger.info("[%s] Loop cap reached with open gaps — WATCHLIST", state.ticker)
        else:
            state.status = "completed"
            logger.info(
                "[%s] risk_stress_test complete: R/R %s (%s)",
                state.ticker, rr_ratio, state.phase_outputs["risk"]["rr_source"],
            )

    except Exception as e:
        logger.error("[%s] risk_stress_test failed: %s", state.ticker, e)
        state.phase_outputs["risk"] = {"__type__": "PhaseError", "reason": str(e)}
        state.status = "error"

    return state


# ── Phase 6: position_monitor ─────────────────────────────────────────────────

async def node_position_monitor(state: ResearchState) -> ResearchState:
    """Phase 6: generate entry zones, sizing, stops, and monitoring cadence."""
    logger.info("[%s] position_monitor starting", state.ticker)
    state.phase = "position_monitor"

    thesis_output = state.phase_outputs.get("thesis", {})
    thesis_text = thesis_output.get("content", "") if isinstance(thesis_output, dict) else ""

    risk_output = state.phase_outputs.get("risk", {})
    risk_text = risk_output.get("content", "") if isinstance(risk_output, dict) else ""

    try:
        parsed = await complete_structured(
            system=POSITION_SYSTEM,
            user=POSITION_USER.format(
                ticker=state.ticker,
                as_of=_as_of(),
                market_data=_market_data_block(state),
                conviction_score=state.conviction_score,
                thesis_status=state.thesis_status,
                thesis_summary=thesis_text,
                risk_summary=risk_text,
            ),
            output_model=PositionMonitorOutput,
            model=FAST_MODEL,
            max_tokens=2000,
        )

        state.phase_outputs["position"] = {
            "__type__": "PhaseOutput",
            "content": parsed.model_dump_json(),
            "structured": parsed.model_dump(),
            "parse_error": None,
        }
        state.status = "completed"
        state.phase = "completed"
        logger.info("[%s] position_monitor complete — run finished", state.ticker)

    except Exception as e:
        logger.exception("[%s] position_monitor failed", state.ticker)
        state.phase_outputs["position"] = {"__type__": "PhaseError", "reason": redact_secrets(str(e))}
        state.status = "completed"
        state.phase = "completed"

    return state

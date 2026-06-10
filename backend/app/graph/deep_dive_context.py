"""Per-category context builders for `node_deep_dive`.

Each builder is a pure function over a `DeepDiveContext` snapshot plus a
category name, returning the formatted prompt slot for that category.
The empty-string-when-no-data convention is preserved — empty slots drop
out cleanly in `DEEP_DIVE_USER`.

Lifted from inside `node_deep_dive` so they can be exercised on JSON
fixtures in unit tests rather than only as a side-effect of running the
full deep-dive node. Behaviour-identical to the originals at the time
of the lift; verified via byte-equality snapshot diff on ORCL.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from backend.app.graph.deep_dive_helpers import format_fact_value
from backend.app.graph.deep_dive_routing import (
    EDGAR_ROUTING,
    FILING_EXCERPT_BUDGET_CHARS,
    FILING_EXCERPT_ROUTING,
    MACRO_ROUTING,
    QUANT_ROUTING,
    RELATIONSHIP_ROUTING,
    TRANSCRIPT_ROUTING,
)
from backend.app.services.relationship_context import CounterpartyContext


@dataclass(frozen=True)
class DeepDiveContext:
    """Frozen bundle of every input the per-category builders need.

    Built once per `node_deep_dive` invocation, after all data fetches
    resolve (notably after the FRED block which mutates
    `state.curated_financials`).
    """

    ticker: str
    categories: list[str]
    transcript_analysis: dict | str | None
    curated_financials: dict | None  # holds macro_indicators + daily_prices
    signals: dict | None
    edgar_facts: dict | None
    filing_sections: dict | None
    counterparty_context: CounterpartyContext | None


# ── Builders ────────────────────────────────────────────────────────────────


def build_transcript_context(ctx: DeepDiveContext, category: str) -> str:
    if not ctx.transcript_analysis or isinstance(ctx.transcript_analysis, str):
        return ""
    passes = TRANSCRIPT_ROUTING.get(category)
    if not passes:
        return ""
    sections = []
    for pass_key in passes:
        val = ctx.transcript_analysis.get(pass_key)
        if val is not None and not isinstance(val, str):
            sections.append(f"[Transcript: {pass_key}]\n{json.dumps(val, indent=2)}")
    if not sections:
        return ""
    return "Earnings transcript analysis:\n" + "\n\n".join(sections)


def build_macro_context(ctx: DeepDiveContext, category: str) -> str:
    macro = (ctx.curated_financials or {}).get("macro_indicators")
    if not macro or not isinstance(macro, dict):
        return ""
    series_keys = MACRO_ROUTING.get(category)
    if not series_keys:
        return ""
    sections = []
    for key in series_keys:
        points = macro.get(key)
        if points and isinstance(points, list) and len(points) > 0:
            latest = points[-1]
            recent = points[-6:] if len(points) >= 6 else points
            trend_str = ", ".join(f"{p['date']}: {p['value']}" for p in recent)
            sections.append(f"{key}: latest={latest['value']} ({latest['date']}), trend=[{trend_str}]")
    if not sections:
        return ""
    return "Macro economic indicators (FRED):\n" + "\n".join(sections)


def build_technical_context(ctx: DeepDiveContext, category: str) -> str:
    if category != "Technical & Market Structure":
        return ""
    prices = (ctx.curated_financials or {}).get("daily_prices")
    if not prices or not isinstance(prices, list) or len(prices) == 0:
        return ""
    # Latest 20 sessions, newest last (chronological already)
    recent = prices[-20:]
    lines = ["date | close | volume | sma_9 | sma_20 | sma_50 | sma_200 | rsi"]
    for p in recent:
        lines.append(
            f"{p.get('date')} | {p.get('close')} | {p.get('volume')} | "
            f"{p.get('sma_9')} | {p.get('sma_20')} | {p.get('sma_50')} | "
            f"{p.get('sma_200')} | {p.get('rsi')}"
        )
    latest = prices[-1]
    summary = (
        f"Latest close: {latest.get('close')} | "
        f"RSI(14): {latest.get('rsi')} | "
        f"SMA50: {latest.get('sma_50')} | SMA200: {latest.get('sma_200')}"
    )
    return (
        "Technical indicators (computed from 1Y daily OHLCV):\n"
        f"{summary}\n\nLast 20 sessions:\n" + "\n".join(lines)
    )


def build_sentiment_context(ctx: DeepDiveContext, category: str) -> str:
    if category != "Sentiment & Narrative":
        return ""
    if not ctx.signals:
        return ""
    parts = ["X social signal (Tier 2, directional only):"]
    vel = ctx.signals.get("velocity")
    if isinstance(vel, dict):
        parts.append(
            f"Velocity: ratio={vel.get('ratio')} direction={vel.get('direction')} "
            f"count_7d={vel.get('count_7d')} count_30d_approx={vel.get('count_30d_approx')}"
        )
    narr = ctx.signals.get("narrative")
    if isinstance(narr, dict):
        parts.append(f"Narrative: post_count={narr.get('post_count')} summary={narr.get('summary') or 'N/A'}")
    disc = ctx.signals.get("discovery")
    if isinstance(disc, dict):
        parts.append(
            f"Discovery: score={disc.get('score')} co_mentions_7d={disc.get('co_mentions_7d')} "
            f"total_theme_mentions_7d={disc.get('total_theme_mentions_7d')}"
        )
    if len(parts) == 1:
        return ""
    return "\n".join(parts)


def build_edgar_context(ctx: DeepDiveContext, category: str) -> str:
    concepts = EDGAR_ROUTING.get(category)
    if not concepts:
        return ""
    present_lines: list[str] = []
    missing: list[str] = []
    facts = ctx.edgar_facts or {}
    for concept in concepts:
        entries = facts.get(concept)
        short = concept.split(":", 1)[-1]
        if not entries:
            missing.append(short)
            continue
        # Most recent first, show up to 4
        for e in entries[:4]:
            present_lines.append(
                f"  {short} [{e.get('fiscal_year')} {e.get('fiscal_period') or ''}] "
                f"{e.get('period_start')} → {e.get('period_end')}: "
                f"{format_fact_value(e['value'], e.get('unit') or '')}"
            )
    if not present_lines and not missing:
        return ""
    sections = ["SEC EDGAR XBRL facts (Tier 1, authoritative from 10-K/10-Q filings):"]
    if present_lines:
        sections.append("\n".join(present_lines))
    if missing:
        sections.append("Not disclosed in XBRL: " + ", ".join(missing))
    return "\n".join(sections)


def build_filing_excerpt_context(ctx: DeepDiveContext, category: str) -> str:
    section_keys = FILING_EXCERPT_ROUTING.get(category)
    if not section_keys:
        return ""
    sections = ctx.filing_sections or {}
    blocks: list[str] = []
    for key in section_keys:
        payload = sections.get(key)
        if not payload:
            continue
        text = (payload.get("text") or "")[:FILING_EXCERPT_BUDGET_CHARS]
        if not text:
            continue
        truncated = len(payload.get("text") or "") > FILING_EXCERPT_BUDGET_CHARS
        header = (
            f"[{payload.get('form_type', '?')} · {payload.get('filing_date', '?')} · "
            f"{payload.get('heading') or key}]"
        )
        if truncated:
            header += f" (truncated to {FILING_EXCERPT_BUDGET_CHARS} chars)"
        blocks.append(f"{header}\n{text}")
    if not blocks:
        return ""
    return (
        "SEC filing excerpts (Tier 1, verbatim narrative from latest 10-K / 10-Q / DEF 14A):\n"
        + "\n\n".join(blocks)
    )


def build_counterparty_context(ctx: DeepDiveContext, category: str) -> str:
    """Render the relationship graph payload for the deep-dive prompt.
    Returns '' when the category is not routed, or when we have no
    extracted relationships for this ticker."""
    if category not in RELATIONSHIP_ROUTING:
        return ""
    if not ctx.counterparty_context or not ctx.counterparty_context.has_data:
        return ""

    cp = ctx.counterparty_context  # alias for brevity

    lines: list[str] = [
        "RESOLVED COUNTERPARTIES",
        "(pre-extracted from the filing excerpts above; use these as anchors when",
        "referring to named customers, suppliers, or partners.",
        "For resolved entities, use the $TICKER notation exactly as shown below",
        "on first mention — do not refer to them by product/vendor name alone.",
        "Do NOT re-quote verbatim text from the filings for these entities.)",
        "",
    ]

    def _fmt_entry(e) -> str:
        # e: CounterpartyEntry
        label = f"${e.resolved_ticker} — {e.name}" if e.resolved_ticker else e.name
        parts = [label, e.relationship_type]
        if e.magnitude_pct is not None:
            parts.append(f"{e.magnitude_pct:.1f}%")
        return "    - " + " — ".join(parts)

    if cp.outbound:
        lines.append(f"Outbound — {ctx.ticker}'s disclosed relationships:")
        # Stable type order — show concentration-relevant buckets first.
        type_order = [
            "customer", "supplier", "partner", "joint_venture",
            "licensor", "licensee", "distributor", "reseller",
            "other",
        ]
        for t in type_order:
            entries = cp.outbound.get(t)
            if not entries:
                continue
            lines.append(f"  {t.replace('_', ' ').title()}s:")
            for e in entries:
                lines.append(_fmt_entry(e))
        lines.append("")

    if cp.inbound:
        lines.append(f"Mentioned by others — who named {ctx.ticker} in their own filings:")
        for t, entries in sorted(cp.inbound.items()):
            if not entries:
                continue
            lines.append(f"  As a {t.replace('_', ' ')} ({len(entries)} mention(s)):")
            for e in entries:
                # e.resolved_ticker is the author ticker here
                # Bucket header already states the relationship_type; don't repeat.
                lines.append(f"    - ${e.resolved_ticker}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


_QUANT_HEADER = (
    "Deterministic quant metrics (computed in pure Python from the FMP statements "
    "above — Tier 1, established facts. Do NOT recompute these; interpret them. "
    "Where a metric is null or marked not-applicable, treat it as a stated data "
    "gap, not a derivable value.)"
)


def _render_quant_metric(key: str, fp: dict) -> str:
    if key == "piotroski":
        p = fp.get("piotroski") or {}
        comps = p.get("components") or []
        if not comps:
            return ""
        marks = {True: "✓", False: "✗", None: "—"}
        detail = ", ".join(f"{marks[c.get('passed')]} {c.get('key')}" for c in comps)
        return (f"Piotroski F-score: {p.get('score')}/9 "
                f"({p.get('components_evaluated')} evaluated): {detail}")
    if key == "altman_z":
        a = fp.get("altman_z") or {}
        if a.get("not_applicable_reason"):
            return f"Altman Z: n/a — {a['not_applicable_reason']}"
        if a.get("z") is None:
            return "Altman Z: null (insufficient inputs)"
        return (f"Altman Z: {a['z']} ({a['zone']}; "
                ">2.99 safe, 1.81–2.99 grey, <1.81 distress)")
    if key == "beneish_m":
        b = fp.get("beneish_m") or {}
        if b.get("not_applicable_reason"):
            return f"Beneish M: n/a — {b['not_applicable_reason']}"
        if b.get("m") is None:
            missing = ", ".join(b.get("inputs_missing") or []) or "insufficient inputs"
            return f"Beneish M: null (missing: {missing})"
        ratios = b.get("ratios") or {}
        ratio_str = ", ".join(f"{k}={v}" for k, v in ratios.items() if v is not None)
        return (f"Beneish M: {b['m']} ({b['zone']}; >-1.78 flag, "
                f"-2.22..-1.78 caution, <-2.22 unlikely) [{ratio_str}]")
    if key == "accruals":
        v = fp.get("accruals_ratio")
        if v is None:
            return ""
        return (f"Accruals ratio ((NI−CFO)/avg TA, TTM): {v} "
                "(large positive ⇒ earnings outrunning cash)")
    if key == "fcf_conversion":
        v = fp.get("fcf_conversion")
        return "" if v is None else f"FCF conversion (FCF/NI, TTM): {v}"
    if key == "sbc":
        s = fp.get("sbc") or {}
        parts = []
        if s.get("sbc_pct_revenue") is not None:
            parts.append(f"SBC {s['sbc_pct_revenue']}% of revenue (TTM)")
        if s.get("share_growth_yoy_pct") is not None:
            parts.append(f"diluted shares {s['share_growth_yoy_pct']:+g}% YoY")
        return "; ".join(parts)
    if key == "margin_slopes":
        m = fp.get("margin_slopes") or {}
        parts = []
        for label in ("gross", "operating", "net"):
            entry = m.get(label) or {}
            slope = entry.get("slope_pp_per_quarter")
            if slope is not None:
                parts.append(f"{label} {slope:+g}pp/q over {entry.get('quarters')}q")
        return "Margin trend slopes (OLS): " + ", ".join(parts) if parts else ""
    return ""


def build_quant_context(ctx: DeepDiveContext, category: str) -> str:
    metric_keys = QUANT_ROUTING.get(category)
    if not metric_keys:
        return ""
    fp = (ctx.curated_financials or {}).get("quant_fingerprint")
    if not fp or not isinstance(fp, dict):
        return ""
    lines = [_QUANT_HEADER]
    for key in metric_keys:
        rendered = _render_quant_metric(key, fp)
        if rendered:
            lines.append(rendered)
    if len(lines) == 1:
        return ""
    return "\n".join(lines)


# ── Dispatcher ──────────────────────────────────────────────────────────────


def build_all_contexts(ctx: DeepDiveContext) -> dict[str, dict[str, str]]:
    """Materialise every context kind for every category in `ctx.categories`.

    Returned shape: `{category: {kind: text}}`. Empty strings preserved
    so the consuming prompt template's slot replacement drops them.
    """
    return {
        cat: {
            "transcript": build_transcript_context(ctx, cat),
            "macro": build_macro_context(ctx, cat),
            "technical": build_technical_context(ctx, cat),
            "sentiment": build_sentiment_context(ctx, cat),
            "edgar": build_edgar_context(ctx, cat),
            "filing": build_filing_excerpt_context(ctx, cat),
            "counterparty": build_counterparty_context(ctx, cat),
            "quant": build_quant_context(ctx, cat),
        }
        for cat in ctx.categories
    }

"""Data gap detection — pure functions over ResearchState JSONB dicts.

compute_data_gaps(state)  → list of gaps for a single run
aggregate_data_gaps(runs) → frequency-ranked gaps across runs
"""

from __future__ import annotations

# Deep-dive categories that should exist when deep_dive phase completes.
# Keys match the titles used in phase_outputs (not snake_case).
_DEEP_DIVE_CATEGORIES = [
    "Business Quality", "Financial Health", "Growth & Earnings",
    "Management & Governance", "Technical & Market Structure",
    "Macro & Regime", "Sentiment & Narrative", "Risk Assessment",
    "Future Durability",
]

# CuratedFinancials fields that indicate soft gaps when null/empty
_CURATED_FINANCIAL_GAPS: list[tuple[str, str]] = [
    ("dcf_intrinsic_value", "DCF valuation data unavailable"),
    ("dcf_gap_percent", "DCF gap percentage unavailable"),
    ("forward_revenue_estimates", "No forward revenue estimates (no analyst coverage)"),
    ("forward_eps_estimates", "No forward EPS estimates (no analyst coverage)"),
    ("daily_prices", "No daily price history available"),
    ("beta", "Beta unavailable"),
]


def _has_any_category_result(phase_outputs: dict) -> bool:
    """True if at least one deep-dive category produced a CategoryResult."""
    return any(
        isinstance(v, dict) and v.get("__type__") == "CategoryResult"
        for v in phase_outputs.values()
    )


# Known-stale error patterns from historic runs whose root cause has been
# fixed. Filtering these out prevents old runs from skewing hard-error
# aggregation. Leave the state JSONB intact so history is recoverable.
_STALE_HARD_ERROR_SUBSTRINGS = (
    "does not support assistant message prefill",  # fixed: see 0ccee3e / b26079e
)


def _is_stale_hard_error(reason: str | None) -> bool:
    if not reason:
        return False
    return any(s in reason for s in _STALE_HARD_ERROR_SUBSTRINGS)


def compute_data_gaps(state: dict) -> list[dict]:
    """Scan a single run's JSONB state and return all detected data gaps.

    Returns list of:
        {"gap_type": "hard_error"|"soft_gap", "category": str,
         "field": str|None, "description": str}
    """
    gaps: list[dict] = []
    phase_outputs = state.get("phase_outputs", {})

    # ── Hard errors: CategoryError entries ────────────────────────────
    for key, val in phase_outputs.items():
        if isinstance(val, dict) and val.get("__type__") == "CategoryError":
            reason = val.get("reason", "Category analysis failed")
            if _is_stale_hard_error(reason):
                continue  # skip historic errors whose root cause is fixed
            gaps.append({
                "gap_type": "hard_error",
                "category": key,
                "field": None,
                "description": reason,
            })

    # ── Soft gaps: CuratedFinancials null/empty fields ────────────────
    curated = state.get("curated_financials")
    deep_dive_ran = _has_any_category_result(phase_outputs)

    if curated and isinstance(curated, dict):
        for field_name, description in _CURATED_FINANCIAL_GAPS:
            value = curated.get(field_name)
            if value is None or (isinstance(value, list) and len(value) == 0):
                gaps.append({
                    "gap_type": "soft_gap",
                    "category": "curated_financials",
                    "field": field_name,
                    "description": description,
                })
        # FRED macro indicators — separate from the null-field list because
        # the field is a dict, not None, when unavailable.
        macro = curated.get("macro_indicators")
        if not macro or (isinstance(macro, dict) and len(macro) == 0):
            gaps.append({
                "gap_type": "soft_gap",
                "category": "curated_financials",
                "field": "macro_indicators",
                "description": "FRED macro indicators unavailable (rates, yield curve, unemployment, etc.)",
            })
    elif deep_dive_ran:
        # curated_financials is None but deep_dive ran anyway — full FMP
        # fundamentals fetch failed and the LLM analysed on partial context.
        gaps.append({
            "gap_type": "soft_gap",
            "category": "curated_financials",
            "field": None,
            "description": "FMP fundamentals fetch failed — deep-dive ran on partial data",
        })

    # ── Soft gap: earnings transcript unavailable ─────────────────────
    # Surfaces the silent-skip in node_deep_dive when FMP returns no transcripts
    # or the transcript fetch itself failed. 6 of 9 categories are routed
    # transcript context, so this is a material gap when it happens.
    if deep_dive_ran:
        transcript = state.get("transcript_analysis")
        transcript_missing = (
            transcript is None
            or (isinstance(transcript, dict) and transcript.get("error"))
        )
        if transcript_missing:
            gaps.append({
                "gap_type": "soft_gap",
                "category": "transcript_analysis",
                "field": None,
                "description": "Earnings transcript unavailable — transcript-routed categories ran without management commentary",
            })

    # ── Soft gaps: LLM-reported data_gaps from deep-dive categories ───
    for cat_key in _DEEP_DIVE_CATEGORIES:
        output = phase_outputs.get(cat_key)
        if not isinstance(output, dict) or output.get("__type__") != "CategoryResult":
            continue
        structured = output.get("structured")
        if not isinstance(structured, dict):
            continue
        for gap_desc in structured.get("data_gaps", []):
            if gap_desc:  # skip empty strings
                gaps.append({
                    "gap_type": "soft_gap",
                    "category": cat_key,
                    "field": "data_gaps",
                    "description": gap_desc,
                })

    return gaps


def aggregate_data_gaps(
    runs: list[tuple[str, dict]],
) -> dict:
    """Aggregate gaps across multiple runs.

    Args:
        runs: list of (ticker, state_dict) tuples

    Returns:
        {"total_runs_scanned": int, "gaps": [AggregatedGap...]}
    """
    from collections import defaultdict

    # Key: (gap_type, category, field, description) → {count, tickers}
    counter: dict[tuple, dict] = defaultdict(lambda: {"count": 0, "tickers": set()})

    for ticker, state in runs:
        for gap in compute_data_gaps(state):
            key = (gap["gap_type"], gap["category"], gap["field"], gap["description"])
            counter[key]["count"] += 1
            counter[key]["tickers"].add(ticker)

    total = len(runs)
    aggregated = []
    for (gap_type, category, field_name, description), info in counter.items():
        aggregated.append({
            "gap_type": gap_type,
            "category": category,
            "field": field_name,
            "description": description,
            "occurrences": info["count"],
            "frequency": round(info["count"] / total, 2) if total > 0 else 0,
            "example_tickers": sorted(info["tickers"])[:3],
        })

    aggregated.sort(key=lambda g: g["occurrences"], reverse=True)

    return {"total_runs_scanned": total, "gaps": aggregated}

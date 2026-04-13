"""Data gap detection — pure functions over ResearchState JSONB dicts.

compute_data_gaps(state)  → list of gaps for a single run
aggregate_data_gaps(runs) → frequency-ranked gaps across runs
"""

from __future__ import annotations

# Deep-dive categories that should exist when deep_dive phase completes
_DEEP_DIVE_CATEGORIES = [
    "business_quality", "financial_health", "growth_earnings",
    "management_governance", "technical_market_structure", "macro_regime",
    "sentiment_narrative", "risk_assessment", "future_durability",
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
            gaps.append({
                "gap_type": "hard_error",
                "category": key,
                "field": None,
                "description": val.get("reason", "Category analysis failed"),
            })

    # ── Soft gaps: CuratedFinancials null/empty fields ────────────────
    curated = state.get("curated_financials")
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

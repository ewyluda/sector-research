"""Per-category data routing for `node_deep_dive`.

Six parallel routing tables previously lived as module-level dicts inside
`graph/nodes.py`. They answer the same question — "which subset of source X
does category Y see?" — for six different sources (transcripts, macro,
EDGAR XBRL, filing excerpts, supply-chain relationships, quant fingerprint).

Consolidated here so:
  - Adding a new deep-dive category is a single `routing_for()` lookup,
    not a five-dict survey.
  - The per-category contract is grokable in one dataclass.
  - The tables themselves remain as the source of truth for routing
    decisions — re-exported for backward compat with existing call sites
    inside `node_deep_dive`'s context-builder closures.
"""
from __future__ import annotations

from dataclasses import dataclass, field


# ── Sub-registries ──────────────────────────────────────────────────────────

TRANSCRIPT_ROUTING: dict[str, list[str]] = {
    "Management & Governance": [
        "pass1_claims", "pass2_tiers", "pass3_qa_tensions",
        "pass4_validation", "pass5_consistency",
    ],
    "Business Quality": ["pass3_qa_tensions", "pass5_consistency"],
    "Growth & Earnings": ["pass1_claims", "pass4_validation", "pass6_bom"],
    "Sentiment & Narrative": ["pass3_qa_tensions", "pass5_consistency"],
    "Risk Assessment": ["pass1_claims", "pass4_validation"],
    "Future Durability": ["pass1_claims", "pass5_consistency"],
}

_ALL_MACRO = [
    "fed_funds_rate", "treasury_10y", "treasury_2y", "yield_curve_spread",
    "cpi", "unemployment", "gdp_growth", "m2_money_supply", "nonfarm_payrolls",
]

MACRO_ROUTING: dict[str, list[str]] = {
    "Macro & Regime": _ALL_MACRO,
    "Risk Assessment": _ALL_MACRO,
    "Future Durability": ["gdp_growth", "cpi", "m2_money_supply", "fed_funds_rate", "treasury_10y"],
    "Financial Health": ["fed_funds_rate", "treasury_10y", "yield_curve_spread"],
}

# EDGAR XBRL concept routing — when a routed concept has no facts in
# xbrl_facts, the prompt builder explicitly notes "not disclosed in XBRL"
# so the LLM distinguishes unrouted from unavailable.
_DEBT_MATURITY_CONCEPTS = [
    "us-gaap:LongTermDebtMaturitiesRepaymentsOfPrincipalInNextTwelveMonths",
    "us-gaap:LongTermDebtMaturitiesRepaymentsOfPrincipalInYearTwo",
    "us-gaap:LongTermDebtMaturitiesRepaymentsOfPrincipalInYearThree",
    "us-gaap:LongTermDebtMaturitiesRepaymentsOfPrincipalInYearFour",
    "us-gaap:LongTermDebtMaturitiesRepaymentsOfPrincipalInYearFive",
    "us-gaap:LongTermDebtMaturitiesRepaymentsOfPrincipalAfterYearFive",
]
_RPO_CONCEPTS = [
    "us-gaap:RevenueRemainingPerformanceObligation",
    "us-gaap:RevenueRemainingPerformanceObligationExpectedTimingOfSatisfactionPercentage",
]
# NOTE: customer concentration intentionally absent. The SEC
# `companyfacts` endpoint only exposes un-dimensioned parent facts and
# `ConcentrationRiskPercentage1` is always disclosed with axes
# (`CustomerAxis`, `ProductAxis`), so the API returns nothing for it.
# Structured concentration arrives via Phase B narrative extraction
# (`Relationship.unnamed=true` rows) and is rendered through the
# RELATIONSHIP_ROUTING path below.
_CREDIT_CONCEPTS = [
    "us-gaap:WeightedAverageInterestRate",
    "us-gaap:LongTermDebt",
    "us-gaap:LineOfCreditFacilityCurrentBorrowingCapacity",
]

EDGAR_ROUTING: dict[str, list[str]] = {
    "Growth & Earnings": _RPO_CONCEPTS,
    "Future Durability": _RPO_CONCEPTS,
    "Financial Health": _DEBT_MATURITY_CONCEPTS + _CREDIT_CONCEPTS,
    "Risk Assessment": _DEBT_MATURITY_CONCEPTS + _CREDIT_CONCEPTS,
}

# Filing narrative excerpts. Section text is stored in filing_sections by
# the Phase A ingest pipeline. Each section is truncated to
# FILING_EXCERPT_BUDGET_CHARS at prompt-build time.
FILING_EXCERPT_ROUTING: dict[str, list[str]] = {
    "Business Quality": ["item_1_business"],
    "Risk Assessment": ["item_1a_risk_factors"],
    "Growth & Earnings": ["item_7_mda", "item_2_mda_10q"],
    "Future Durability": ["item_7_mda", "item_1_business"],
    "Management & Governance": ["def14a_governance"],
}

FILING_EXCERPT_BUDGET_CHARS = 5000

# Categories that receive the counterparty (supply-chain) context. Uses
# DISPLAY NAMES to match FILING_EXCERPT_ROUTING.
RELATIONSHIP_ROUTING: set[str] = {
    "Business Quality",
    "Risk Assessment",
    "Future Durability",
}

# Deterministic quant fingerprint metric groups (services/quant_fingerprint.py).
# Keys are metric-group names inside CuratedFinancials.quant_fingerprint.
QUANT_ROUTING: dict[str, list[str]] = {
    "Financial Health": ["piotroski", "altman_z", "accruals", "fcf_conversion"],
    "Risk Assessment": ["altman_z", "beneish_m", "accruals"],
    "Growth & Earnings": ["margin_slopes", "sbc", "fcf_conversion"],
    "Business Quality": ["margin_slopes", "piotroski"],
    "Management & Governance": ["sbc", "beneish_m"],
}


# ── Unified accessor ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CategoryRouting:
    """All sources a deep-dive category receives, in one place.

    Empty list / False means the category does not receive that source.
    """
    transcript_passes: list[str] = field(default_factory=list)
    macro_indicators: list[str] = field(default_factory=list)
    edgar_concepts: list[str] = field(default_factory=list)
    filing_sections: list[str] = field(default_factory=list)
    relationships: bool = False
    quant_metrics: list[str] = field(default_factory=list)


def routing_for(category: str) -> CategoryRouting:
    """Return the consolidated per-source routing for a deep-dive category.

    Unknown categories return an empty `CategoryRouting` (no sources). This
    is the single accessor that future code should reach for; the underlying
    dicts are still re-exported for now to avoid touching the existing
    closures inside `node_deep_dive`.
    """
    return CategoryRouting(
        transcript_passes=list(TRANSCRIPT_ROUTING.get(category, [])),
        macro_indicators=list(MACRO_ROUTING.get(category, [])),
        edgar_concepts=list(EDGAR_ROUTING.get(category, [])),
        filing_sections=list(FILING_EXCERPT_ROUTING.get(category, [])),
        relationships=category in RELATIONSHIP_ROUTING,
        quant_metrics=list(QUANT_ROUTING.get(category, [])),
    )

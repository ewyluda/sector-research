"""Prompts for the prospectus pipeline's per-category analyses.

Seven categories. Six are adaptations of the equity deep-dive categories,
limited to what an S-1 actually answers. The seventh ("IPO Mechanics") is
new and scopes deal structure, dilution, lock-ups and use of proceeds.

Each system prompt asks Sonnet to return ONE JSON object matching:

{
  "category": "<name>",
  "content": "<markdown analysis>",
  "score": <0-100>,
  "key_findings": ["...", "..."]
}
"""
from __future__ import annotations

PROSPECTUS_CATEGORIES: tuple[str, ...] = (
    "Business Quality",
    "Risk Assessment",
    "Growth & Earnings",
    "Management & Governance",
    "Future Durability",
    "Macro & Regime",
    "IPO Mechanics",
)


# Sections each category receives. Keys are S-1 section_keys (Task 3) — the
# orchestrator pulls each section's text from filing_sections and renders it
# into {filing_excerpts} via the formatter below.
CATEGORY_SECTION_ROUTING: dict[str, tuple[str, ...]] = {
    "Business Quality": ("s1_business",),
    "Risk Assessment": ("s1_risk_factors", "s1_capitalization", "s1_dilution"),
    "Growth & Earnings": ("s1_mda",),
    "Management & Governance": ("s1_principal_stockholders", "s1_business"),
    "Future Durability": ("s1_business", "s1_use_of_proceeds"),
    "Macro & Regime": (),  # no S-1 sections — runs on FRED only
    "IPO Mechanics": ("s1_underwriting", "s1_use_of_proceeds", "s1_dilution"),
}

# Whether a category receives the counterparty context payload.
CATEGORY_USES_RELATIONSHIPS: frozenset[str] = frozenset({
    "Business Quality", "Risk Assessment", "Future Durability",
})

# Whether a category receives FRED macro data.
CATEGORY_USES_MACRO: frozenset[str] = frozenset({"Macro & Regime", "Future Durability"})

SECTION_BUDGET_CHARS = 8_000


PROSPECTUS_SYSTEM = """You are a fundamental analyst evaluating a company that has just filed an S-1 prospectus to go public.

You will analyse ONE category. Your inputs are verbatim excerpts from the S-1 plus, depending on the category, an extracted counterparty context and macro indicators.

Constraints:
- Be specific. Cite verbatim phrases from the filing in quotes when they support a claim.
- This is a private company about to IPO. There is no analyst consensus, no earnings transcript, no trading history. Do not invent any of those — work strictly from the inputs.
- Output a single JSON object with keys: category, content (markdown), score (0-100), key_findings (list of 3-6 short bullets). No prose outside the JSON.
- Score rubric for an IPO context:
   0-30 = serious concerns / disqualifying weakness
   31-55 = uncertain or below average
   56-75 = competent / typical
   76-100 = standout strength

Category being analysed: {category}
"""


PROSPECTUS_USER = """Category: {category}

{filing_excerpts}

{counterparty_context}

{macro_indicators}

Issuer: {issuer_name} (filing date: {filing_date}, form: {form_type})

Produce the JSON object now."""


# ── Per-category USER refinements (appended to PROSPECTUS_USER) ──────────────

CATEGORY_FOCUS: dict[str, str] = {
    "Business Quality": (
        "Focus on: what does the company actually do, who are its customers, "
        "what are its unit economics, what's the durability of its competitive position, "
        "is the business model proven or experimental."
    ),
    "Risk Assessment": (
        "Focus on: which risk factors are boilerplate vs. concrete; pre-IPO capital "
        "structure (Capitalization); dilution profile post-offering; concentration risks; "
        "regulatory / customer / supplier dependencies. Differentiate severity."
    ),
    "Growth & Earnings": (
        "Focus on: revenue trajectory, gross margin progression, opex leverage, "
        "path to profitability (or commentary on it), and any forward-looking statements "
        "in the MD&A that bound expectations for the next 12-24 months."
    ),
    "Management & Governance": (
        "Focus on: insider ownership concentration, founder / control-person structure "
        "(dual-class, voting agreements), independence of the board, related-party "
        "transactions, executive comp structure."
    ),
    "Future Durability": (
        "Focus on: where the capital raised will be deployed, the addressable-market "
        "narrative, vulnerability to macro / rate regimes, and counterparty concentration "
        "that could break the durability story."
    ),
    "Macro & Regime": (
        "Focus on: where the issuer sits in the current macro regime (rates, growth, "
        "inflation, credit). If the macro inputs are minimal, say so and score conservatively."
    ),
    "IPO Mechanics": (
        "Focus on: deal size, share count, primary vs. secondary mix, underwriter syndicate "
        "quality, use-of-proceeds clarity (concrete vs. 'general corporate purposes'), "
        "dilution to existing holders, lock-up structure (180-day standard? extended? early "
        "release triggers?), and post-offering float."
    ),
}

// Deep-dive category vocabularies — single source of truth.
//
// The app uses TWO overlapping 9-category sets:
//   SCORE_CATEGORIES — the scoring/deep-dive vocab; emitted by the LangGraph
//                      pipeline's report API as display-name keys.
//   DELTA_AXES       — the transcript-delta vocab; emitted by the Haiku
//                      delta extractor as snake_case keys.
//
// Both sets share 8 categories. They diverge on one slot:
//   scoring uses "Technical & Market Structure" (chart/RSI/momentum);
//   delta uses   "Valuation & Stage"            (mgmt language about pricing,
//                                                positioning, business maturity).
// Management never talks about chart structure on earnings calls, so the
// substitution is intentional. See `CONTEXT.md` -> Transcript delta.

// ── Scoring vocabulary ──────────────────────────────────────────────────────

export const SCORE_DISPLAY_TO_KEY: Record<string, string> = {
  "Business Quality": "business_quality",
  "Financial Health": "financial_health",
  "Growth & Earnings": "growth_earnings",
  "Management & Governance": "management_governance",
  "Technical & Market Structure": "technical_market_structure",
  "Macro & Regime": "macro_regime",
  "Sentiment & Narrative": "sentiment_narrative",
  "Risk Assessment": "risk_assessment",
  "Future Durability": "future_durability",
};

export function normalizeScoreKeys<T>(record: Record<string, T>): Record<string, T> {
  const out: Record<string, T> = {};
  for (const [k, v] of Object.entries(record)) {
    out[SCORE_DISPLAY_TO_KEY[k] ?? k] = v;
  }
  return out;
}

// ── Transcript-delta vocabulary ─────────────────────────────────────────────

export const DELTA_AXIS_KEYS = [
  "business_quality",
  "risk_assessment",
  "growth_earnings",
  "sentiment_narrative",
  "management_governance",
  "future_durability",
  "macro_regime",
  "financial_health",
  "valuation_stage",
] as const;

export type DeltaAxisKey = (typeof DELTA_AXIS_KEYS)[number];

export const DELTA_AXIS_LABELS: Record<DeltaAxisKey, string> = {
  business_quality: "Business Quality",
  risk_assessment: "Risk Assessment",
  growth_earnings: "Growth & Earnings",
  sentiment_narrative: "Sentiment & Narrative",
  management_governance: "Management & Governance",
  future_durability: "Future Durability",
  macro_regime: "Macro & Regime",
  financial_health: "Financial Health",
  valuation_stage: "Valuation & Stage",
};

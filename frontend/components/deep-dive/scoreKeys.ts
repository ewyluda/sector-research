export const DISPLAY_TO_KEY: Record<string, string> = {
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
    out[DISPLAY_TO_KEY[k] ?? k] = v;
  }
  return out;
}

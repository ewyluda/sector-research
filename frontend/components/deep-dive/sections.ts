/**
 * Shared section registry used by the sticky SectionNav and the Cmd-K command
 * palette. Keeping it in one place prevents the two surfaces from drifting —
 * every section needs both a pill and a searchable entry.
 *
 * `label` is the short pill label, `title` is the longer search-friendly form.
 */
export interface SectionEntry {
  id: string;
  label: string;
  title?: string;
}

export interface SectionGroup {
  title: string;
  items: SectionEntry[];
}

export const SECTION_GROUPS: SectionGroup[] = [
  {
    title: "Summary",
    items: [{ id: "overview", label: "Overview", title: "Deep Dive Overview" }],
  },
  {
    title: "Financials",
    items: [
      { id: "financial_health", label: "Financial Health" },
      { id: "growth_earnings", label: "Growth & Earnings" },
      { id: "technical_market_structure", label: "Technical", title: "Technical & Market Structure" },
      { id: "cross_category", label: "Correlations", title: "Cross-Category Correlations" },
      { id: "quant_fingerprint", label: "Quant", title: "Quant Fingerprint" },
    ],
  },
  {
    title: "Context",
    items: [
      { id: "business_quality", label: "Business Quality" },
      { id: "competition", label: "Competition" },
      { id: "supply_chain", label: "Supply Chain" },
      { id: "macro_regime", label: "Macro", title: "Macro & Regime" },
      { id: "risk_assessment", label: "Risk", title: "Risk Assessment" },
    ],
  },
  {
    title: "Qualitative",
    items: [
      { id: "what_changed", label: "What Changed", title: "What Changed" },
      { id: "management_governance", label: "Management", title: "Management & Governance" },
      { id: "sentiment_narrative", label: "Sentiment", title: "Sentiment & Narrative" },
      { id: "future_durability", label: "Future", title: "Future Durability" },
    ],
  },
];

export const SECTIONS: SectionEntry[] = SECTION_GROUPS.flatMap((g) => g.items);

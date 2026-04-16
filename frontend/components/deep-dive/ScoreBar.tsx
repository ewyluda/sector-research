const CATEGORIES = [
  { key: "business_quality", short: "BizQ", full: "Business Quality" },
  { key: "financial_health", short: "Fin", full: "Financial Health" },
  { key: "growth_earnings", short: "Grw", full: "Growth & Earnings" },
  { key: "management_governance", short: "Mgt", full: "Management & Governance" },
  { key: "technical_market_structure", short: "Tech", full: "Technical & Market" },
  { key: "macro_regime", short: "Mac", full: "Macro & Regime" },
  { key: "sentiment_narrative", short: "Sen", full: "Sentiment & Narrative" },
  { key: "risk_assessment", short: "Rsk", full: "Risk Assessment" },
  { key: "future_durability", short: "Fut", full: "Future Durability" },
];

function segmentColor(score: number | null): string {
  if (score == null) return "bg-[var(--color-surface-alt)] text-[var(--color-text-faint)] animate-pulse";
  if (score >= 70) return "bg-emerald-500/20 text-emerald-400";
  if (score >= 50) return "bg-amber-500/20 text-amber-400";
  return "bg-red-500/20 text-red-400";
}

interface ScoreBarProps {
  scores: Record<string, number>;
}

export function ScoreBar({ scores }: ScoreBarProps) {
  return (
    <div className="flex gap-0.5 rounded-lg overflow-hidden">
      {CATEGORIES.map(({ key, short, full }) => {
        const score = scores[key] ?? null;
        return (
          <div key={key} className={`flex-1 py-1.5 text-center ${segmentColor(score)}`} title={`${full}: ${score ?? "N/A"}/100`}>
            <p className="text-[8px] font-medium uppercase">{short}</p>
            <p className="text-[10px] font-mono font-semibold">{score ?? "—"}</p>
          </div>
        );
      })}
    </div>
  );
}

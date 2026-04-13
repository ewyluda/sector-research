const CATEGORIES = [
  { key: "business_quality", short: "BizQ" },
  { key: "financial_health", short: "Fin" },
  { key: "growth_earnings", short: "Grw" },
  { key: "management_governance", short: "Mgt" },
  { key: "technical_market_structure", short: "Tech" },
  { key: "macro_regime", short: "Mac" },
  { key: "sentiment_narrative", short: "Sen" },
  { key: "risk_assessment", short: "Rsk" },
  { key: "future_durability", short: "Fut" },
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
      {CATEGORIES.map(({ key, short }) => {
        const score = scores[key] ?? null;
        return (
          <div key={key} className={`flex-1 py-1.5 text-center ${segmentColor(score)}`}>
            <p className="text-[8px] font-medium uppercase">{short}</p>
            <p className="text-[10px] font-mono font-semibold">{score ?? "—"}</p>
          </div>
        );
      })}
    </div>
  );
}

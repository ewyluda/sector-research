import { scoreSegment } from "./scoreColors";

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

interface ScoreBarProps {
  scores: Record<string, number>;
}

export function ScoreBar({ scores }: ScoreBarProps) {
  return (
    <div className="flex gap-0.5 rounded-lg overflow-hidden">
      {CATEGORIES.map(({ key, short, full }) => {
        const score = scores[key] ?? null;
        return (
          <div key={key} className={`flex-1 py-1.5 text-center ${scoreSegment(score)}`} title={`${full}: ${score ?? "N/A"}/100`}>
            <p className="text-[8px] font-medium uppercase">{short}</p>
            <p className="text-[10px] font-mono font-semibold">{score ?? "—"}</p>
          </div>
        );
      })}
    </div>
  );
}

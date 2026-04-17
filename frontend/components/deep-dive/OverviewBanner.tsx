import type { CuratedFinancials } from "@/lib/api";
import { ScoreRadar } from "./ScoreRadar";
import { HeadlineMetrics } from "./HeadlineMetrics";
import { ScoreBar } from "./ScoreBar";

interface OverviewBannerProps {
  financials: CuratedFinancials | null;
  scores: Record<string, number>;
}

const SCORE_LABELS: Record<string, string> = {
  business_quality: "Business Quality",
  financial_health: "Financial Health",
  growth_earnings: "Growth",
  management_governance: "Management",
  technical_market_structure: "Technicals",
  macro_regime: "Macro",
  sentiment_narrative: "Sentiment",
  risk_assessment: "Risk",
  future_durability: "Durability",
};

const SCORING_KEYS = Object.keys(SCORE_LABELS);

function overallTone(score: number): string {
  if (score >= 70) return "Strong";
  if (score >= 55) return "Balanced";
  if (score >= 40) return "Mixed";
  return "Fragile";
}

/** Compose a single-sentence verdict from the nine category scores.
 * Highlights the highest and lowest category so the reader gets orientation
 * in one glance before scrolling the dashboard. */
function buildSummary(scores: Record<string, number>, total: number): string | null {
  const entries = SCORING_KEYS
    .map((k) => ({ key: k, score: scores[k] }))
    .filter((e): e is { key: string; score: number } => typeof e.score === "number");
  if (entries.length < 2) return null;
  const sorted = [...entries].sort((a, b) => b.score - a.score);
  const best = sorted[0];
  const worst = sorted[sorted.length - 1];
  const tone = overallTone(total);
  const bestLabel = SCORE_LABELS[best.key] ?? best.key;
  const worstLabel = SCORE_LABELS[worst.key] ?? worst.key;
  return `${tone} overall — ${bestLabel} tops at ${best.score}, ${worstLabel} bottoms at ${worst.score}.`;
}

export function OverviewBanner({ financials, scores }: OverviewBannerProps) {
  const totalScore = Object.values(scores).length > 0
    ? Math.round(Object.values(scores).reduce((a, b) => a + b, 0) / Object.values(scores).length)
    : null;
  const summary = totalScore != null ? buildSummary(scores, totalScore) : null;

  return (
    <div id="overview" className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold text-[var(--color-text-primary)] uppercase tracking-wider">
            Deep Dive Analysis
          </h2>
          {summary && (
            <p className="text-xs text-[var(--color-text-muted)] mt-1 leading-relaxed">{summary}</p>
          )}
        </div>
        {totalScore != null && (
          <span className="shrink-0 text-sm font-mono font-semibold text-[var(--color-text-primary)]">
            Score: {totalScore}
          </span>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ScoreRadar scores={scores} />
        {financials ? (
          <HeadlineMetrics financials={financials} />
        ) : (
          <div className="grid grid-cols-3 gap-2">
            {[1, 2, 3, 4, 5, 6].map((i) => (
              <div key={i} className="animate-pulse rounded-lg bg-[var(--color-surface-alt)] h-20" />
            ))}
          </div>
        )}
      </div>

      <ScoreBar scores={scores} />
    </div>
  );
}

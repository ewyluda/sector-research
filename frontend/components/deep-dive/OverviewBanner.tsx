import type { CuratedFinancials } from "@/lib/api";
import { ScoreRadar } from "./ScoreRadar";
import { HeadlineMetrics } from "./HeadlineMetrics";
import { ScoreBar } from "./ScoreBar";

interface OverviewBannerProps {
  financials: CuratedFinancials | null;
  scores: Record<string, number>;
}

export function OverviewBanner({ financials, scores }: OverviewBannerProps) {
  const totalScore = Object.values(scores).length > 0
    ? Math.round(Object.values(scores).reduce((a, b) => a + b, 0) / Object.values(scores).length)
    : null;

  return (
    <div id="overview" className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-[var(--color-text-primary)] uppercase tracking-wider">
          Deep Dive Analysis
        </h2>
        {totalScore != null && (
          <span className="text-sm font-mono font-semibold text-[var(--color-text-primary)]">
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

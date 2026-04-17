import type { CuratedFinancials, QuickScreenStructured } from "@/lib/api";
import ScoreRing from "@/components/ScoreRing";

interface ReportHeaderProps {
  financials: CuratedFinancials | null;
  quickScreen: QuickScreenStructured | null;
  convictionScore: number | null;
  ticker: string;
  isLive?: boolean;
}

function fmtMarketCap(value: number): string {
  if (value >= 1e12) return `$${(value / 1e12).toFixed(1)}T`;
  if (value >= 1e9) return `$${(value / 1e9).toFixed(1)}B`;
  if (value >= 1e6) return `$${(value / 1e6).toFixed(0)}M`;
  return `$${value.toFixed(0)}`;
}

function convictionTier(score: number): string {
  if (score >= 75) return "High Conviction";
  if (score >= 55) return "Moderate";
  if (score >= 35) return "Low";
  return "Very Low";
}

function VerdictBadge({ recommendation }: { recommendation: "GO" | "WATCHLIST" | "PASS" }) {
  const styles: Record<string, string> = {
    GO: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
    WATCHLIST: "bg-amber-500/15 text-amber-400 border-amber-500/30",
    PASS: "bg-red-500/15 text-red-400 border-red-500/30",
  };

  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold uppercase tracking-wide border ${styles[recommendation]}`}>
      {recommendation}
    </span>
  );
}

export function ReportHeader({ financials, quickScreen, convictionScore, ticker, isLive }: ReportHeaderProps) {
  return (
    <section id="report_header" className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] overflow-hidden">
      {/* Top row: identity + conviction ring */}
      <div className="p-5 border-b border-[var(--color-border)] flex items-start justify-between gap-4">
        <div className="flex items-center gap-3 min-w-0">
          <div className="min-w-0">
            <div className="flex items-center gap-2.5">
              <h1 className="text-2xl font-bold font-mono text-[var(--color-text-primary)]">{ticker}</h1>
              {quickScreen && <VerdictBadge recommendation={quickScreen.recommendation} />}
            </div>
            {financials && (
              <>
                <p className="text-sm text-[var(--color-text-primary)] mt-0.5">{financials.company_name}</p>
                <p className="text-xs text-[var(--color-text-muted)] mt-0.5">
                  {[
                    financials.sector,
                    financials.industry,
                    fmtMarketCap(financials.market_cap),
                    `$${financials.current_price.toFixed(2)}`,
                  ].join(" \u00B7 ")}
                </p>
              </>
            )}
          </div>
        </div>
        <div className="shrink-0 flex flex-col items-center gap-1">
          {convictionScore != null ? (
            <>
              <ScoreRing score={convictionScore} size={92} label="Conviction" />
              <span className="text-[10px] font-medium text-[var(--color-text-muted)] whitespace-nowrap">
                {convictionTier(convictionScore)}
              </span>
            </>
          ) : isLive ? (
            <>
              <div className="w-[92px] h-[92px] rounded-full bg-[var(--color-surface-alt)] animate-pulse" />
              <span className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">Conviction</span>
            </>
          ) : null}
        </div>
      </div>

      {/* Thesis / Key Risk callouts */}
      {quickScreen?.thesis && quickScreen?.key_risk && (
        <div className="grid grid-cols-1 md:grid-cols-2">
          <div className="p-5 border-b md:border-b-0 md:border-r border-[var(--color-border)]">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-emerald-400 mb-1">Thesis</p>
            <p className="text-sm text-[var(--color-text-primary)] leading-relaxed">{quickScreen.thesis}</p>
          </div>
          <div className="p-5">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-red-400 mb-1">Key Risk</p>
            <p className="text-sm text-[var(--color-text-primary)] leading-relaxed">{quickScreen.key_risk}</p>
          </div>
        </div>
      )}
    </section>
  );
}

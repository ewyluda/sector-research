import { memo } from "react";
import type { CuratedFinancials, DeepDiveCategoryStructured, CategoryOutput } from "@/lib/api";
import { DataRichSection } from "./DataRichSection";
import { BulletRangeChart } from "../charts/BulletRangeChart";
import { CandlestickChart } from "../charts/CandlestickChart";
import { ChartSkeleton } from "../skeleton/ChartSkeleton";

interface TechnicalMarketProps {
  financials: CuratedFinancials | null;
  structured: DeepDiveCategoryStructured | null;
  score: number | null;
  fallback?: CategoryOutput | null;
  isLive?: boolean;
}

function fmtVol(v: number): string {
  if (v >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `${(v / 1e3).toFixed(0)}K`;
  return String(Math.round(v));
}

function TechnicalMarketImpl({ financials, structured, score, fallback, isLive }: TechnicalMarketProps) {
  return (
    <DataRichSection id="technical_market_structure" label="Technical & Market Structure" score={score} structured={structured} fallback={fallback} isLive={isLive}>
      {financials ? (
        <>
          {financials.daily_prices?.length > 0 && (
            <div>
              <h4 className="text-[10px] font-medium text-[var(--color-text-muted)] uppercase tracking-wider mb-2">Price Action (1Y)</h4>
              <CandlestickChart data={financials.daily_prices} />
            </div>
          )}
          <div>
            <h4 className="text-[10px] font-medium text-[var(--color-text-muted)] uppercase tracking-wider mb-2">52-Week Price Range</h4>
            {financials.fifty_two_week_low != null && financials.fifty_two_week_high != null ? (
              <BulletRangeChart
                low={financials.fifty_two_week_low}
                high={financials.fifty_two_week_high}
                current={financials.current_price}
                dcfTarget={financials.dcf_intrinsic_value}
              />
            ) : (
              <p className="text-xs text-[var(--color-text-muted)]">52-week range data unavailable</p>
            )}
          </div>
          <div>
            <h4 className="text-[10px] font-medium text-[var(--color-text-muted)] uppercase tracking-wider mb-2">Key Metrics</h4>
            <table className="w-full text-xs">
              <tbody>
                <tr className="border-b border-[var(--color-border)]">
                  <td className="py-1.5 text-[var(--color-text-muted)]">Beta</td>
                  <td className="py-1.5 text-right font-mono text-[var(--color-text-primary)]">{financials.beta?.toFixed(2) ?? "—"}</td>
                </tr>
                <tr className="border-b border-[var(--color-border)]">
                  <td className="py-1.5 text-[var(--color-text-muted)]">52W High</td>
                  <td className="py-1.5 text-right font-mono text-[var(--color-text-primary)]">${financials.fifty_two_week_high?.toFixed(2) ?? "—"}</td>
                </tr>
                <tr className="border-b border-[var(--color-border)]">
                  <td className="py-1.5 text-[var(--color-text-muted)]">52W Low</td>
                  <td className="py-1.5 text-right font-mono text-[var(--color-text-primary)]">${financials.fifty_two_week_low?.toFixed(2) ?? "—"}</td>
                </tr>
                <tr className="border-b border-[var(--color-border)]">
                  <td className="py-1.5 text-[var(--color-text-muted)]">DCF Value</td>
                  <td className="py-1.5 text-right font-mono text-[var(--color-text-primary)]">{financials.dcf_intrinsic_value != null ? `$${financials.dcf_intrinsic_value.toFixed(2)}` : "—"}</td>
                </tr>
                <tr className="border-b border-[var(--color-border)]">
                  <td className="py-1.5 text-[var(--color-text-muted)]">Over/Undervalued</td>
                  <td className="py-1.5 text-right font-mono text-[var(--color-text-primary)]">{financials.dcf_gap_percent != null ? `${financials.dcf_gap_percent > 0 ? "+" : ""}${financials.dcf_gap_percent.toFixed(1)}%` : "—"}</td>
                </tr>
                <tr>
                  <td className="py-1.5 text-[var(--color-text-muted)]">Avg Volume</td>
                  <td className="py-1.5 text-right font-mono text-[var(--color-text-primary)]">{financials.volume_avg != null ? fmtVol(financials.volume_avg) : "—"}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </>
      ) : isLive ? (
        <ChartSkeleton className="h-[200px]" />
      ) : null}
    </DataRichSection>
  );
}

export const TechnicalMarket = memo(TechnicalMarketImpl);

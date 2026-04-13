import type { CuratedFinancials, DeepDiveCategoryStructured } from "@/lib/api";
import { DataRichSection } from "./DataRichSection";
import { GroupedBarChart } from "../charts/GroupedBarChart";
import { TrendLineChart } from "../charts/TrendLineChart";
import { ChartSkeleton } from "../skeleton/ChartSkeleton";

interface GrowthEarningsProps {
  financials: CuratedFinancials | null;
  structured: DeepDiveCategoryStructured | null;
  score: number | null;
  isLive?: boolean;
}

export function GrowthEarnings({ financials, structured, score, isLive }: GrowthEarningsProps) {
  return (
    <DataRichSection id="growth_earnings" label="Growth & Earnings" score={score} structured={structured} isLive={isLive}>
      {financials ? (
        <>
          <div>
            <h4 className="text-[10px] font-medium text-[var(--color-text-muted)] uppercase tracking-wider mb-2">Revenue</h4>
            <GroupedBarChart metrics={financials.quarterly_revenue} label="Revenue" />
          </div>
          <div>
            <h4 className="text-[10px] font-medium text-[var(--color-text-muted)] uppercase tracking-wider mb-2">Margin Trends</h4>
            <TrendLineChart
              lines={[
                { data: financials.quarterly_gross_margin, name: "Gross", color: "#34d399" },
                { data: financials.quarterly_operating_margin, name: "Operating", color: "#60a5fa" },
                { data: financials.quarterly_net_margin, name: "Net", color: "#a78bfa" },
              ]}
            />
          </div>
          <div>
            <h4 className="text-[10px] font-medium text-[var(--color-text-muted)] uppercase tracking-wider mb-2">Analyst Estimates</h4>
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-[var(--color-border)]">
                  <th className="text-left py-1.5 font-medium text-[var(--color-text-muted)]">Period</th>
                  <th className="text-right py-1.5 font-medium text-[var(--color-text-muted)]">Rev Est.</th>
                  <th className="text-right py-1.5 font-medium text-[var(--color-text-muted)]">EPS Est.</th>
                </tr>
              </thead>
              <tbody>
                {financials.forward_revenue_estimates.map((rev, i) => {
                  const eps = financials.forward_eps_estimates[i];
                  return (
                    <tr key={rev.period} className="border-b border-[var(--color-border)] last:border-0">
                      <td className="py-1.5 text-[var(--color-text-primary)]">{rev.period}</td>
                      <td className="py-1.5 text-right font-mono text-[var(--color-text-primary)]">
                        ${(rev.estimate / 1e9).toFixed(1)}B
                      </td>
                      <td className="py-1.5 text-right font-mono text-[var(--color-text-primary)]">
                        {eps ? `$${eps.estimate.toFixed(2)}` : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      ) : isLive ? (
        <>
          <ChartSkeleton className="h-[220px]" />
          <ChartSkeleton className="h-[200px]" />
        </>
      ) : null}
    </DataRichSection>
  );
}

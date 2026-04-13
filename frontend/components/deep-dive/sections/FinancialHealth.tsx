import type { CuratedFinancials, DeepDiveCategoryStructured, CategoryOutput } from "@/lib/api";
import { DataRichSection } from "./DataRichSection";
import { StackedBarChart } from "../charts/StackedBarChart";
import { TrendLineChart } from "../charts/TrendLineChart";
import { ChartSkeleton } from "../skeleton/ChartSkeleton";

interface FinancialHealthProps {
  financials: CuratedFinancials | null;
  structured: DeepDiveCategoryStructured | null;
  score: number | null;
  fallback?: CategoryOutput | null;
  isLive?: boolean;
}

export function FinancialHealth({ financials, structured, score, fallback, isLive }: FinancialHealthProps) {
  return (
    <DataRichSection id="financial_health" label="Financial Health" score={score} structured={structured} fallback={fallback} isLive={isLive}>
      {financials ? (
        <>
          <div>
            <h4 className="text-[10px] font-medium text-[var(--color-text-muted)] uppercase tracking-wider mb-2">Balance Sheet Composition</h4>
            <StackedBarChart cash={financials.quarterly_cash} debt={financials.quarterly_total_debt} equity={financials.quarterly_shareholders_equity} />
          </div>
          <div>
            <h4 className="text-[10px] font-medium text-[var(--color-text-muted)] uppercase tracking-wider mb-2">Current Ratio</h4>
            <TrendLineChart
              lines={[{ data: financials.quarterly_current_ratio, name: "Current Ratio", color: "#60a5fa" }]}
              yAxisSuffix=""
              referenceLine={1.0}
            />
          </div>
          <div>
            <h4 className="text-[10px] font-medium text-[var(--color-text-muted)] uppercase tracking-wider mb-2">Key Ratios</h4>
            <table className="w-full text-xs">
              <tbody>
                <tr className="border-b border-[var(--color-border)]">
                  <td className="py-1.5 text-[var(--color-text-muted)]">D/E Ratio</td>
                  <td className="py-1.5 text-right font-mono text-[var(--color-text-primary)]">{financials.debt_to_equity.toFixed(2)}</td>
                </tr>
                <tr className="border-b border-[var(--color-border)]">
                  <td className="py-1.5 text-[var(--color-text-muted)]">Current Ratio</td>
                  <td className="py-1.5 text-right font-mono text-[var(--color-text-primary)]">{financials.quarterly_current_ratio[0]?.value.toFixed(2) ?? "—"}</td>
                </tr>
                <tr>
                  <td className="py-1.5 text-[var(--color-text-muted)]">Cash / Debt</td>
                  <td className="py-1.5 text-right font-mono text-[var(--color-text-primary)]">
                    {financials.quarterly_total_debt[0]?.value
                      ? (financials.quarterly_cash[0]?.value / financials.quarterly_total_debt[0].value).toFixed(2)
                      : "—"}
                  </td>
                </tr>
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

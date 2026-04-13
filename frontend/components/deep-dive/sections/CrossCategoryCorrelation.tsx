"use client";

import type { CuratedFinancials, QuarterlyMetric } from "@/lib/api";
import { TrendLineChart } from "../charts/TrendLineChart";
import { ChartSkeleton } from "../skeleton/ChartSkeleton";

interface CrossCategoryCorrelationProps {
  financials: CuratedFinancials | null;
  isLive?: boolean;
}

interface CorrelationPair {
  title: string;
  description: string;
  lines: { data: QuarterlyMetric[]; name: string; color: string }[];
  yAxisSuffix: string;
  referenceLine?: number;
}

function buildPairs(f: CuratedFinancials): CorrelationPair[] {
  const pairs: CorrelationPair[] = [];

  // 1. Revenue vs Free Cash Flow (normalized to $B)
  if (f.quarterly_revenue.length >= 2 && f.quarterly_free_cf.length >= 2) {
    pairs.push({
      title: "Revenue vs Free Cash Flow",
      description: "Cash conversion efficiency — FCF should track revenue growth",
      lines: [
        { data: f.quarterly_revenue, name: "Revenue", color: "#6366f1" },
        { data: f.quarterly_free_cf, name: "Free CF", color: "#10b981" },
      ],
      yAxisSuffix: "",
    });
  }

  // 2. Gross Margin vs Operating Margin
  if (f.quarterly_gross_margin.length >= 2 && f.quarterly_operating_margin.length >= 2) {
    pairs.push({
      title: "Gross Margin vs Operating Margin",
      description: "Operating leverage — narrowing spread signals rising SG&A or R&D",
      lines: [
        { data: f.quarterly_gross_margin, name: "Gross Margin", color: "#8b5cf6" },
        { data: f.quarterly_operating_margin, name: "Op Margin", color: "#f59e0b" },
        ...(f.quarterly_net_margin.length >= 2
          ? [{ data: f.quarterly_net_margin, name: "Net Margin", color: "#ef4444" }]
          : []),
      ],
      yAxisSuffix: "%",
    });
  }

  // 3. Operating Cash Flow vs CapEx
  if (f.quarterly_operating_cf.length >= 2 && f.quarterly_capex.length >= 2) {
    // Invert capex (usually negative) so both lines trend positively
    const capexPositive = f.quarterly_capex.map((m) => ({
      ...m,
      value: Math.abs(m.value),
    }));
    pairs.push({
      title: "Operating CF vs CapEx",
      description: "Capital intensity — gap between OCF and CapEx = free cash generation",
      lines: [
        { data: f.quarterly_operating_cf, name: "Operating CF", color: "#06b6d4" },
        { data: capexPositive, name: "CapEx", color: "#f43f5e" },
      ],
      yAxisSuffix: "",
    });
  }

  // 4. Debt vs Cash position
  if (f.quarterly_total_debt.length >= 2 && f.quarterly_cash.length >= 2) {
    pairs.push({
      title: "Cash vs Total Debt",
      description: "Net liquidity position — convergence signals improving balance sheet",
      lines: [
        { data: f.quarterly_cash, name: "Cash", color: "#10b981" },
        { data: f.quarterly_total_debt, name: "Total Debt", color: "#ef4444" },
      ],
      yAxisSuffix: "",
    });
  }

  return pairs;
}

function formatValue(v: number): string {
  if (Math.abs(v) >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (Math.abs(v) >= 1e6) return `$${(v / 1e6).toFixed(0)}M`;
  return `$${v.toFixed(0)}`;
}

export function CrossCategoryCorrelation({ financials, isLive }: CrossCategoryCorrelationProps) {
  if (!financials) {
    if (isLive) return <section id="cross_category"><ChartSkeleton /></section>;
    return null;
  }

  const pairs = buildPairs(financials);
  if (pairs.length === 0) return null;

  return (
    <section id="cross_category" className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] overflow-hidden">
      <div className="px-5 py-3 border-b border-[var(--color-border)] bg-[var(--color-bg)]/40">
        <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">Cross-Category Correlations</h3>
        <p className="text-[10px] text-[var(--color-text-muted)] mt-0.5">Overlay trends across financial categories to surface relationships</p>
      </div>
      <div className="p-5 grid grid-cols-1 lg:grid-cols-2 gap-6">
        {pairs.map((pair) => (
          <div key={pair.title}>
            <p className="text-xs font-semibold text-[var(--color-text-primary)] mb-0.5">{pair.title}</p>
            <p className="text-[10px] text-[var(--color-text-muted)] mb-3">{pair.description}</p>
            <TrendLineChart
              lines={pair.lines}
              yAxisSuffix={pair.yAxisSuffix}
              referenceLine={pair.referenceLine}
            />
          </div>
        ))}
      </div>
    </section>
  );
}

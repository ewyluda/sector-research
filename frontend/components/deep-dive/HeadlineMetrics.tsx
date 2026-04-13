import type { CuratedFinancials } from "@/lib/api";

interface HeadlineMetricsProps {
  financials: CuratedFinancials;
}

function fmt(value: number, type: "currency" | "pct" | "ratio" | "eps"): string {
  if (type === "currency") {
    if (Math.abs(value) >= 1e9) return `$${(value / 1e9).toFixed(1)}B`;
    if (Math.abs(value) >= 1e6) return `$${(value / 1e6).toFixed(0)}M`;
    return `$${value.toFixed(0)}`;
  }
  if (type === "pct") return `${value > 0 ? "+" : ""}${value.toFixed(1)}%`;
  if (type === "ratio") return value.toFixed(2);
  if (type === "eps") return `$${value.toFixed(2)}`;
  return String(value);
}

function MetricCard({ label, value, subtitle, subtitleColor }: { label: string; value: string; subtitle: string; subtitleColor?: string }) {
  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-3">
      <p className="text-[10px] font-medium text-[var(--color-text-muted)] uppercase tracking-wider">{label}</p>
      <p className="text-lg font-semibold font-mono text-[var(--color-text-primary)] mt-0.5">{value}</p>
      <p className={`text-[10px] mt-0.5 ${subtitleColor ?? "text-[var(--color-text-muted)]"}`}>{subtitle}</p>
    </div>
  );
}

export function HeadlineMetrics({ financials }: HeadlineMetricsProps) {
  const latestRev = financials.quarterly_revenue[0];
  const latestFcf = financials.quarterly_free_cf[0];
  const latestOpMargin = financials.quarterly_operating_margin[0];
  const ttmEps = financials.quarterly_eps.slice(0, 4).reduce((sum, m) => sum + m.value, 0);
  const prevTtmEps = financials.quarterly_eps.length >= 5
    ? financials.quarterly_eps.slice(1, 5).reduce((sum, m) => sum + m.value, 0)
    : null;
  const epsGrowth = prevTtmEps && prevTtmEps !== 0 ? ((ttmEps - prevTtmEps) / Math.abs(prevTtmEps)) * 100 : null;

  const deLabel = financials.debt_to_equity < 0.5 ? "Low Leverage" : financials.debt_to_equity < 1.5 ? "Moderate" : "High Leverage";
  const dcfLabel = financials.dcf_gap_percent != null
    ? (financials.dcf_gap_percent > 0 ? "Undervalued" : "Overvalued")
    : "N/A";

  const marginDir = financials.quarterly_operating_margin.length >= 2
    ? (financials.quarterly_operating_margin[0].value > financials.quarterly_operating_margin[1].value ? "Expanding" : "Contracting")
    : "—";

  return (
    <div className="grid grid-cols-3 gap-2">
      <MetricCard
        label="Revenue"
        value={latestRev ? fmt(latestRev.value, "currency") : "—"}
        subtitle={latestRev?.yoy_growth != null ? fmt(latestRev.yoy_growth, "pct") + " YoY" : "—"}
        subtitleColor={latestRev?.yoy_growth != null ? (latestRev.yoy_growth >= 0 ? "text-emerald-400" : "text-red-400") : undefined}
      />
      <MetricCard
        label="Free Cash Flow"
        value={latestFcf ? fmt(latestFcf.value, "currency") : "—"}
        subtitle={latestFcf?.yoy_growth != null ? fmt(latestFcf.yoy_growth, "pct") + " YoY" : "—"}
        subtitleColor={latestFcf?.yoy_growth != null ? (latestFcf.yoy_growth >= 0 ? "text-emerald-400" : "text-red-400") : undefined}
      />
      <MetricCard
        label="DCF Gap"
        value={financials.dcf_gap_percent != null ? fmt(financials.dcf_gap_percent, "pct") : "—"}
        subtitle={dcfLabel}
        subtitleColor={financials.dcf_gap_percent != null ? (financials.dcf_gap_percent > 0 ? "text-emerald-400" : "text-red-400") : undefined}
      />
      <MetricCard label="D/E Ratio" value={fmt(financials.debt_to_equity, "ratio")} subtitle={deLabel} />
      <MetricCard label="Op. Margin" value={latestOpMargin ? `${latestOpMargin.value.toFixed(1)}%` : "—"} subtitle={marginDir} />
      <MetricCard
        label="EPS (TTM)"
        value={fmt(ttmEps, "eps")}
        subtitle={epsGrowth != null ? fmt(epsGrowth, "pct") + " YoY" : "—"}
        subtitleColor={epsGrowth != null ? (epsGrowth >= 0 ? "text-emerald-400" : "text-red-400") : undefined}
      />
    </div>
  );
}

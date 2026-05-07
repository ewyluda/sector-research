"use client";

import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import type { EdgarFacts } from "@/lib/api";
import { formatUSD } from "@/lib/format";

const RPO_CONCEPT = "us-gaap:RevenueRemainingPerformanceObligation";

interface RPOTrendProps {
  edgarFacts: EdgarFacts;
}

export function RPOTrend({ edgarFacts }: RPOTrendProps) {
  const facts = edgarFacts[RPO_CONCEPT] ?? [];
  if (facts.length === 0) return null;

  const twoYearsAgo = new Date();
  twoYearsAgo.setFullYear(twoYearsAgo.getFullYear() - 2);
  if (new Date(facts[0].period_end) < twoYearsAgo) return null;

  // API returns most-recent-first; chart reads left→right oldest→newest.
  const data = [...facts]
    .reverse()
    .slice(-8)
    .map((f) => ({
      period: f.fiscal_year && f.fiscal_period
        ? `${f.fiscal_period} FY${String(f.fiscal_year).slice(-2)}`
        : f.period_end,
      value: f.value,
      periodEnd: f.period_end,
    }));

  const latest = data[data.length - 1];
  const first = data[0];
  const growth =
    first && latest && first.value > 0
      ? ((latest.value - first.value) / first.value) * 100
      : null;

  return (
    <div>
      <h4 className="text-[10px] font-medium text-[var(--color-text-muted)] uppercase tracking-wider mb-2">
        RPO Trend <span className="text-[9px] text-[var(--color-text-muted)] normal-case">(SEC XBRL)</span>
      </h4>
      <div className="flex items-center justify-between mb-1 px-1">
        <span className="text-[10px] text-[var(--color-text-muted)]">
          Remaining Performance Obligation (contracted backlog)
        </span>
        <span className="text-[10px] font-mono text-[var(--color-text-primary)]">
          {formatUSD(latest.value)}
          {growth !== null && (
            <span className={`ml-2 ${growth >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
              {growth >= 0 ? "+" : ""}{growth.toFixed(1)}%
            </span>
          )}
        </span>
      </div>
      <ResponsiveContainer width="100%" height={200}>
        <BarChart data={data} margin={{ top: 5, right: 5, bottom: 5, left: 5 }}>
          <XAxis dataKey="period" tick={{ fontSize: 10, fill: "var(--color-text-muted)" }} />
          <YAxis
            tick={{ fontSize: 10, fill: "var(--color-text-muted)" }}
            tickFormatter={(v) => formatUSD(v)}
            width={60}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "var(--color-surface)",
              border: "1px solid var(--color-border)",
              borderRadius: 8,
              fontSize: 11,
            }}
            formatter={(value) => [formatUSD(value as number), "RPO"]}
          />
          <Bar dataKey="value" fill="#60a5fa" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

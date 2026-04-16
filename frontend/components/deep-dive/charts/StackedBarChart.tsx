"use client";

import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend } from "recharts";
import type { QuarterlyMetric } from "@/lib/api";
import { formatUSD } from "@/lib/format";

interface StackedBarChartProps {
  cash: QuarterlyMetric[];
  debt: QuarterlyMetric[];
  equity: QuarterlyMetric[];
}

export function StackedBarChart({ cash, debt, equity }: StackedBarChartProps) {
  const data = cash.map((c, i) => ({
    period: c.period,
    Cash: c.value,
    Debt: debt[i]?.value ?? 0,
    Equity: equity[i]?.value ?? 0,
  })).reverse();

  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={data} margin={{ top: 5, right: 5, bottom: 5, left: 5 }}>
        <XAxis dataKey="period" tick={{ fontSize: 12, fill: "var(--color-text-muted)" }} />
        <YAxis tick={{ fontSize: 12, fill: "var(--color-text-muted)" }} tickFormatter={(v) => formatUSD(v)} width={60} />
        <Tooltip
          contentStyle={{ backgroundColor: "var(--color-surface)", border: "1px solid var(--color-border)", borderRadius: 8, fontSize: 11 }}
          formatter={(value) => [formatUSD(value as number)]}
        />
        <Legend wrapperStyle={{ fontSize: 10 }} />
        <Bar dataKey="Cash" stackId="a" fill="#34d399" radius={[0, 0, 0, 0]} />
        <Bar dataKey="Debt" stackId="a" fill="#f87171" radius={[0, 0, 0, 0]} />
        <Bar dataKey="Equity" stackId="a" fill="#60a5fa" radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

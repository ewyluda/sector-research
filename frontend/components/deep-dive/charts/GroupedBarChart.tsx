"use client";

import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, LabelList } from "recharts";
import type { QuarterlyMetric } from "@/lib/api";

interface GroupedBarChartProps {
  metrics: QuarterlyMetric[];
  label?: string;
  formatValue?: (v: number) => string;
}

export function GroupedBarChart({ metrics, label = "Revenue", formatValue }: GroupedBarChartProps) {
  const fmt = formatValue ?? ((v: number) => `$${(v / 1e9).toFixed(1)}B`);
  const data = [...metrics].reverse().map((m) => ({
    period: m.period,
    value: m.value,
    yoy: m.yoy_growth != null ? `${m.yoy_growth > 0 ? "+" : ""}${m.yoy_growth.toFixed(1)}%` : "",
  }));

  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data} margin={{ top: 20, right: 5, bottom: 5, left: 5 }}>
        <XAxis dataKey="period" tick={{ fontSize: 10, fill: "var(--color-text-muted)" }} />
        <YAxis tick={{ fontSize: 10, fill: "var(--color-text-muted)" }} tickFormatter={(v) => fmt(v)} width={55} />
        <Tooltip
          contentStyle={{ backgroundColor: "var(--color-surface)", border: "1px solid var(--color-border)", borderRadius: 8, fontSize: 11 }}
          formatter={(value) => [fmt(value as number), label]}
        />
        <Bar dataKey="value" fill="var(--color-primary)" radius={[4, 4, 0, 0]}>
          <LabelList dataKey="yoy" position="top" style={{ fontSize: 9, fill: "var(--color-text-muted)" }} />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

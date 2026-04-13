"use client";

import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend, ReferenceLine } from "recharts";
import type { QuarterlyMetric } from "@/lib/api";

interface TrendLine {
  data: QuarterlyMetric[];
  name: string;
  color: string;
}

interface TrendLineChartProps {
  lines: TrendLine[];
  yAxisSuffix?: string;
  referenceLine?: number;
}

export function TrendLineChart({ lines, yAxisSuffix = "%", referenceLine }: TrendLineChartProps) {
  const periodSet = new Map<string, Record<string, number>>();
  for (const line of lines) {
    for (const m of line.data) {
      const existing = periodSet.get(m.period) ?? {};
      existing[line.name] = m.value;
      periodSet.set(m.period, existing);
    }
  }
  const data = [...periodSet.entries()]
    .map(([period, vals]) => ({ period, ...vals }))
    .reverse();

  return (
    <ResponsiveContainer width="100%" height={200}>
      <LineChart data={data} margin={{ top: 5, right: 5, bottom: 5, left: 5 }}>
        <XAxis dataKey="period" tick={{ fontSize: 10, fill: "var(--color-text-muted)" }} />
        <YAxis tick={{ fontSize: 10, fill: "var(--color-text-muted)" }} tickFormatter={(v) => `${v}${yAxisSuffix}`} width={45} />
        <Tooltip
          contentStyle={{ backgroundColor: "var(--color-surface)", border: "1px solid var(--color-border)", borderRadius: 8, fontSize: 11 }}
          formatter={(value) => [`${(value as number).toFixed(1)}${yAxisSuffix}`]}
        />
        <Legend wrapperStyle={{ fontSize: 10 }} />
        {referenceLine !== undefined && (
          <ReferenceLine y={referenceLine} stroke="var(--color-text-faint)" strokeDasharray="4 4" />
        )}
        {lines.map((line) => (
          <Line key={line.name} type="monotone" dataKey={line.name} stroke={line.color} strokeWidth={2} dot={{ r: 3 }} />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

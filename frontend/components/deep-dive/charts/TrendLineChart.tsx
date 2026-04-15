"use client";

import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend, ReferenceLine } from "recharts";
import type { QuarterlyMetric } from "@/lib/api";
import { formatUSD, formatNumber } from "@/lib/format";

interface TrendLine {
  data: QuarterlyMetric[];
  name: string;
  color: string;
}

interface TrendLineChartProps {
  lines: TrendLine[];
  yAxisSuffix?: string;
  referenceLine?: number;
  /** Tighten Y-axis to data range with small padding instead of including 0 */
  tightDomain?: boolean;
}

export function TrendLineChart({ lines, yAxisSuffix = "%", referenceLine, tightDomain }: TrendLineChartProps) {
  const periodSet = new Map<string, Record<string, number>>();
  for (const line of lines) {
    for (const m of line.data) {
      const existing = periodSet.get(m.period) ?? {};
      existing[line.name] = m.value;
      periodSet.set(m.period, existing);
    }
  }
  const data = [...periodSet.entries()]
    .map(([period, vals]) => ({ period, ...vals }) as Record<string, string | number>)
    .reverse();

  // Compute tight domain: pad 2% around [min, max] so trends are visible
  let yDomain: [number | string, number | string] | undefined;
  if (tightDomain && data.length > 0) {
    const keys = lines.map((l) => l.name);
    let min = Infinity;
    let max = -Infinity;
    for (const d of data) {
      for (const k of keys) {
        const v = d[k] as number | undefined;
        if (v != null) {
          if (v < min) min = v;
          if (v > max) max = v;
        }
      }
    }
    if (min !== Infinity) {
      const range = max - min || Math.abs(max) * 0.1 || 1;
      const pad = range * 0.15;
      yDomain = [min - pad, max + pad];
    }
  }

  // When no suffix is provided, caller is passing raw USD amounts — format
  // them compactly so the Y-axis shows $600M instead of 600000000.
  const isMoney = yAxisSuffix === "";
  const tickFmt = (v: number) =>
    isMoney ? formatUSD(v) : `${formatNumber(v, 1)}${yAxisSuffix}`;
  const tooltipFmt = (v: number) =>
    isMoney ? formatUSD(v) : `${formatNumber(v, 1)}${yAxisSuffix}`;

  return (
    <ResponsiveContainer width="100%" height={200}>
      <LineChart data={data} margin={{ top: 5, right: 5, bottom: 5, left: 5 }}>
        <XAxis dataKey="period" tick={{ fontSize: 10, fill: "var(--color-text-muted)" }} />
        <YAxis tick={{ fontSize: 10, fill: "var(--color-text-muted)" }} tickFormatter={(v) => tickFmt(v)} width={isMoney ? 60 : 48} domain={yDomain} />
        <Tooltip
          contentStyle={{ backgroundColor: "var(--color-surface)", border: "1px solid var(--color-border)", borderRadius: 8, fontSize: 11 }}
          formatter={(value) => [tooltipFmt(value as number)]}
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

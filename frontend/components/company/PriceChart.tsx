"use client";

import { useMemo, useState } from "react";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
} from "recharts";
import type { PricePoint } from "@/lib/api";

const RANGES = ["1M", "3M", "6M", "YTD", "1Y", "5Y"] as const;
type Range = (typeof RANGES)[number];

function cutoff(range: Range): Date {
  const now = new Date();
  switch (range) {
    case "1M": return new Date(now.getFullYear(), now.getMonth() - 1, now.getDate());
    case "3M": return new Date(now.getFullYear(), now.getMonth() - 3, now.getDate());
    case "6M": return new Date(now.getFullYear(), now.getMonth() - 6, now.getDate());
    case "YTD": return new Date(now.getFullYear(), 0, 1);
    case "1Y": return new Date(now.getFullYear() - 1, now.getMonth(), now.getDate());
    case "5Y": return new Date(now.getFullYear() - 5, now.getMonth(), now.getDate());
  }
}

export function PriceChart({ prices }: { prices: PricePoint[] }) {
  const [range, setRange] = useState<Range>("1Y");

  const data = useMemo(() => {
    const from = cutoff(range).toISOString().slice(0, 10);
    return prices.filter((p) => p.date >= from);
  }, [prices, range]);

  const first = data[0]?.close;
  const last = data[data.length - 1]?.close;
  const delta = first != null && last != null ? last - first : null;
  const pct = delta != null && first ? (delta / first) * 100 : null;
  const up = (delta ?? 0) >= 0;
  const stroke = up ? "var(--success,#16a34a)" : "var(--error,#dc2626)";

  if (prices.length === 0) {
    return (
      <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-6 text-sm text-[var(--text-muted)]">
        No price history available.
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="flex items-baseline gap-2">
          {last != null && (
            <span className="font-mono text-lg font-semibold text-[var(--text)]">
              ${last.toFixed(2)}
            </span>
          )}
          {delta != null && pct != null && (
            <span className="font-mono text-xs" style={{ color: stroke }}>
              {up ? "+" : ""}{delta.toFixed(2)} ({up ? "+" : ""}{pct.toFixed(2)}%) · {range}
            </span>
          )}
        </div>
        <div className="flex gap-1">
          {RANGES.map((r) => (
            <button
              key={r}
              onClick={() => setRange(r)}
              className={`rounded px-2 py-0.5 text-xs transition-colors ${
                r === range
                  ? "bg-[var(--accent-bg)] font-medium text-[var(--text)]"
                  : "text-[var(--text-muted)] hover:text-[var(--text)]"
              }`}
            >
              {r}
            </button>
          ))}
        </div>
      </div>
      <ResponsiveContainer width="100%" height={280}>
        <LineChart data={data} margin={{ top: 5, right: 8, bottom: 5, left: 8 }}>
          <XAxis
            dataKey="date"
            tick={{ fontSize: 10, fill: "var(--text-muted)" }}
            minTickGap={40}
            tickFormatter={(d) => (d as string).slice(0, 7)}
          />
          <YAxis
            domain={["auto", "auto"]}
            tick={{ fontSize: 10, fill: "var(--text-muted)" }}
            width={48}
            tickFormatter={(v) => `$${(v as number).toFixed(0)}`}
          />
          <Tooltip
            contentStyle={{ fontSize: 12, background: "var(--surface)", border: "1px solid var(--border)" }}
            formatter={(value) => [`$${(value as number).toFixed(2)}`, "Close"]}
          />
          <Line type="monotone" dataKey="close" stroke={stroke} dot={false} strokeWidth={1.5} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

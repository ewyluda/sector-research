"use client";

import { useEffect, useId, useState } from "react";
import {
  Area,
  AreaChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import type { SignalHistoryPoint } from "@/lib/api";
import { getSignalHistory } from "@/lib/api";

type Direction = "accelerating" | "stable" | "decelerating" | "unknown" | null;

interface VelocityShape {
  direction: Direction;
  ratio: number | null;
  is_stale: boolean;
}

interface DirectionConfig {
  arrow: string;
  pillBg: string;
  pillFg: string;
  pillBorder: string;
  chartLine: string;
  chartFill: string;
}

const DIRECTION_CONFIG: Record<Exclude<Direction, "unknown" | null>, DirectionConfig> = {
  accelerating: {
    arrow: "↑",
    pillBg: "bg-emerald-50",
    pillFg: "text-emerald-700",
    pillBorder: "border-emerald-200",
    chartLine: "#10b981",
    chartFill: "#10b981",
  },
  stable: {
    arrow: "→",
    pillBg: "bg-[var(--surface-alt)]",
    pillFg: "text-[var(--text-muted)]",
    pillBorder: "border-[var(--border)]",
    chartLine: "#7A7974",
    chartFill: "#7A7974",
  },
  decelerating: {
    arrow: "↓",
    pillBg: "bg-amber-50",
    pillFg: "text-amber-700",
    pillBorder: "border-amber-200",
    chartLine: "#d97706",
    chartFill: "#d97706",
  },
};

interface VelocitySparklineProps {
  velocity: VelocityShape;
  /** When set together with `ticker`, the component fetches signal_history and renders a real sparkline. */
  themeId?: string;
  ticker?: string;
  days?: number;
  width?: number;
  height?: number;
}

interface ChartPoint {
  t: number;
  date: string;
  ratio: number;
}

export function VelocitySparkline({
  velocity,
  themeId,
  ticker,
  days = 30,
  width = 96,
  height = 24,
}: VelocitySparklineProps) {
  const [data, setData] = useState<ChartPoint[] | null>(null);

  useEffect(() => {
    if (!themeId || !ticker) return;
    let cancelled = false;
    getSignalHistory(themeId, ticker, { signalType: "velocity", days })
      .then((res) => {
        if (cancelled) return;
        const points: ChartPoint[] = res.points
          .map((p: SignalHistoryPoint): ChartPoint | null => {
            const ratio = p.value?.["ratio"];
            if (typeof ratio !== "number" || !Number.isFinite(ratio)) return null;
            const t = new Date(p.computed_at).getTime();
            if (Number.isNaN(t)) return null;
            return { t, date: p.computed_at, ratio };
          })
          .filter((p): p is ChartPoint => p !== null)
          .sort((a, b) => a.t - b.t);
        setData(points);
      })
      .catch(() => {
        if (!cancelled) setData([]);
      });
    return () => {
      cancelled = true;
    };
  }, [themeId, ticker, days]);

  if (!velocity.direction || velocity.direction === "unknown" || velocity.ratio == null) {
    return null;
  }
  const config = DIRECTION_CONFIG[velocity.direction];
  const ratioDisplay = velocity.ratio.toFixed(2);
  const hasHistory = data !== null && data.length >= 2;
  const dimmed = velocity.is_stale ? "opacity-50" : "";

  return (
    <div className={`inline-flex items-center gap-2 ${dimmed}`}>
      <div
        className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border ${config.pillBg} ${config.pillBorder}`}
      >
        <span className={`text-xs font-semibold ${config.pillFg}`}>{config.arrow}</span>
        <span className={`text-[10px] font-mono font-medium tabular-nums ${config.pillFg}`}>
          {ratioDisplay}x
        </span>
        {velocity.is_stale && (
          <span
            className="text-[9px] text-[var(--text-faint)] uppercase tracking-wide"
            title="Signal data is stale (>36h old)"
          >
            stale
          </span>
        )}
      </div>

      {hasHistory && (
        <Sparkline
          data={data!}
          config={config}
          width={width}
          height={height}
        />
      )}
    </div>
  );
}

function Sparkline({
  data,
  config,
  width,
  height,
}: {
  data: ChartPoint[];
  config: DirectionConfig;
  width: number;
  height: number;
}) {
  // Per-instance id; previously color-derived, which collided across
  // multiple same-direction sparklines on the same page.
  const reactId = useId();
  const gradientId = `velocity-spark-${reactId.replace(/[^a-z0-9]/gi, "")}`;

  return (
    <div style={{ width, height }} aria-hidden="true">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 2, right: 0, bottom: 2, left: 0 }}>
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={config.chartFill} stopOpacity={0.18} />
              <stop offset="100%" stopColor={config.chartFill} stopOpacity={0} />
            </linearGradient>
          </defs>
          <ReferenceLine
            y={1}
            stroke="var(--text-faint)"
            strokeDasharray="2 2"
            strokeWidth={0.5}
            ifOverflow="extendDomain"
          />
          <Area
            type="monotone"
            dataKey="ratio"
            stroke={config.chartLine}
            strokeWidth={1.5}
            fill={`url(#${gradientId})`}
            dot={false}
            activeDot={{ r: 2.5, strokeWidth: 0, fill: config.chartLine }}
            isAnimationActive={false}
          />
          <Tooltip
            cursor={false}
            wrapperStyle={{ outline: "none", zIndex: 50 }}
            content={({ active, payload }) => {
              if (!active || !payload?.[0]) return null;
              const datum = payload[0].payload as ChartPoint;
              const dateLabel = new Date(datum.date).toLocaleDateString(undefined, {
                month: "short",
                day: "numeric",
              });
              return (
                <div
                  style={{
                    backgroundColor: "var(--surface)",
                    border: "1px solid var(--border)",
                    borderRadius: 6,
                    padding: "4px 8px",
                    boxShadow: "0 2px 10px rgba(40, 37, 29, 0.08)",
                    color: "var(--text)",
                    fontSize: 10,
                    fontVariantNumeric: "tabular-nums",
                    whiteSpace: "nowrap",
                  }}
                >
                  <span
                    style={{
                      fontFamily: "ui-monospace, SFMono-Regular, monospace",
                      fontWeight: 600,
                      color: config.chartLine,
                    }}
                  >
                    {datum.ratio.toFixed(2)}x
                  </span>
                  <span style={{ color: "var(--text-muted)", marginLeft: 6 }}>{dateLabel}</span>
                </div>
              );
            }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

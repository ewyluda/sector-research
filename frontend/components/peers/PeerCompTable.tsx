"use client";

import type { PeerCompTable as PeerCompTableData, PeerCompRow } from "@/lib/api";
import { fmtMarketCap } from "@/lib/api";

type MetricKey = Exclude<keyof PeerCompRow, "ticker">;
type Kind = "multiple" | "pct" | "money";
type Better = "low" | "high" | null;

interface MetricDef { key: MetricKey; label: string; kind: Kind; better: Better }

const GROUPS: { label: string; metrics: MetricDef[] }[] = [
  {
    label: "Valuation",
    metrics: [
      { key: "pe", label: "P/E", kind: "multiple", better: "low" },
      { key: "ev_ebitda", label: "EV/EBITDA", kind: "multiple", better: "low" },
      { key: "p_b", label: "P/B", kind: "multiple", better: "low" },
      { key: "p_fcf", label: "P/FCF", kind: "multiple", better: "low" },
      { key: "p_s", label: "P/S", kind: "multiple", better: "low" },
      { key: "peg", label: "PEG", kind: "multiple", better: "low" },
    ],
  },
  {
    label: "Growth",
    metrics: [
      { key: "revenue_yoy", label: "Rev YoY", kind: "pct", better: "high" },
      { key: "eps_yoy", label: "EPS YoY", kind: "pct", better: "high" },
    ],
  },
  {
    label: "Margins",
    metrics: [
      { key: "gross_margin", label: "Gross", kind: "pct", better: "high" },
      { key: "operating_margin", label: "Oper", kind: "pct", better: "high" },
      { key: "ebitda_margin", label: "EBITDA", kind: "pct", better: "high" },
      { key: "fcf_margin", label: "FCF", kind: "pct", better: "high" },
    ],
  },
  {
    label: "Returns",
    metrics: [
      { key: "roe", label: "ROE", kind: "pct", better: "high" },
      { key: "roic", label: "ROIC", kind: "pct", better: "high" },
      { key: "roa", label: "ROA", kind: "pct", better: "high" },
    ],
  },
  {
    label: "",
    metrics: [
      // Context only — no best-in-class judgment on size.
      { key: "market_cap", label: "Mkt Cap", kind: "money", better: null },
    ],
  },
];

const ALL_METRICS: MetricDef[] = GROUPS.flatMap((g) => g.metrics);

function fmtValue(v: number | null, kind: Kind): string {
  if (v == null || Number.isNaN(v)) return "—";
  if (kind === "pct") return `${(v * 100).toFixed(1)}%`;
  if (kind === "money") return fmtMarketCap(v);
  return `${v.toFixed(1)}x`;
}

/** Per-metric best value across the displayed company rows (focus + peers). */
function bestValues(rows: PeerCompRow[]): Partial<Record<MetricKey, number>> {
  const best: Partial<Record<MetricKey, number>> = {};
  for (const m of ALL_METRICS) {
    if (!m.better) continue;
    const vals = rows.map((r) => r[m.key]).filter((v): v is number => v != null);
    if (vals.length === 0) continue;
    best[m.key] = m.better === "low" ? Math.min(...vals) : Math.max(...vals);
  }
  return best;
}

export function PeerCompTable({ table }: { table: PeerCompTableData }) {
  const focus = table.focus_ticker;
  const companyRows = [
    ...table.rows.filter((r) => r.ticker === focus),
    ...table.rows.filter((r) => r.ticker !== focus),
  ];
  const best = bestValues(companyRows);

  const cell = (row: PeerCompRow, m: MetricDef) => {
    const v = row[m.key];
    const isBest = m.better != null && v != null && v === best[m.key];
    return (
      <td
        key={m.key}
        className={`text-right py-1.5 px-2 tabular-nums ${
          isBest ? "text-[var(--success)] font-semibold" : "text-[var(--text)]"
        }`}
      >
        {fmtValue(v, m.kind)}
      </td>
    );
  };

  return (
    <div className="overflow-x-auto rounded-lg border border-[var(--border)]">
      <table className="w-full text-xs border-collapse">
        <thead>
          <tr className="border-b border-[var(--border)]">
            <th className="sticky left-0 bg-[var(--surface)] z-10" />
            {GROUPS.map((g) => (
              <th
                key={g.label || "context"}
                colSpan={g.metrics.length}
                className="py-1 px-2 text-center text-[10px] uppercase tracking-wide text-[var(--text-muted)] border-l border-[var(--border)]"
              >
                {g.label}
              </th>
            ))}
          </tr>
          <tr className="border-b border-[var(--border)]">
            <th className="sticky left-0 bg-[var(--surface)] text-left py-1.5 px-2 font-semibold text-[var(--text-muted)] z-10">
              Ticker
            </th>
            {GROUPS.map((g) =>
              g.metrics.map((m, i) => (
                <th
                  key={m.key}
                  className={`text-right py-1.5 px-2 font-semibold text-[var(--text-muted)] whitespace-nowrap ${
                    i === 0 ? "border-l border-[var(--border)]" : ""
                  }`}
                >
                  {m.label}
                </th>
              ))
            )}
          </tr>
        </thead>
        <tbody>
          {companyRows.map((row) => {
            const isFocus = row.ticker === focus;
            return (
              <tr
                key={row.ticker}
                className={`border-b border-[var(--border)] ${
                  isFocus ? "bg-[var(--accent-bg)] font-semibold" : ""
                }`}
              >
                <td
                  className={`sticky left-0 z-10 text-left py-1.5 px-2 ${
                    isFocus
                      ? "bg-[var(--accent-bg)] text-[var(--primary)]"
                      : "bg-[var(--surface)] text-[var(--text)]"
                  }`}
                >
                  {row.ticker}
                </td>
                {ALL_METRICS.map((m) => cell(row, m))}
              </tr>
            );
          })}

          {/* Median footer */}
          <tr className="border-b border-[var(--border)] bg-[var(--surface-alt)]">
            <td className="sticky left-0 bg-[var(--surface-alt)] z-10 text-left py-1.5 px-2 font-medium text-[var(--text-muted)]">
              Peer median
            </td>
            {ALL_METRICS.map((m) => (
              <td
                key={m.key}
                className="text-right py-1.5 px-2 tabular-nums text-[var(--text-muted)]"
              >
                {fmtValue(table.median[m.key], m.kind)}
              </td>
            ))}
          </tr>

          {/* Δ vs median — relative delta computed backend-side; green/red signals direction
              only. The best-in-class tint on company rows above is the judgment layer. */}
          <tr>
            <td className="sticky left-0 bg-[var(--surface)] z-10 text-left py-1.5 px-2 font-medium text-[var(--text-muted)]">
              Δ vs median
            </td>
            {ALL_METRICS.map((m) => {
              const d = table.delta_vs_median_pct[m.key];
              const color =
                d == null
                  ? "text-[var(--text-muted)]"
                  : d > 0
                    ? "text-[var(--success)]"
                    : "text-[var(--error)]";
              return (
                <td key={m.key} className={`text-right py-1.5 px-2 tabular-nums ${color}`}>
                  {d == null ? "—" : `${d > 0 ? "+" : ""}${d.toFixed(1)}%`}
                </td>
              );
            })}
          </tr>
        </tbody>
      </table>
    </div>
  );
}

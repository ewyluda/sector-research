"use client";

import { useMemo } from "react";
import type { SupplyChainGraph } from "@/lib/api";
import { buildConcentrationFlow } from "@/lib/concentrationFlow";
import type { FlowBand } from "@/lib/concentrationFlow";
import { REL_TYPE_COLORS } from "@/lib/themeGraph";

// ── Visual constants ───────────────────────────────────────────────────────────

const SUPPLIER_COLOR = REL_TYPE_COLORS.supplier; // "#34d399"
const CUSTOMER_COLOR = REL_TYPE_COLORS.customer; // "#60a5fa"
const OTHER_FILL = "rgba(156,163,175,0.18)";       // muted gray at low opacity

const SVG_WIDTH = 480;
const SVG_HEIGHT_PER_BAND = 30;
const SVG_MIN_HEIGHT = 80;
const SVG_PADDING_Y = 20;

// Column x-positions
const BAND_WIDTH = 120;
const COMPANY_NODE_W = 80;
const COMPANY_NODE_H = 32;
const COL_LEFT_X = 0;
const COL_RIGHT_X = SVG_WIDTH - BAND_WIDTH;
const COMPANY_X = (SVG_WIDTH - COMPANY_NODE_W) / 2;

// ── Helpers ────────────────────────────────────────────────────────────────────

function bandColor(band: FlowBand): string {
  if (band.isOther) return OTHER_FILL;
  return band.side === "supplier" ? SUPPLIER_COLOR : CUSTOMER_COLOR;
}

function bandOpacity(band: FlowBand): number {
  return band.isOther ? 1 : 0.8;
}

/**
 * Compute per-band rect y-positions given a list of bands and available height.
 * Distributes bands evenly with a small gap.
 */
function computeBandRects(
  bands: FlowBand[],
  totalHeight: number,
): { y: number; h: number }[] {
  if (bands.length === 0) return [];
  const gap = 4;
  const totalGap = gap * (bands.length - 1);
  const totalPct = bands.reduce((s, b) => s + b.pct, 0);
  const available = totalHeight - totalGap;

  let cursor = 0;
  return bands.map((b) => {
    const h = Math.max(16, (b.pct / totalPct) * available);
    const rect = { y: cursor, h };
    cursor += h + gap;
    return rect;
  });
}

/**
 * Cubic bezier ribbon from a band rect on one side to the company node center.
 * For suppliers (left side): ribbon flows left → center.
 * For customers (right side): ribbon flows center → right.
 */
function ribbonPath(
  side: "supplier" | "customer",
  bandX: number,
  bandY: number,
  bandH: number,
  companyY: number,
  companyH: number,
  pct: number,
  totalPct: number,
  svgH: number,
): string {
  const thickness = Math.max(3, (pct / totalPct) * companyH * 0.9);
  const companyMidY = companyY + companyH / 2;
  const halfThick = thickness / 2;

  if (side === "supplier") {
    // Band is on left; ribbon goes right toward company left edge.
    const bx1 = bandX + BAND_WIDTH;
    const bTop = bandY;
    const bBot = bandY + bandH;
    const cx = COMPANY_X;
    const cTop = companyMidY - halfThick;
    const cBot = companyMidY + halfThick;
    const mid = (bx1 + cx) / 2;
    return [
      `M ${bx1} ${bTop}`,
      `C ${mid} ${bTop}, ${mid} ${cTop}, ${cx} ${cTop}`,
      `L ${cx} ${cBot}`,
      `C ${mid} ${cBot}, ${mid} ${bBot}, ${bx1} ${bBot}`,
      `Z`,
    ].join(" ");
  } else {
    // Band is on right; ribbon goes left toward company right edge.
    const bx1 = COL_RIGHT_X;
    const bTop = bandY;
    const bBot = bandY + bandH;
    const cx = COMPANY_X + COMPANY_NODE_W;
    const cTop = companyMidY - halfThick;
    const cBot = companyMidY + halfThick;
    const mid = (cx + bx1) / 2;
    return [
      `M ${cx} ${cTop}`,
      `C ${mid} ${cTop}, ${mid} ${bTop}, ${bx1} ${bTop}`,
      `L ${bx1} ${bBot}`,
      `C ${mid} ${bBot}, ${mid} ${cBot}, ${cx} ${cBot}`,
      `Z`,
    ].join(" ");
  }

  void svgH; // unused but keeps signature consistent for future use
}

// ── Band SVG column ────────────────────────────────────────────────────────────

function BandColumn({
  bands,
  side,
  svgH,
  companyY,
  companyH,
}: {
  bands: FlowBand[];
  side: "supplier" | "customer";
  svgH: number;
  companyY: number;
  companyH: number;
}) {
  const rects = computeBandRects(bands, svgH - SVG_PADDING_Y * 2);
  const xBase = side === "supplier" ? COL_LEFT_X : COL_RIGHT_X;
  const totalPct = bands.reduce((s, b) => s + b.pct, 0);

  return (
    <>
      {bands.map((band, i) => {
        const { y: ry, h: rh } = rects[i];
        const absY = ry + SVG_PADDING_Y;
        const color = bandColor(band);
        const opacity = bandOpacity(band);
        const tooltip = band.isOther
          ? "Other / undisclosed"
          : [
              band.quote ? `"${band.quote}"` : null,
              band.filingDate ? `Filing: ${band.filingDate}` : null,
            ]
              .filter(Boolean)
              .join(" · ") || band.label;

        return (
          <g key={i}>
            {/* Ribbon */}
            <path
              d={ribbonPath(
                side,
                xBase,
                absY,
                rh,
                companyY,
                companyH,
                band.pct,
                totalPct,
                svgH,
              )}
              fill={color}
              opacity={opacity * 0.5}
            />
            {/* Band rect */}
            <rect
              x={xBase}
              y={absY}
              width={BAND_WIDTH}
              height={rh}
              rx={3}
              fill={color}
              opacity={opacity}
            />
            {/* Label text */}
            <text
              x={side === "supplier" ? xBase + 4 : xBase + BAND_WIDTH - 4}
              y={absY + rh / 2}
              dominantBaseline="middle"
              textAnchor={side === "supplier" ? "start" : "end"}
              fontSize={9}
              fill="var(--color-text-primary)"
              opacity={0.9}
            >
              {band.label.length > 14 ? `${band.label.slice(0, 13)}…` : band.label}
            </text>
            {/* Pct text */}
            <text
              x={
                side === "supplier"
                  ? xBase + BAND_WIDTH - 4
                  : xBase + 4
              }
              y={absY + rh / 2}
              dominantBaseline="middle"
              textAnchor={side === "supplier" ? "end" : "start"}
              fontSize={9}
              fontFamily="monospace"
              fill="var(--color-text-muted)"
            >
              {band.pct}%
            </text>
            <title>{tooltip}</title>
          </g>
        );
      })}
    </>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

interface Props {
  graph: SupplyChainGraph;
}

export function ConcentrationFlow({ graph }: Props) {
  const data = useMemo(
    () => buildConcentrationFlow(graph.nodes, graph.edges),
    [graph],
  );

  // Self-hide when not enough data — mirrors RPOTrend prior art.
  if (!data.eligible) return null;

  const maxBands = Math.max(data.suppliers.length, data.customers.length, 1);
  const svgH = Math.max(
    SVG_MIN_HEIGHT,
    maxBands * SVG_HEIGHT_PER_BAND + SVG_PADDING_Y * 2,
  );

  const companyY = svgH / 2 - COMPANY_NODE_H / 2;

  return (
    <div className="space-y-2">
      <div>
        <h4 className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
          Disclosed concentration
        </h4>
        <p className="text-[10px] text-[var(--color-text-muted)] leading-relaxed">
          % of cost (suppliers) / revenue (customers) from the latest filing
          that quantifies concentration.
        </p>
      </div>

      <div className="rounded border border-[var(--color-border)] bg-[var(--color-bg)]/40 overflow-hidden">
        <svg
          viewBox={`0 0 ${SVG_WIDTH} ${svgH}`}
          width="100%"
          height={svgH}
          aria-label="Supplier and customer concentration flow"
        >
          {/* Supplier bands */}
          <BandColumn
            bands={data.suppliers}
            side="supplier"
            svgH={svgH}
            companyY={companyY}
            companyH={COMPANY_NODE_H}
          />

          {/* Customer bands */}
          <BandColumn
            bands={data.customers}
            side="customer"
            svgH={svgH}
            companyY={companyY}
            companyH={COMPANY_NODE_H}
          />

          {/* Company node (center) */}
          <rect
            x={COMPANY_X}
            y={companyY}
            width={COMPANY_NODE_W}
            height={COMPANY_NODE_H}
            rx={6}
            fill="var(--color-surface)"
            stroke="var(--color-border)"
            strokeWidth={1.5}
          />
          <text
            x={COMPANY_X + COMPANY_NODE_W / 2}
            y={companyY + COMPANY_NODE_H / 2}
            dominantBaseline="middle"
            textAnchor="middle"
            fontSize={11}
            fontWeight={600}
            fill="var(--color-text-primary)"
          >
            {graph.root_ticker}
          </text>

          {/* Side labels */}
          {data.suppliers.length > 0 && (
            <text
              x={COL_LEFT_X + BAND_WIDTH / 2}
              y={6}
              textAnchor="middle"
              fontSize={8}
              fill="var(--color-text-muted)"
              fontWeight={600}
            >
              SUPPLIERS
            </text>
          )}
          {data.customers.length > 0 && (
            <text
              x={COL_RIGHT_X + BAND_WIDTH / 2}
              y={6}
              textAnchor="middle"
              fontSize={8}
              fill="var(--color-text-muted)"
              fontWeight={600}
            >
              CUSTOMERS
            </text>
          )}
        </svg>
      </div>
    </div>
  );
}

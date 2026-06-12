"use client";

import { useMemo } from "react";
import type { SupplyChainGraph } from "@/lib/api";
import { buildConcentrationFlow, computeBandHeights } from "@/lib/concentrationFlow";
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

const BAND_GAP = 4;

/**
 * Stack band rects top-to-bottom.
 * Heights are provided by computeBandHeights (lib); this function only adds y
 * positions. Keeping y-stacking here (render layer) and height math in the lib
 * (node-testable) follows the house pattern.
 */
function stackBandRects(heights: number[]): { y: number; h: number }[] {
  let cursor = 0;
  return heights.map((h) => {
    const rect = { y: cursor, h };
    cursor += h + BAND_GAP;
    return rect;
  });
}

/**
 * Derive the column content height (excluding padding) from actual stacked band
 * heights so bands never overflow: sum of heights + gaps between them.
 */
function columnContentHeight(heights: number[]): number {
  if (heights.length === 0) return 0;
  return heights.reduce((s, h) => s + h, 0) + BAND_GAP * (heights.length - 1);
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
}

// ── Band SVG column ────────────────────────────────────────────────────────────

function BandColumn({
  bands,
  side,
  rects,
  companyY,
  companyH,
}: {
  bands: FlowBand[];
  side: "supplier" | "customer";
  rects: { y: number; h: number }[];
  companyY: number;
  companyH: number;
}) {
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

        // Never truncate the two fixed-width generic labels; widen truncation
        // to 20 chars for arbitrary counterparty names.
        const isGenericLabel =
          band.label === "Undisclosed supplier" ||
          band.label === "Undisclosed customer" ||
          band.label === "Other / undisclosed";
        const displayLabel = isGenericLabel
          ? band.label
          : band.label.length > 20
            ? `${band.label.slice(0, 19)}…`
            : band.label;

        const pctStr =
          band.pct % 1 === 0
            ? band.pct.toFixed(0)
            : band.pct.toFixed(1);

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
              {displayLabel}
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
              {pctStr}%
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

  // Derive svg height from actual stacked band heights — prevents overflow on
  // skewed distributions (e.g. [90,8,2]) where the 16px floor pushes cumulative
  // height past any fixed proportional budget.
  const supplierHeights = computeBandHeights(
    data.suppliers.map((b) => b.pct),
    SVG_HEIGHT_PER_BAND * Math.max(data.suppliers.length, 1),
  );
  const customerHeights = computeBandHeights(
    data.customers.map((b) => b.pct),
    SVG_HEIGHT_PER_BAND * Math.max(data.customers.length, 1),
  );

  const supplierContent = columnContentHeight(supplierHeights);
  const customerContent = columnContentHeight(customerHeights);
  const svgH = Math.max(
    SVG_MIN_HEIGHT,
    Math.max(supplierContent, customerContent) + SVG_PADDING_Y * 2,
  );

  const supplierRects = stackBandRects(supplierHeights);
  const customerRects = stackBandRects(customerHeights);

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
            rects={supplierRects}
            companyY={companyY}
            companyH={COMPANY_NODE_H}
          />

          {/* Customer bands */}
          <BandColumn
            bands={data.customers}
            side="customer"
            rects={customerRects}
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

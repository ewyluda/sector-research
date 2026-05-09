"use client";
import Link from "next/link";
import type { ValidationOutput } from "@/lib/api";
// Shape transforms are needed because api.ts has two SensitivityGrid interfaces
// (model: x_dim/x_values and workspace: dim_x/x_axis) and two ThesisVsPriced shapes.
// SensitivityHeatmap accesses x_dim, y_dim, x_values, y_values at runtime.
// ThesisVsPricedTable accesses dimension, thesis, priced_in, delta at runtime.
// We cast to `any` to bridge the shapes without modifying the model components.
import { SensitivityHeatmap } from "@/components/model/SensitivityHeatmap";
import { ThesisVsPricedTable } from "@/components/model/ThesisVsPricedTable";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function toModelGrid(g: ValidationOutput["sensitivity_grids"][number]): any {
  return {
    x_dim: g.dim_x,
    y_dim: g.dim_y,
    x_values: g.x_axis,
    y_values: g.y_axis,
    values: g.values,
  };
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function toModelThesisRows(rows: ValidationOutput["thesis_vs_priced_in"]): any[] {
  return rows.map((r) => ({
    dimension: r.metric,
    thesis: r.thesis_value,
    priced_in: r.priced_in_value,
    delta: r.delta_pct,
  }));
}

export function ValidationCard({
  output,
  ticker,
}: {
  output: ValidationOutput;
  ticker: string;
}) {
  const irr = output.implied_irr;

  return (
    <div className="space-y-4 mt-2">
      {/* Header: current price + implied IRR */}
      <div className="flex items-baseline gap-4">
        <span className="text-sm text-slate-300">
          Price{" "}
          <span className="font-semibold text-slate-100">
            ${output.current_price.toFixed(2)}
          </span>
        </span>
        {irr != null && (
          <span className="text-sm text-slate-300">
            Implied IRR{" "}
            <span
              className={`font-semibold ${irr >= 0 ? "text-green-400" : "text-red-400"}`}
            >
              {(irr * 100).toFixed(1)}%
            </span>
          </span>
        )}
      </div>

      {/* Implied-driver cards */}
      {output.implied_drivers.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {output.implied_drivers.map((d) => (
            <div
              key={d.dimension}
              className="rounded border border-slate-700 bg-slate-900/50 p-3"
            >
              <div className="text-xs text-slate-400 mb-1">{d.dimension}</div>
              <div className="text-lg font-semibold text-slate-100">
                {(d.implied_value * 100).toFixed(1)}%
              </div>
              <div className="text-xs text-slate-500">
                baseline {(d.baseline_value * 100).toFixed(1)}%
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Thesis vs priced-in table */}
      {output.thesis_vs_priced_in.length > 0 && (
        <div className="rounded border border-slate-700 bg-slate-900/50 p-3">
          <div className="text-xs font-medium text-slate-400 mb-2">
            Thesis vs. Priced In
          </div>
          <ThesisVsPricedTable rows={toModelThesisRows(output.thesis_vs_priced_in)} />
        </div>
      )}

      {/* Sensitivity heatmaps */}
      {output.sensitivity_grids.length > 0 && (
        <div className="rounded border border-slate-700 bg-slate-900/50 p-3">
          <div className="text-xs font-medium text-slate-400 mb-3">
            Sensitivity Grids
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 overflow-x-auto">
            {output.sensitivity_grids.map((g, i) => (
              <SensitivityHeatmap
                key={i}
                grid={toModelGrid(g)}
                currentPrice={output.current_price}
              />
            ))}
          </div>
        </div>
      )}

      {/* Footer link */}
      <div className="text-xs text-slate-500">
        <Link
          href={`/model/${ticker}#reverse-dcf`}
          className="underline hover:text-slate-300"
        >
          Open full reverse-DCF →
        </Link>
      </div>
    </div>
  );
}

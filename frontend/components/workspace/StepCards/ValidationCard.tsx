"use client";
import Link from "next/link";
import type { ValidationOutput, WorkspaceSensitivityGrid } from "@/lib/api";
// Shape transforms: WorkspaceSensitivityGrid (dim_x/x_axis) → model SensitivityGrid (x_dim/x_values)
// required by SensitivityHeatmap. ThesisVsPricedTable expects dimension/thesis/priced_in/delta.
// We cast to `any` to bridge shapes without modifying the shared model components.
//
// Note: if the heatmap renders as solid red, it means all DCF-implied per-share values
// are below the current market price — the model sees the stock as overvalued at every
// parameter combination. This is correct behavior, not a rendering bug.
import { SensitivityHeatmap } from "@/components/model/SensitivityHeatmap";
import { ThesisVsPricedTable } from "@/components/model/ThesisVsPricedTable";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function toModelGrid(g: WorkspaceSensitivityGrid): any {
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
  const noModel = output.current_price === 0;

  if (noModel) {
    return (
      <div className="mt-2 text-xs text-[var(--text-muted)]">
        No financial model — validation skipped.
      </div>
    );
  }

  return (
    <div className="space-y-4 mt-2">
      {/* Header: current price + implied IRR */}
      <div className="flex items-baseline gap-4">
        <span className="text-sm text-[var(--text-muted)]">
          Price{" "}
          <span className="font-semibold text-[var(--text)]">
            ${output.current_price.toFixed(2)}
          </span>
        </span>
        {irr != null && (
          <span className="text-sm text-[var(--text-muted)]">
            Implied IRR{" "}
            <span
              className={`font-semibold ${irr >= 0 ? "text-[var(--success)]" : "text-[var(--error)]"}`}
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
              className="rounded border border-[var(--border)] bg-[var(--surface)] p-3"
            >
              <div className="text-xs text-[var(--text-muted)] mb-1">{d.dimension}</div>
              <div className="text-lg font-semibold text-[var(--text)]">
                {(d.implied_value * 100).toFixed(1)}%
              </div>
              <div className="text-xs text-[var(--text-faint)]">
                baseline {(d.baseline_value * 100).toFixed(1)}%
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Thesis vs priced-in table */}
      {output.thesis_vs_priced_in.length > 0 && (
        <div className="rounded border border-[var(--border)] bg-[var(--surface)] p-3">
          <div className="text-xs font-medium text-[var(--text-muted)] mb-2">
            Thesis vs. Priced In
          </div>
          <ThesisVsPricedTable rows={toModelThesisRows(output.thesis_vs_priced_in)} />
        </div>
      )}

      {/* Sensitivity heatmaps */}
      {output.sensitivity_grids.length > 0 && (
        <div className="rounded border border-[var(--border)] bg-[var(--surface)] p-3">
          <div className="text-xs font-medium text-[var(--text-muted)] mb-3">
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
      <div className="text-xs text-[var(--text-faint)]">
        <Link
          href={`/model/${ticker}#reverse-dcf`}
          className="underline hover:text-[var(--text-muted)]"
        >
          Open full reverse-DCF →
        </Link>
      </div>
    </div>
  );
}

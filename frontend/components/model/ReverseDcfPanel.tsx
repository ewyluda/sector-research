"use client";
import { useEffect, useState } from "react";
import { getReverseDcf, type ReverseDcfResponse } from "@/lib/api";
import { ThesisVsPricedTable, NO_SOLUTION_NOTE } from "./ThesisVsPricedTable";
import { SensitivityHeatmap } from "./SensitivityHeatmap";
import { WhatIfScratchPanel } from "./WhatIfScratchPanel";

export function ReverseDcfPanel({ ticker, hasDraft }: { ticker: string; hasDraft: boolean }) {
  const [data, setData] = useState<ReverseDcfResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [priceOverride, setPriceOverride] = useState<string>("");
  const [fromDraft, setFromDraft] = useState(false);

  async function load() {
    setErr(null);
    try {
      const opts: { price?: number; from_draft?: boolean } = {};
      if (priceOverride) opts.price = Number(priceOverride);
      if (fromDraft) opts.from_draft = true;
      const r = await getReverseDcf(ticker, opts);
      setData(r);
    } catch (e) {
      setErr(String(e));
    }
  }
  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ticker]);

  if (err) return <div className="p-6 text-[var(--error)]">Error: {err}</div>;
  if (!data) return <div className="p-6 text-[var(--text-muted)]">Loading reverse DCF&hellip;</div>;
  return (
    <div className="p-6 space-y-6 text-[var(--text)]">
      <div className="flex gap-3 items-center text-sm" data-print-hide="true">
        <label className="text-[var(--text-muted)]">
          Price override:{" "}
          <input
            value={priceOverride}
            onChange={(e) => setPriceOverride(e.target.value)}
            className="bg-[var(--surface)] border border-[var(--border)] text-[var(--text)] rounded px-2 py-0.5 w-24"
          />
        </label>
        {hasDraft && (
          <label className="text-[var(--text-muted)]">
            <input type="checkbox" checked={fromDraft} onChange={(e) => setFromDraft(e.target.checked)} /> Use draft
          </label>
        )}
        <button onClick={load} className="px-3 py-0.5 rounded-md bg-[var(--primary)] hover:bg-[var(--primary-dk)] text-white text-sm">
          Recompute
        </button>
      </div>

      <section className="grid grid-cols-2 gap-6">
        <div>
          <div className="text-xs uppercase tracking-wide text-[var(--text-muted)]">Implied IRR</div>
          <div
            className="text-4xl font-semibold text-[var(--text)]"
            title={data.implied_irr === null ? NO_SOLUTION_NOTE : undefined}
          >
            {data.implied_irr === null ? "—" : `${(data.implied_irr * 100).toFixed(2)}%`}
          </div>
          <div className="text-xs text-[var(--text-muted)] mt-1">
            at {data.price_used.toFixed(2)} ({data.price_source})
          </div>
        </div>
        <div>
          <div className="text-xs uppercase tracking-wide text-[var(--text-muted)] mb-1">Thesis vs priced in</div>
          <ThesisVsPricedTable rows={data.thesis_vs_priced_in} showFootnote={false} />
        </div>
        {(data.implied_irr === null ||
          data.thesis_vs_priced_in.some((r) => r.priced_in == null || r.delta == null)) && (
          <p className="col-span-2 text-xs text-[var(--text-muted)]">— = {NO_SOLUTION_NOTE}</p>
        )}
      </section>

      <section>
        <h2 className="text-sm font-semibold text-[var(--text)] mb-2">Sensitivity grids</h2>
        <div className="grid grid-cols-3 gap-6">
          <SensitivityHeatmap grid={data.sensitivity_grids.growth_margin} currentPrice={data.price_used} />
          <SensitivityHeatmap grid={data.sensitivity_grids.growth_multiple} currentPrice={data.price_used} />
          <SensitivityHeatmap grid={data.sensitivity_grids.margin_multiple} currentPrice={data.price_used} />
        </div>
      </section>

      <section>
        <h2 className="text-sm font-semibold text-[var(--text)] mb-2">What-if (illustrative)</h2>
        <WhatIfScratchPanel
          baseline={{
            growth: data.thesis_vs_priced_in.find((r) => r.dimension === "revenue_growth_pct")?.thesis ?? 0.05,
            margin: data.thesis_vs_priced_in.find((r) => r.dimension === "ebit_margin_pct")?.thesis ?? 0.20,
            multiple: data.thesis_vs_priced_in.find((r) => r.dimension === "terminal_multiple")?.thesis ?? 12.0,
          }}
        />
      </section>
    </div>
  );
}

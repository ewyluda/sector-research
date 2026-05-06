"use client";
import { useEffect, useState } from "react";
import { getReverseDcf, type ReverseDcfResponse } from "@/lib/api";
import { ThesisVsPricedTable } from "./ThesisVsPricedTable";
import { SensitivityHeatmap } from "./SensitivityHeatmap";

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

  if (err) return <div className="p-6 text-rose-400">Error: {err}</div>;
  if (!data) return <div className="p-6 text-slate-400">Loading reverse DCF&hellip;</div>;
  return (
    <div className="p-6 space-y-6">
      <div className="flex gap-3 items-center text-sm" data-print-hide="true">
        <label>
          Price override:{" "}
          <input
            value={priceOverride}
            onChange={(e) => setPriceOverride(e.target.value)}
            className="bg-slate-900 border border-slate-700 rounded px-2 py-0.5 w-24"
          />
        </label>
        {hasDraft && (
          <label>
            <input type="checkbox" checked={fromDraft} onChange={(e) => setFromDraft(e.target.checked)} /> Use draft
          </label>
        )}
        <button onClick={load} className="px-3 py-0.5 rounded bg-blue-600 text-white text-sm">
          Recompute
        </button>
      </div>

      <section className="grid grid-cols-2 gap-6">
        <div>
          <div className="text-xs uppercase text-slate-500">Implied IRR</div>
          <div className="text-4xl font-semibold">
            {data.implied_irr === null ? "—" : `${(data.implied_irr * 100).toFixed(2)}%`}
          </div>
          <div className="text-xs text-slate-500 mt-1">
            at {data.price_used.toFixed(2)} ({data.price_source})
          </div>
        </div>
        <div>
          <div className="text-xs uppercase text-slate-500 mb-1">Thesis vs priced in</div>
          <ThesisVsPricedTable rows={data.thesis_vs_priced_in} />
        </div>
      </section>

      <section>
        <h2 className="text-sm font-semibold text-slate-300 mb-2">Sensitivity grids</h2>
        <div className="grid grid-cols-3 gap-6">
          <SensitivityHeatmap grid={data.sensitivity_grids.growth_margin} currentPrice={data.price_used} />
          <SensitivityHeatmap grid={data.sensitivity_grids.growth_multiple} currentPrice={data.price_used} />
          <SensitivityHeatmap grid={data.sensitivity_grids.margin_multiple} currentPrice={data.price_used} />
        </div>
      </section>
    </div>
  );
}

"use client";

import { useEffect, useState } from "react";
import { journalApi } from "@/lib/api";
import type { ExitReason, LinkCandidate, TradeDirection } from "@/lib/api";
import type { FormState } from "./TradeJournalSection";

const EXIT_REASONS: { value: ExitReason; label: string }[] = [
  { value: "thesis_played_out", label: "Thesis played out" },
  { value: "kill_criterion", label: "Kill criterion" },
  { value: "stop_loss", label: "Stop loss" },
  { value: "better_opportunity", label: "Better opportunity" },
  { value: "rebalance", label: "Rebalance" },
  { value: "mistake", label: "Mistake" },
  { value: "other", label: "Other" },
];

const inputCls =
  "w-full rounded-md border border-[var(--border)] bg-[var(--bg)] px-2 py-1 text-sm";
const labelCls = "block text-[11px] uppercase tracking-wide text-[var(--text-muted)] mb-1";

export function TradeForm({
  state,
  onDone,
  onCancel,
}: {
  state: FormState;
  onDone: () => void;
  onCancel: () => void;
}) {
  const editing = state.mode !== "create" ? state.trade : null;
  const closing = state.mode === "close";

  const [ticker, setTicker] = useState(
    state.mode === "create" ? (state.ticker ?? "") : state.trade.ticker
  );
  const [direction, setDirection] = useState<TradeDirection>(editing?.direction ?? "long");
  const [entryDate, setEntryDate] = useState(editing?.entry_date ?? "");
  const [entryPrice, setEntryPrice] = useState(editing?.entry_price ?? "");
  const [quantity, setQuantity] = useState(editing?.quantity ?? "");
  const [rationale, setRationale] = useState(editing?.entry_rationale ?? "");
  const [outcomeId, setOutcomeId] = useState(editing?.outcome_id ?? "");
  const [exitDate, setExitDate] = useState(editing?.exit_date ?? "");
  const [exitPrice, setExitPrice] = useState(editing?.exit_price ?? "");
  const [exitReason, setExitReason] = useState<ExitReason | "">(editing?.exit_reason ?? "");
  const [exitNote, setExitNote] = useState(editing?.exit_note ?? "");

  const [entryPriceDirty, setEntryPriceDirty] = useState(false);
  const [exitPriceDirty, setExitPriceDirty] = useState(false);

  const [candidates, setCandidates] = useState<LinkCandidate[]>([]);
  const [priceHint, setPriceHint] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Auto-fill hint: entry price for create/edit, exit price for close.
  const hintDate = closing ? exitDate : entryDate;
  const hintSetter = closing ? setExitPrice : setEntryPrice;
  useEffect(() => {
    if (!ticker || !hintDate) return;
    let alive = true;
    const timer = setTimeout(() => {
      journalApi
        .pricePreview(ticker, hintDate)
        .then((p) => {
          if (!alive) return;
          hintSetter((prev) => (prev ? prev : p.price));
          setPriceHint(
            p.price_date === hintDate
              ? `EOD close ${p.price}`
              : `EOD close ${p.price} (session ${p.price_date})`
          );
        })
        .catch(() => alive && setPriceHint("no price found — enter manually"));
    }, 300);
    return () => {
      alive = false;
      clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ticker, hintDate]);

  // Link candidates for the ticker (create/edit only).
  useEffect(() => {
    if (closing || !ticker) return;
    let alive = true;
    const timer = setTimeout(() => {
      journalApi
        .linkCandidates(ticker)
        .then((c) => alive && setCandidates(c))
        .catch(() => alive && setCandidates([]));
    }, 300);
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [ticker, closing]);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      if (state.mode === "create") {
        await journalApi.create({
          ticker,
          entry_date: entryDate,
          entry_price: entryPriceDirty && entryPrice ? entryPrice : undefined,
          quantity: quantity || undefined,
          direction,
          outcome_id: outcomeId || undefined,
          entry_rationale: rationale || undefined,
        });
      } else if (state.mode === "close") {
        await journalApi.update(state.trade.id, {
          exit_date: exitDate,
          exit_price: exitPriceDirty && exitPrice ? exitPrice : undefined,
          exit_reason: (exitReason || undefined) as ExitReason | undefined,
          exit_note: exitNote || undefined,
        });
      } else {
        await journalApi.update(state.trade.id, {
          entry_date: entryDate,
          entry_price: entryPriceDirty && entryPrice ? entryPrice : undefined,
          quantity: quantity === "" ? null : quantity,
          direction,
          outcome_id: outcomeId === "" ? null : outcomeId,
          entry_rationale: rationale === "" ? null : rationale,
        });
      }
      onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : "request failed");
    } finally {
      setBusy(false);
    }
  }

  const title =
    state.mode === "create" ? "Log trade" : state.mode === "close" ? `Close ${ticker}` : `Edit ${ticker}`;

  return (
    <div
      data-print-hide="true"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={onCancel}
    >
      <div
        className="w-full max-w-md rounded-xl border border-[var(--border)] bg-[var(--bg)] p-4 space-y-3"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-sm font-semibold">{title}</h3>

        {!closing && (
          <>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className={labelCls}>Ticker</label>
                <input
                  className={inputCls}
                  value={ticker}
                  onChange={(e) => setTicker(e.target.value.toUpperCase())}
                  disabled={state.mode !== "create"}
                />
              </div>
              <div>
                <label className={labelCls}>Direction</label>
                <select
                  className={inputCls}
                  value={direction}
                  onChange={(e) => setDirection(e.target.value as TradeDirection)}
                >
                  <option value="long">Long</option>
                  <option value="short">Short</option>
                </select>
              </div>
              <div>
                <label className={labelCls}>Entry date</label>
                <input
                  type="date"
                  className={inputCls}
                  value={entryDate}
                  onChange={(e) => setEntryDate(e.target.value)}
                />
              </div>
              <div>
                <label className={labelCls}>Entry price</label>
                <input
                  className={inputCls}
                  value={entryPrice}
                  onChange={(e) => {
                    setEntryPrice(e.target.value);
                    setEntryPriceDirty(true);
                  }}
                  placeholder="auto-fill"
                />
              </div>
              <div>
                <label className={labelCls}>Quantity (optional)</label>
                <input
                  className={inputCls}
                  value={quantity}
                  onChange={(e) => setQuantity(e.target.value)}
                />
              </div>
              <div>
                <label className={labelCls}>Linked thesis</label>
                <select
                  className={inputCls}
                  value={outcomeId}
                  onChange={(e) => setOutcomeId(e.target.value)}
                >
                  <option value="">— none —</option>
                  {outcomeId && !candidates.some((c) => c.id === outcomeId) && (
                    <option value={outcomeId}>current link (superseded)</option>
                  )}
                  {candidates.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.verdict} · {c.source_type === "research_run" ? "research" : "workspace"} ·{" "}
                      {c.verdict_emitted_at.slice(0, 10)}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <div>
              <label className={labelCls}>Rationale</label>
              <textarea
                className={inputCls}
                rows={2}
                value={rationale}
                onChange={(e) => setRationale(e.target.value)}
              />
            </div>
          </>
        )}

        {closing && (
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={labelCls}>Exit date</label>
              <input
                type="date"
                className={inputCls}
                value={exitDate}
                onChange={(e) => setExitDate(e.target.value)}
              />
            </div>
            <div>
              <label className={labelCls}>Exit price</label>
              <input
                className={inputCls}
                value={exitPrice}
                onChange={(e) => {
                  setExitPrice(e.target.value);
                  setExitPriceDirty(true);
                }}
                placeholder="auto-fill"
              />
            </div>
            <div>
              <label className={labelCls}>Exit reason</label>
              <select
                className={inputCls}
                value={exitReason}
                onChange={(e) => setExitReason(e.target.value as ExitReason | "")}
              >
                <option value="">— select —</option>
                {EXIT_REASONS.map((r) => (
                  <option key={r.value} value={r.value}>
                    {r.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="col-span-2">
              <label className={labelCls}>Exit note</label>
              <textarea
                className={inputCls}
                rows={2}
                value={exitNote}
                onChange={(e) => setExitNote(e.target.value)}
              />
            </div>
          </div>
        )}

        {priceHint && <p className="text-xs text-[var(--text-muted)]">{priceHint}</p>}
        {error && <p className="text-xs text-rose-400">{error}</p>}

        <div className="flex justify-end gap-2 pt-1">
          <button
            onClick={onCancel}
            className="px-3 py-1 rounded-md text-xs text-[var(--text-muted)] hover:text-[var(--text)]"
          >
            Cancel
          </button>
          <button
            onClick={submit}
            disabled={busy || !ticker || (closing ? !exitDate : !entryDate)}
            className="px-3 py-1 rounded-md border border-[var(--border)] text-xs font-semibold hover:bg-[var(--surface-alt)] disabled:opacity-50"
          >
            {busy ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}

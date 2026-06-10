"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { journalApi } from "@/lib/api";
import type { JournalSummary, TradeDetail } from "@/lib/api";
import { TradeForm } from "./TradeForm";
import { TradeList } from "./TradeList";
import { DecisionVsOutcomePanel } from "./DecisionVsOutcomePanel";
import { ExitReasonTable } from "./ExitReasonTable";

export type FormState =
  | { mode: "create"; ticker?: string }
  | { mode: "edit"; trade: TradeDetail }
  | { mode: "close"; trade: TradeDetail };

export function TradeJournalSection() {
  const [trades, setTrades] = useState<TradeDetail[]>([]);
  const [summary, setSummary] = useState<JournalSummary | null>(null);
  const [form, setForm] = useState<FormState | null>(null);

  const refresh = useCallback(() => {
    journalApi.list().then(setTrades).catch(() => setTrades([]));
    journalApi.getSummary().then(setSummary).catch(() => setSummary(null));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Deep link: /performance?log_trade=TICKER auto-opens the create form,
  // prefilled. One-shot (pattern: /status?expand_earnings): consumed ref +
  // URL cleanup so refresh/back doesn't reopen a form the user dismissed.
  const logTradeConsumed = useRef(false);
  useEffect(() => {
    if (logTradeConsumed.current) return;
    const t = new URLSearchParams(window.location.search).get("log_trade");
    if (!t) return;
    logTradeConsumed.current = true;
    // One-shot URL param read on mount; empty dep array is intentional.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setForm({ mode: "create", ticker: t.toUpperCase() });
    const url = new URL(window.location.href);
    url.searchParams.delete("log_trade");
    window.history.replaceState({}, "", url.toString());
  }, []);

  return (
    <section className="px-4 py-4 border-t border-[var(--border)]">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--text-muted)]">
          Trade journal
        </h2>
        <button
          onClick={() => setForm({ mode: "create" })}
          data-print-hide="true"
          className="px-3 py-1 rounded-md border border-[var(--border)] text-xs font-semibold hover:bg-[var(--surface-alt)]"
        >
          Log trade
        </button>
      </div>

      {summary && summary.closed_count > 0 && (
        <DecisionVsOutcomePanel summary={summary} trades={trades} />
      )}
      <TradeList
        trades={trades}
        onEdit={(t) => setForm({ mode: "edit", trade: t })}
        onCloseTrade={(t) => setForm({ mode: "close", trade: t })}
        onChanged={refresh}
      />
      {summary && summary.by_exit_reason.length > 0 && (
        <ExitReasonTable rows={summary.by_exit_reason} />
      )}

      {form && (
        <TradeForm
          state={form}
          onDone={() => {
            setForm(null);
            refresh();
          }}
          onCancel={() => setForm(null)}
        />
      )}
    </section>
  );
}

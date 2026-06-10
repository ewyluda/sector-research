"use client";

import { useCallback, useEffect, useState } from "react";
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

// Read + consume the one-shot ?log_trade=TICKER query param at init time.
function consumeLogTradeParam(): FormState | null {
  if (typeof window === "undefined") return null;
  const t = new URLSearchParams(window.location.search).get("log_trade");
  if (!t) return null;
  const url = new URL(window.location.href);
  url.searchParams.delete("log_trade");
  window.history.replaceState({}, "", url.toString());
  return { mode: "create", ticker: t.toUpperCase() };
}

export function TradeJournalSection() {
  const [trades, setTrades] = useState<TradeDetail[]>([]);
  const [summary, setSummary] = useState<JournalSummary | null>(null);
  // Lazy initializer handles the one-shot deep link: /performance?log_trade=TICKER
  // (pattern: /status?expand_earnings). consumeLogTradeParam() runs once at mount.
  const [form, setForm] = useState<FormState | null>(consumeLogTradeParam);

  const refresh = useCallback(() => {
    journalApi.list().then(setTrades).catch(() => setTrades([]));
    journalApi.getSummary().then(setSummary).catch(() => setSummary(null));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

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

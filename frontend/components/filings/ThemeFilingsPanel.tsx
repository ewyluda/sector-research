"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { fanouts } from "@/lib/api";
import type { FanoutStatus, Theme } from "@/lib/api";
import TickerFilingsCard, { type TickerFilingsCardHandle } from "./TickerFilingsCard";

export default function ThemeFilingsPanel({ theme }: { theme: Theme }) {
  const tickers = Array.isArray(theme.seed_tickers) ? theme.seed_tickers : [];
  const [expanded, setExpanded] = useState(true);
  const [bulkProgress, setBulkProgress] = useState<{ done: number; total: number } | null>(null);
  const [fanoutStatus, setFanoutStatus] = useState<FanoutStatus | null>(null);
  const fanoutPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const cardRefs = useRef<Map<string, TickerFilingsCardHandle>>(new Map());

  useEffect(() => {
    return () => {
      if (fanoutPollRef.current) clearInterval(fanoutPollRef.current);
    };
  }, []);

  const registerCard = useCallback((ticker: string, handle: TickerFilingsCardHandle | null) => {
    if (handle) cardRefs.current.set(ticker, handle);
    else cardRefs.current.delete(ticker);
  }, []);

  async function onFanoutTheme() {
    try {
      const initial = await fanouts.startTheme(theme.id);
      setFanoutStatus(initial);
      if (fanoutPollRef.current) clearInterval(fanoutPollRef.current);
      fanoutPollRef.current = setInterval(async () => {
        try {
          const next = await fanouts.get(initial.fanout_id);
          setFanoutStatus(next);
          if (next.status !== "running" && fanoutPollRef.current) {
            clearInterval(fanoutPollRef.current);
            fanoutPollRef.current = null;
          }
        } catch (err) {
          console.error("fanout poll failed", err);
          if (fanoutPollRef.current) {
            clearInterval(fanoutPollRef.current);
            fanoutPollRef.current = null;
          }
        }
      }, 3000);
    } catch (err) {
      console.error("fanout start failed", err);
      setFanoutStatus(null);
    }
  }

  async function onIngestAll() {
    if (bulkProgress) return;
    setExpanded(true);
    setBulkProgress({ done: 0, total: tickers.length });
    for (let i = 0; i < tickers.length; i++) {
      const handle = cardRefs.current.get(tickers[i]);
      if (handle) {
        try {
          await handle.ingest();
        } catch {
          // Keep going; individual card shows its own error.
        }
      }
      setBulkProgress({ done: i + 1, total: tickers.length });
    }
    setBulkProgress(null);
  }

  const bulkLabel = bulkProgress
    ? `Ingesting ${bulkProgress.done}/${bulkProgress.total}…`
    : `Ingest all ${tickers.length}`;

  const fanoutLabel =
    fanoutStatus?.status === "running"
      ? `Fanning ${fanoutStatus.completed_tickers}/${fanoutStatus.total_tickers}…`
      : fanoutStatus?.status === "completed"
      ? fanoutStatus.errors.length > 0
        ? `Fan-out done · ${fanoutStatus.errors.length} error${fanoutStatus.errors.length !== 1 ? "s" : ""}`
        : "Fan-out done"
      : fanoutStatus?.status === "failed"
      ? "Fan-out failed"
      : `Fan out ${tickers.length}`;

  return (
    <section className="rounded-xl border border-[var(--border)] bg-[var(--surface)] overflow-hidden">
      <div className="w-full bg-[var(--teal-dark)] flex items-stretch">
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="flex-1 text-left px-5 py-3 flex items-center justify-between gap-4 hover:brightness-110 transition cursor-pointer min-w-0"
          aria-expanded={expanded}
        >
          <div className="min-w-0 flex-1">
            <h2 className="text-white font-semibold text-sm">{theme.name}</h2>
            {theme.description && (
              <p className="text-[var(--teal-lighter)] text-xs mt-0.5 line-clamp-1">
                {theme.description}
              </p>
            )}
          </div>
          <div className="shrink-0 flex items-center gap-3 text-[11px] text-[var(--teal-light)]">
            <span className="whitespace-nowrap">
              {tickers.length} ticker{tickers.length !== 1 ? "s" : ""}
            </span>
            <svg
              className={`w-3.5 h-3.5 transition-transform ${expanded ? "rotate-180" : ""}`}
              aria-hidden="true"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2.5}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
            </svg>
          </div>
        </button>
        <div className="shrink-0 flex items-center gap-2 pr-4">
          <button
            type="button"
            onClick={onFanoutTheme}
            disabled={fanoutStatus?.status === "running" || tickers.length === 0}
            className="text-[11px] px-2.5 py-1 rounded-md bg-white/10 text-white hover:bg-white/20 disabled:opacity-50 transition whitespace-nowrap cursor-pointer"
          >
            {fanoutLabel}
          </button>
          <button
            type="button"
            onClick={onIngestAll}
            disabled={!!bulkProgress || tickers.length === 0}
            className="text-[11px] px-2.5 py-1 rounded-md bg-white/10 text-white hover:bg-white/20 disabled:opacity-50 transition whitespace-nowrap cursor-pointer"
          >
            {bulkLabel}
          </button>
        </div>
      </div>

      {fanoutStatus?.status === "running" && fanoutStatus.current_ticker && (
        <div className="text-[11px] text-[var(--text-muted)] px-4 py-1 border-t border-[var(--border)]">
          Fan-out: {fanoutStatus.current_stage} · {fanoutStatus.current_ticker}
        </div>
      )}

      {expanded && (
        <div className="p-4 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
          {tickers.map((t) => (
            <TickerFilingsCard
              key={t}
              ticker={t}
              ref={(handle) => registerCard(t, handle)}
            />
          ))}
        </div>
      )}
    </section>
  );
}

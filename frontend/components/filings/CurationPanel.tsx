"use client";

import { useCallback, useEffect, useState } from "react";
import { relationships } from "@/lib/api";
import type {
  DismissedAlias,
  ResolutionCandidate,
  UnresolvedCounterparty,
} from "@/lib/api";

export default function CurationPanel() {
  const [expanded, setExpanded] = useState(false);
  const [items, setItems] = useState<UnresolvedCounterparty[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  // Dismissed sub-panel state
  const [dismissedExpanded, setDismissedExpanded] = useState(false);
  const [dismissed, setDismissed] = useState<DismissedAlias[] | null>(null);
  const [dismissedLoading, setDismissedLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const rows = await relationships.listUnresolved(50);
      setItems(rows);
    } catch (e) {
      setError(e instanceof Error ? e.message : "load failed");
    } finally {
      setLoading(false);
    }
  }, []);

  const loadDismissed = useCallback(async () => {
    setDismissedLoading(true);
    try {
      const rows = await relationships.listDismissed();
      setDismissed(rows);
    } catch {
      // non-blocking; leave dismissed as null
    } finally {
      setDismissedLoading(false);
    }
  }, []);

  // Fetch the queue on mount so the pending count shows even when collapsed.
  useEffect(() => {
    if (items === null) {
      load();
    }
  }, [items, load]);

  // Lazy-load dismissed list on first expand.
  useEffect(() => {
    if (dismissedExpanded && dismissed === null) {
      loadDismissed();
    }
  }, [dismissedExpanded, dismissed, loadDismissed]);

  async function onApplyCandidate(
    row: UnresolvedCounterparty,
    candidate: ResolutionCandidate,
  ) {
    setBusy(row.alias_normalized);
    setError(null);
    try {
      await relationships.createAlias({
        alias_name: row.counterparty_name,
        canonical_cik: candidate.cik,
        canonical_ticker: candidate.ticker,
        canonical_name: candidate.canonical_name,
        created_by: "ui-curator",
      });
      // Remove from the queue locally so the user sees the action take.
      setItems((cur) =>
        cur?.filter((r) => r.alias_normalized !== row.alias_normalized) ?? null
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "alias failed");
    } finally {
      setBusy(null);
    }
  }

  async function onDismiss(row: UnresolvedCounterparty) {
    setBusy(row.alias_normalized);
    setError(null);
    try {
      await relationships.dismiss(row.counterparty_name);
      setItems((cur) =>
        cur?.filter((r) => r.alias_normalized !== row.alias_normalized) ?? null
      );
      // Invalidate dismissed list so it reloads on next expand.
      setDismissed(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "dismiss failed");
    } finally {
      setBusy(null);
    }
  }

  async function onUndismiss(row: DismissedAlias) {
    try {
      await relationships.undismiss(row.alias_normalized);
      // Reload both lists.
      setDismissed(null);
      setItems(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "undo failed");
    }
  }

  function formatDate(iso: string | null): string {
    if (!iso) return "";
    try {
      return new Date(iso).toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
      });
    } catch {
      return iso;
    }
  }

  return (
    <section className="rounded-xl border border-[var(--border)] bg-[var(--surface)] overflow-hidden">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="w-full bg-[var(--surface-alt)] px-5 py-3 flex items-center justify-between hover:brightness-105 transition cursor-pointer"
      >
        <div className="text-left">
          <h2 className="text-sm font-semibold text-[var(--text)]">
            Counterparty resolution queue
          </h2>
          <p className="text-[11px] text-[var(--text-muted)]">
            Unresolved counterparties from extracted relationships — pick a
            candidate or keep researching.
          </p>
        </div>
        <div className="shrink-0 flex items-center gap-3 text-[11px] text-[var(--text-muted)]">
          {items && <span className="whitespace-nowrap">{items.length} pending</span>}
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

      {expanded && (
        <div className="p-4 space-y-3">
          {loading && (
            <div className="text-xs text-[var(--text-faint)]">Loading…</div>
          )}
          {error && <div className="text-xs text-[var(--error-text)]">{error}</div>}
          {!loading && items && items.length === 0 && (
            <div className="text-xs text-[var(--text-faint)]">
              Nothing to resolve. Run extraction on more tickers to fill the
              queue.
            </div>
          )}
          {items?.map((row) => (
            <div
              key={row.alias_normalized}
              className="rounded-lg border border-[var(--border)] p-3 space-y-2"
            >
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="font-medium text-[var(--text)] text-sm">
                    {row.counterparty_name}
                  </div>
                  <div className="text-[11px] text-[var(--text-faint)]">
                    {row.occurrence_count} mention{row.occurrence_count !== 1 ? "s" : ""} across{" "}
                    {row.tickers.length} ticker{row.tickers.length !== 1 ? "s" : ""}
                    {row.tickers.length > 0 && (
                      <> — {row.tickers.join(", ")}</>
                    )}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => onDismiss(row)}
                  disabled={busy === row.alias_normalized}
                  className="shrink-0 text-[11px] px-2 py-1 rounded border border-[var(--border)] text-[var(--text-muted)] hover:bg-[var(--error-bg)] hover:text-[var(--error-text)] disabled:opacity-50 transition"
                >
                  Not public / dismiss
                </button>
              </div>

              <div className="space-y-1">
                {row.candidates.length === 0 && (
                  <div className="text-[11px] italic text-[var(--text-faint)]">
                    No EDGAR candidates found.
                  </div>
                )}
                {row.candidates.map((c) => (
                  <div
                    key={c.cik}
                    className="flex items-center justify-between gap-3 rounded bg-[var(--surface-alt)] px-2 py-1.5"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="text-[12px] text-[var(--text)] truncate">
                        {c.canonical_name}
                      </div>
                      <div className="text-[10px] text-[var(--text-faint)] font-mono">
                        {c.ticker ?? "(no ticker)"} · CIK {c.cik} ·{" "}
                        <span className="text-[var(--primary)]">
                          {c.score.toFixed(0)}
                        </span>
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => onApplyCandidate(row, c)}
                      disabled={busy === row.alias_normalized}
                      className="text-[11px] px-2 py-1 rounded border border-[var(--border)] hover:bg-[var(--primary)] hover:text-white hover:border-[var(--primary)] disabled:opacity-50 transition"
                    >
                      {busy === row.alias_normalized ? "…" : "Use this"}
                    </button>
                  </div>
                ))}
              </div>
            </div>
          ))}

          {/* Dismissed (private / not public) disclosure */}
          <div className="rounded-lg border border-[var(--border)] overflow-hidden">
            <button
              type="button"
              onClick={() => setDismissedExpanded((v) => !v)}
              className="w-full bg-[var(--surface-alt)] px-4 py-2.5 flex items-center justify-between hover:brightness-105 transition cursor-pointer"
            >
              <span className="text-[12px] font-medium text-[var(--text-muted)]">
                Dismissed (private / not public)
                {dismissed && dismissed.length > 0 && (
                  <span className="ml-2 text-[var(--text-faint)]">
                    {dismissed.length}
                  </span>
                )}
              </span>
              <svg
                className={`w-3 h-3 transition-transform text-[var(--text-faint)] ${dismissedExpanded ? "rotate-180" : ""}`}
                aria-hidden="true"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2.5}
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
              </svg>
            </button>

            {dismissedExpanded && (
              <div className="px-4 py-3 space-y-1.5">
                {dismissedLoading && (
                  <div className="text-xs text-[var(--text-faint)]">Loading…</div>
                )}
                {!dismissedLoading && dismissed && dismissed.length === 0 && (
                  <div className="text-xs text-[var(--text-faint)]">
                    No dismissed counterparties.
                  </div>
                )}
                {dismissed?.map((row) => (
                  <div
                    key={row.alias_normalized}
                    className="flex items-center justify-between gap-3 rounded bg-[var(--surface-alt)] px-3 py-1.5"
                  >
                    <div className="min-w-0 flex-1">
                      <span className="text-[12px] text-[var(--text)]">
                        {row.alias_name}
                      </span>
                      {row.created_at && (
                        <span className="ml-2 text-[10px] text-[var(--text-faint)]">
                          · {formatDate(row.created_at)}
                        </span>
                      )}
                    </div>
                    <button
                      type="button"
                      onClick={() => onUndismiss(row)}
                      className="shrink-0 text-[11px] px-2 py-1 rounded border border-[var(--border)] text-[var(--text-muted)] hover:bg-[var(--surface)] disabled:opacity-50 transition"
                    >
                      Undo
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  );
}

"use client";

import { useEffect, useState } from "react";
import {
  transcriptDeltaApi,
  type TranscriptAxisDelta,
  type TranscriptDeltaRead,
} from "@/lib/api";
import { DELTA_AXIS_LABELS, type DeltaAxisKey } from "../categories";

function directionClass(d: TranscriptAxisDelta["direction"]): string {
  if (d === "softening") return "bg-red-100 text-red-800 border-red-200";
  if (d === "strengthening") return "bg-green-100 text-green-800 border-green-200";
  return "bg-[var(--surface-2)] text-[var(--text)] border-[var(--border)]";
}

function magnitudeLabel(m: TranscriptAxisDelta["magnitude"]): string {
  return { minor: "minor", material: "material", regime_change: "regime change" }[m];
}

export function WhatChangedPanel({ ticker }: { ticker: string }) {
  const [delta, setDelta] = useState<TranscriptDeltaRead | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const latest = await transcriptDeltaApi.getLatest(ticker);
        if (!cancelled) setDelta(latest);
      } catch (e) {
        if (!cancelled) setError(String(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [ticker]);

  const compute = async (force: boolean) => {
    setBusy(true);
    setError(null);
    try {
      const fresh = await transcriptDeltaApi.compute(ticker, { force });
      setDelta(fresh);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return (
      <section
        id="what_changed"
        className="px-4 py-6 border-b border-[var(--border)]"
      />
    );
  }

  if (!delta) {
    return (
      <section
        id="what_changed"
        className="px-4 py-6 border-b border-[var(--border)]"
      >
        <h2 className="text-sm uppercase tracking-wide text-[var(--text-muted)] mb-2">
          What changed
        </h2>
        <p className="text-sm text-[var(--text-muted)] mb-3">
          Detect QoQ shifts in management&apos;s transcript language across the
          9 deep-dive categories.
        </p>
        <button
          type="button"
          onClick={() => compute(false)}
          disabled={busy}
          data-print-hide="true"
          className="px-3 py-1.5 text-sm rounded bg-[var(--primary)] text-white disabled:opacity-50"
        >
          {busy ? "Computing…" : "Compute transcript delta"}
        </button>
        {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
      </section>
    );
  }

  const populated = (
    Object.entries(delta.axes) as [DeltaAxisKey, TranscriptAxisDelta | null][]
  ).filter(([, v]) => v !== null) as [DeltaAxisKey, TranscriptAxisDelta][];

  return (
    <section
      id="what_changed"
      className="px-4 py-6 border-b border-[var(--border)]"
    >
      <div className="flex items-baseline justify-between mb-3">
        <h2 className="text-sm uppercase tracking-wide text-[var(--text-muted)]">
          What changed — last {delta.transcripts_window.length} quarters
        </h2>
        <button
          type="button"
          onClick={() => compute(true)}
          disabled={busy}
          data-print-hide="true"
          className="text-xs text-[var(--text-muted)] hover:text-[var(--text)] disabled:opacity-50"
        >
          {busy ? "Recomputing…" : "Recompute"}
        </button>
      </div>

      {populated.length === 0 && (
        <p className="text-sm text-[var(--text-muted)]">
          No material language shifts detected across these{" "}
          {delta.transcripts_window.length} quarters.
        </p>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {populated.map(([key, ax]) => (
          <div
            key={key}
            className="border border-[var(--border)] rounded p-3 bg-[var(--surface)]"
          >
            <div className="flex items-center justify-between mb-1.5">
              <div className="text-sm font-medium">{DELTA_AXIS_LABELS[key]}</div>
              <span
                className={`px-2 py-0.5 text-xs rounded border ${directionClass(
                  ax.direction
                )}`}
              >
                {ax.direction} · {magnitudeLabel(ax.magnitude)}
              </span>
            </div>
            <p className="text-sm text-[var(--text)] mb-2">{ax.summary}</p>
            {ax.quotes.length > 0 && (
              <details className="text-xs">
                <summary className="text-[var(--text-muted)] cursor-pointer">
                  {ax.quotes.length} verbatim quote
                  {ax.quotes.length === 1 ? "" : "s"}
                </summary>
                <ul className="mt-1.5 space-y-1.5">
                  {ax.quotes.map((q, i) => (
                    <li
                      key={i}
                      className="border-l-2 border-[var(--border)] pl-2 text-[var(--text-muted)]"
                    >
                      <span className="font-medium">
                        Q{q.quarter} {q.year} · {q.role}:
                      </span>{" "}
                      &quot;{q.text}&quot;
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </div>
        ))}
      </div>

      {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
    </section>
  );
}

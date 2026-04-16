"use client";

import { useEffect, useState } from "react";
import { filings } from "@/lib/api";
import type { FilingSectionText } from "@/lib/api";

interface Props {
  ticker: string;
  accession: string;
  sectionKey: string;
  heading: string | null;
  onClose: () => void;
}

export default function SectionReader({
  ticker,
  accession,
  sectionKey,
  heading,
  onClose,
}: Props) {
  const [data, setData] = useState<FilingSectionText | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    filings
      .getSection(ticker, accession, sectionKey)
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch((e) => {
        if (!cancelled)
          setError(e instanceof Error ? e.message : "fetch failed");
      });
    return () => {
      cancelled = true;
    };
  }, [ticker, accession, sectionKey]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 bg-black/40 flex items-start justify-center p-6 overflow-y-auto"
      onClick={onClose}
    >
      <div
        className="bg-[var(--surface)] rounded-xl border border-[var(--border)] max-w-4xl w-full my-4 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sticky top-0 bg-[var(--surface)] border-b border-[var(--border)] px-5 py-3 flex items-center justify-between rounded-t-xl">
          <div>
            <div className="text-[11px] text-[var(--text-faint)] font-mono">
              ${ticker.toUpperCase()} · {accession}
            </div>
            <h3 className="text-sm font-semibold text-[var(--text)]">
              {heading ?? sectionKey}
            </h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-[var(--text-muted)] hover:text-[var(--text)] text-xl leading-none px-2"
            aria-label="Close"
          >
            ×
          </button>
        </div>

        <div className="p-5">
          {error && (
            <div className="text-sm text-[var(--error-text)]">{error}</div>
          )}
          {!error && !data && (
            <div className="text-sm text-[var(--text-faint)]">Loading…</div>
          )}
          {data && (
            <div className="space-y-1">
              <div className="text-[11px] text-[var(--text-faint)]">
                {data.char_count.toLocaleString()} chars · extracted via {data.extraction_method}
              </div>
              <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed text-[var(--text)] pt-2">
                {data.text}
              </pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

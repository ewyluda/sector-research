"use client";

import { useEffect, useMemo, useState } from "react";
import {
  getTranscripts,
  getTranscript,
  summarizeTranscript,
  type TranscriptEvent,
  type Transcript,
} from "@/lib/api";
import { MarkdownProse } from "@/components/deep-dive/renderMarkdown";
import { EmptyState } from "./EmptyState";

export function TranscriptReader({ ticker }: { ticker: string }) {
  const [events, setEvents] = useState<TranscriptEvent[] | null>(null);
  const [active, setActive] = useState<{ year: number; quarter: number } | null>(null);
  const [transcript, setTranscript] = useState<Transcript | null>(null);
  const [query, setQuery] = useState("");
  const [summary, setSummary] = useState<string | null>(null);
  const [summarizing, setSummarizing] = useState(false);

  useEffect(() => {
    let alive = true;
    getTranscripts(ticker)
      .then((tl) => {
        if (!alive) return;
        setEvents(tl.events);
        if (tl.events[0]) setActive({ year: tl.events[0].fiscal_year, quarter: tl.events[0].quarter });
      })
      .catch(() => alive && setEvents([]));
    return () => { alive = false; };
  }, [ticker]);

  useEffect(() => {
    if (!active) return;
    let alive = true;
    getTranscript(ticker, active.year, active.quarter)
      .then((t) => {
        if (!alive) return;
        setTranscript(null);
        setSummary(null);
        setTranscript(t);
      })
      .catch(() => {
        if (!alive) return;
        setTranscript(null);
        setSummary(null);
      });
    return () => { alive = false; };
  }, [ticker, active]);

  const filtered = useMemo(() => {
    if (!transcript) return [];
    const q = query.trim().toLowerCase();
    if (!q) return transcript.segments;
    return transcript.segments.filter(
      (s) => s.speaker.toLowerCase().includes(q) || s.text.toLowerCase().includes(q),
    );
  }, [transcript, query]);

  async function onSummarize() {
    if (!active) return;
    setSummarizing(true);
    try {
      const r = await summarizeTranscript(ticker, active.year, active.quarter);
      setSummary(r.summary_md);
    } catch {
      setSummary("_Could not generate summary._");
    } finally {
      setSummarizing(false);
    }
  }

  if (events === null) {
    return <div className="p-6 text-sm text-[var(--text-muted)]">Loading transcripts…</div>;
  }
  if (events.length === 0) {
    return <EmptyState title="No transcripts" message="No earnings-call transcripts are available for this company." />;
  }

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-[180px_1fr_320px]">
      <nav className="space-y-1">
        {events.map((e) => {
          const isActive = active?.year === e.fiscal_year && active?.quarter === e.quarter;
          return (
            <button
              key={`${e.fiscal_year}-${e.quarter}`}
              onClick={() => setActive({ year: e.fiscal_year, quarter: e.quarter })}
              className={`block w-full rounded-md px-3 py-2 text-left text-sm transition-colors ${
                isActive
                  ? "bg-[var(--accent-bg)] font-medium text-[var(--text)]"
                  : "text-[var(--text-muted)] hover:bg-[var(--surface-alt)] hover:text-[var(--text)]"
              }`}
            >
              Q{e.quarter} FY{e.fiscal_year}
              <span className="block text-[10px] text-[var(--text-muted)]">{e.date}</span>
            </button>
          );
        })}
      </nav>

      <div className="min-w-0">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search transcript…"
          className="mb-3 w-full rounded-md border border-[var(--border)] bg-[var(--surface-alt)] px-3 py-1.5 text-sm text-[var(--text)] placeholder:text-[var(--text-muted)]"
        />
        {transcript === null ? (
          <div className="p-6 text-sm text-[var(--text-muted)]">Loading transcript…</div>
        ) : transcript.segments.length === 0 ? (
          <div className="p-6 text-sm text-[var(--text-muted)]">Transcript not available for this quarter.</div>
        ) : (
          <div className="space-y-3">
            {filtered.map((s, i) => (
              <div key={i}>
                {s.speaker && <div className="text-sm font-semibold text-[var(--text)]">{s.speaker}</div>}
                <p className="text-sm leading-relaxed text-[var(--text-muted)]">{s.text}</p>
              </div>
            ))}
            {filtered.length === 0 && (
              <p className="text-sm text-[var(--text-muted)]">No segments match &ldquo;{query}&rdquo;.</p>
            )}
          </div>
        )}
      </div>

      <aside className="space-y-2">
        <button
          onClick={onSummarize}
          disabled={summarizing || !transcript || transcript.segments.length === 0}
          className="w-full rounded-md bg-[var(--primary)] px-3 py-1.5 text-sm text-white hover:bg-[var(--primary-dk)] disabled:opacity-40"
        >
          {summarizing ? "Summarizing…" : "AI Summary"}
        </button>
        {summary && (
          <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-3">
            <MarkdownProse text={summary} />
          </div>
        )}
      </aside>
    </div>
  );
}

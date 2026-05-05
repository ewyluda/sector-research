"use client";

import { useState } from "react";
import type { ReadThroughItem } from "@/lib/api";
import { readThroughs } from "@/lib/api";

interface Props {
  runId: string;
  items: ReadThroughItem[];
  onDismissed: (eventKey: string) => void;
}

const TYPE_BADGE: Record<string, string> = {
  customer: "bg-emerald-900/40 text-emerald-200 ring-emerald-700",
  supplier: "bg-emerald-900/40 text-emerald-200 ring-emerald-700",
  partner: "bg-emerald-900/40 text-emerald-200 ring-emerald-700",
  joint_venture: "bg-emerald-900/40 text-emerald-200 ring-emerald-700",
  competitor: "bg-amber-900/40 text-amber-200 ring-amber-700",
  licensor: "bg-slate-800 text-slate-300 ring-slate-700",
  licensee: "bg-slate-800 text-slate-300 ring-slate-700",
  distributor: "bg-slate-800 text-slate-300 ring-slate-700",
  reseller: "bg-slate-800 text-slate-300 ring-slate-700",
  other: "bg-slate-800/60 text-slate-400 ring-slate-700",
};

const EVENT_LABEL: Record<string, string> = {
  earnings: "Earnings",
  run_complete: "Run finished",
};

export function ReadThroughDrawer({ runId, items, onDismissed }: Props) {
  if (items.length === 0) {
    return (
      <div className="px-4 py-3 text-sm text-slate-500" data-print-hide="true">
        No active read-throughs.
      </div>
    );
  }

  return (
    <div className="space-y-2 px-4 py-3" data-print-hide="true">
      {items.map((item) => (
        <ReadThroughRow
          key={item.event_key}
          runId={runId}
          item={item}
          onDismissed={onDismissed}
        />
      ))}
    </div>
  );
}

interface RowProps {
  runId: string;
  item: ReadThroughItem;
  onDismissed: (eventKey: string) => void;
}

function ReadThroughRow({ runId, item, onDismissed }: RowProps) {
  const [summary, setSummary] = useState<string | null>(null);
  const [busy, setBusy] = useState<"none" | "dismiss" | "summary">("none");
  const [error, setError] = useState<string | null>(null);

  async function handleDismiss() {
    setBusy("dismiss");
    setError(null);
    try {
      await readThroughs.dismiss(runId, item.event_key);
      onDismissed(item.event_key);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Dismiss failed");
      setBusy("none");
    }
  }

  async function handleSummarize() {
    setBusy("summary");
    setError(null);
    try {
      const { summary } = await readThroughs.summarize(runId, item.event_key);
      setSummary(summary);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Summary failed");
    } finally {
      setBusy("none");
    }
  }

  return (
    <div className="rounded-md border border-slate-800 bg-slate-900/40 p-3 text-sm">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="rounded bg-slate-800 px-2 py-0.5 font-mono text-xs text-slate-200">
            ${item.peer_ticker}
          </span>
          <span className="text-slate-300">{EVENT_LABEL[item.event_type] ?? item.event_type}</span>
          <span className="text-slate-500">·</span>
          <span className="text-slate-500">{item.event_date}</span>
        </div>
        <div className="flex gap-2">
          <button
            onClick={handleSummarize}
            disabled={busy !== "none"}
            className="rounded border border-slate-700 px-2 py-0.5 text-xs text-slate-300 hover:bg-slate-800 disabled:opacity-50"
          >
            {busy === "summary" ? "Generating…" : summary ? "Regenerate" : "Generate impact summary"}
          </button>
          <button
            onClick={handleDismiss}
            disabled={busy !== "none"}
            className="rounded border border-slate-700 px-2 py-0.5 text-xs text-slate-400 hover:bg-slate-800 disabled:opacity-50"
          >
            {busy === "dismiss" ? "…" : "Dismiss"}
          </button>
        </div>
      </div>

      <div className="mt-2 flex flex-wrap gap-1.5">
        {item.links.map((l, i) => (
          <span
            key={`${l.relationship_type}:${l.direction}:${i}`}
            title={l.verbatim_quote ?? ""}
            className={`rounded px-1.5 py-0.5 text-[11px] ring-1 ${TYPE_BADGE[l.relationship_type] ?? TYPE_BADGE.other}`}
          >
            {l.relationship_type} · {l.direction}
            {l.magnitude_pct != null ? ` · ${l.magnitude_pct.toFixed(0)}%` : ""}
          </span>
        ))}
      </div>

      {summary && (
        <div className="mt-2 rounded bg-slate-950/60 p-2 text-xs text-slate-300">
          {summary}
        </div>
      )}
      {error && (
        <div className="mt-2 text-xs text-rose-400">{error}</div>
      )}
    </div>
  );
}

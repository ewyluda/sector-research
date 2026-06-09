"use client";

import { useState } from "react";

export function PeerSetEditor({
  focus,
  peers,
  busy,
  onChange,
}: {
  focus: string;
  peers: string[];
  busy: boolean;
  onChange: (next: string[]) => void;
}) {
  const [draft, setDraft] = useState("");

  function handleAdd() {
    const candidates = draft
      .split(/[\s,]+/)
      .map((t) => t.trim().toUpperCase())
      .filter((t) => t && t !== focus && !peers.includes(t));
    setDraft("");
    if (candidates.length > 0) onChange([...peers, ...candidates]);
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      {peers.map((t) => (
        <span
          key={t}
          className="inline-flex items-center gap-1 rounded-full border border-[var(--border)] bg-[var(--surface-alt)] px-2 py-0.5 text-xs text-[var(--text)]"
        >
          {t}
          <button
            type="button"
            disabled={busy}
            onClick={() => onChange(peers.filter((p) => p !== t))}
            aria-label={`Remove ${t}`}
            className="text-[var(--text-muted)] hover:text-[var(--error)] disabled:opacity-50"
          >
            ✕
          </button>
        </span>
      ))}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          handleAdd();
        }}
      >
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Add tickers…"
          disabled={busy}
          className="w-28 rounded-md border border-[var(--border)] bg-[var(--surface)] px-2 py-1 text-xs text-[var(--text)] placeholder:text-[var(--text-muted)] disabled:opacity-50"
          aria-label="Add peer tickers"
        />
      </form>
    </div>
  );
}

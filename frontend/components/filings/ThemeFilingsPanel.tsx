"use client";

import { useState } from "react";
import type { Theme } from "@/lib/api";
import TickerFilingsCard from "./TickerFilingsCard";

export default function ThemeFilingsPanel({ theme }: { theme: Theme }) {
  const tickers = Array.isArray(theme.seed_tickers) ? theme.seed_tickers : [];
  const [expanded, setExpanded] = useState(true);

  return (
    <section className="rounded-xl border border-[var(--border)] bg-[var(--surface)] overflow-hidden">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="w-full bg-[var(--teal-dark)] px-5 py-3 flex items-center justify-between hover:brightness-110 transition"
      >
        <div className="text-left">
          <h2 className="text-white font-semibold text-sm">{theme.name}</h2>
          {theme.description && (
            <p className="text-[var(--teal-lighter)] text-xs mt-0.5 line-clamp-1">
              {theme.description}
            </p>
          )}
        </div>
        <div className="flex items-center gap-3 text-[11px] text-[var(--teal-light)]">
          <span>
            {tickers.length} ticker{tickers.length !== 1 ? "s" : ""}
          </span>
          <span aria-hidden>{expanded ? "▾" : "▸"}</span>
        </div>
      </button>

      {expanded && (
        <div className="p-4 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
          {tickers.map((t) => (
            <TickerFilingsCard key={t} ticker={t} />
          ))}
        </div>
      )}
    </section>
  );
}

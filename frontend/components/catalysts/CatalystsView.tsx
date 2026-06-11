"use client";

/**
 * Calendar/List toggle for /catalysts. Calendar (default) renders the
 * unified CalendarView; List renders the pre-existing proximity-bucket
 * CatalystCalendar, untouched.
 */

import { useState } from "react";
import type { CatalystBuckets } from "@/lib/api";
import { CatalystCalendar } from "@/components/CatalystCalendar";
import { CalendarView } from "./CalendarView";

export function CatalystsView({
  buckets,
  activeTickers,
}: {
  buckets: CatalystBuckets;
  activeTickers?: Set<string>; // tickers with an active board entry — see AgendaList
}) {
  const [view, setView] = useState<"calendar" | "list">("calendar");

  return (
    <div className="flex flex-col gap-4">
      <div
        className="flex w-fit overflow-hidden rounded-md border border-[var(--text-muted)]/30 text-[11px]"
        data-print-hide="true"
      >
        {(["calendar", "list"] as const).map((v) => (
          <button
            key={v}
            onClick={() => setView(v)}
            className={`px-3 py-1 capitalize ${
              view === v
                ? "bg-blue-400/20 font-semibold text-[var(--text)]"
                : "text-[var(--text-muted)]"
            }`}
          >
            {v}
          </button>
        ))}
      </div>
      {view === "calendar" ? (
        <CalendarView activeTickers={activeTickers} />
      ) : (
        <CatalystCalendar buckets={buckets} />
      )}
    </div>
  );
}

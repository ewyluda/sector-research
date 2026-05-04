"use client";

import { useEffect, useState } from "react";
import { CatalystCalendar } from "@/components/CatalystCalendar";
import { getCatalysts, type CatalystListResponse } from "@/lib/api";

export default function CatalystsPage() {
  const [data, setData] = useState<CatalystListResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getCatalysts()
      .then((d) => { if (!cancelled) setData(d); })
      .catch((e) => { if (!cancelled) setError(String(e)); });
    return () => { cancelled = true; };
  }, []);

  return (
    <main className="mx-auto max-w-5xl px-6 py-8 flex flex-col gap-6">
      <header>
        <h1 className="text-xl font-semibold text-[var(--text)] tracking-wide">
          Catalysts
        </h1>
        <p className="text-xs text-[var(--text-muted)] mt-1">
          Upcoming events from the latest thesis run for each tracked ticker.
        </p>
      </header>

      {error && (
        <div className="rounded-md border border-[var(--error)]/30 bg-[var(--error)]/5 p-3 text-xs text-[var(--error)]">
          {error}
        </div>
      )}

      {data && <CatalystCalendar buckets={data.buckets} />}

      {!data && !error && (
        <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5">
          <p className="text-xs text-[var(--text-muted)]">Loading…</p>
        </div>
      )}
    </main>
  );
}

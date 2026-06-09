"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { peersApi } from "@/lib/api";
import type { PeerCompResponse } from "@/lib/api";
import { PeerCompTable } from "@/components/peers/PeerCompTable";
import { PeerSetEditor } from "@/components/peers/PeerSetEditor";

function CompareInner() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const tickers = (searchParams.get("tickers") ?? "")
    .split(",")
    .map((t) => t.trim().toUpperCase())
    .filter(Boolean);
  const focus = (searchParams.get("focus") ?? tickers[0] ?? "").toUpperCase();

  const [comp, setComp] = useState<PeerCompResponse | null | undefined>(null);
  const [error, setError] = useState<string | null>(null);

  const key = tickers.join(",") + "|" + focus;
  useEffect(() => {
    if (tickers.length === 0) { setComp(null); return; }
    let alive = true;
    setComp(null);
    setError(null);
    peersApi
      .compare(tickers, focus || undefined)
      .then((c) => { if (alive) setComp(c); })
      .catch((e) => {
        if (alive) {
          setComp(undefined);
          setError(e instanceof Error ? e.message : "Failed to compare");
        }
      });
    return () => { alive = false; };
    // tickers is re-derived each render (new array identity); `key` is the
    // stable string dependency that captures tickers + focus.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  function setUrl(nextTickers: string[], nextFocus: string) {
    if (nextTickers.length === 0) {
      router.replace("/compare");
      return;
    }
    const f = nextTickers.includes(nextFocus) ? nextFocus : nextTickers[0];
    router.replace(
      `/compare?tickers=${encodeURIComponent(nextTickers.join(","))}&focus=${f}`
    );
  }

  // The editor treats `focus` as "self" (excluded from chips); on /compare
  // the focus is just the first chip, so pass an empty focus and manage the
  // full ticker list here.
  return (
    <main className="mx-auto max-w-[1400px] space-y-4 px-6 py-6">
      <div>
        <h1 className="text-lg font-semibold text-[var(--text)]">Compare</h1>
        <p className="text-xs text-[var(--text-muted)]">
          The first ticker is the focus row. The URL is shareable.
        </p>
      </div>

      <PeerSetEditor
        focus=""
        peers={tickers}
        busy={false}
        onChange={(next) => setUrl(next, focus)}
      />

      {tickers.length === 0 && (
        <div className="rounded-lg border border-dashed border-[var(--border)] p-6 text-center text-sm text-[var(--text-muted)]">
          Add tickers to build a comparison, e.g. NVDA AMD INTC.
        </div>
      )}

      {error && <div className="text-xs text-[var(--error)]">{error}</div>}

      {comp?.errors && comp.errors.length > 0 && (
        <div className="text-xs text-[var(--text-muted)]">
          Couldn&apos;t load: {comp.errors.map((e) => e.peer_ticker).join(", ")}
        </div>
      )}

      {tickers.length > 0 && comp === null && (
        <div className="text-sm text-[var(--text-muted)]">Loading…</div>
      )}
      {comp?.table && <PeerCompTable table={comp.table} />}
    </main>
  );
}

export default function ComparePage() {
  return (
    <Suspense fallback={null}>
      <CompareInner />
    </Suspense>
  );
}

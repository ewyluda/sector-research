"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { peersApi } from "@/lib/api";
import type { PeerCompResponse } from "@/lib/api";
import { PeerCompTable } from "@/components/peers/PeerCompTable";
import { PeerSetEditor } from "@/components/peers/PeerSetEditor";

export default function PeersPage() {
  const params = useParams<{ ticker: string }>();
  const ticker = (Array.isArray(params.ticker) ? params.ticker[0] : params.ticker ?? "").toUpperCase();

  const [peers, setPeers] = useState<string[] | null>(null);
  // null = loading, undefined = error
  const [comp, setComp] = useState<PeerCompResponse | null | undefined>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Fetch-sequence counter: a slow mount-time comp fetch must not land after
  // (and overwrite) a fresher post-edit comp fetch. Only the latest sequence
  // is allowed to setComp.
  const compSeq = useRef(0);

  useEffect(() => {
    if (!ticker) return;
    let alive = true;
    const seq = ++compSeq.current;
    // Sequential on purpose: GET /{ticker} seeds the row; firing comp in
    // parallel could double-seed (PK violation on the second insert).
    (async () => {
      try {
        const set = await peersApi.get(ticker);
        if (!alive) return;
        setPeers(set.peers);
        const c = await peersApi.comp(ticker);
        if (alive && seq === compSeq.current) setComp(c);
      } catch {
        if (alive && seq === compSeq.current) setComp(undefined);
      }
    })();
    return () => { alive = false; };
  }, [ticker]);

  async function handleChange(next: string[]) {
    if (peers == null) return;
    const prev = peers;
    setBusy(true);
    setError(null);
    setPeers(next);
    let saved: Awaited<ReturnType<typeof peersApi.update>>;
    try {
      saved = await peersApi.update(ticker, next);
      setPeers(saved.peers);
    } catch (e) {
      setPeers(prev);
      setError(e instanceof Error ? e.message : "Failed to update peers");
      setBusy(false);
      return;
    }
    // PUT succeeded — a comp failure must NOT roll back peers; leave the
    // previous table visible rather than desyncing from the server.
    const seq = ++compSeq.current;
    try {
      const next =
        saved.peers.length > 0
          ? await peersApi.comp(ticker)
          : { table: null, errors: [] };
      if (seq === compSeq.current) setComp(next);
    } catch {
      // stale table stays; peers are correct on the server
    }
    setBusy(false);
  }

  if (comp === undefined && peers == null) {
    return <div className="text-sm text-[var(--error)]">Failed to load peer data.</div>;
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-[var(--text)]">Peer set</h2>
        {peers != null && peers.length > 0 && (
          <Link
            href={`/compare?tickers=${encodeURIComponent([ticker, ...peers].join(","))}&focus=${ticker}`}
            className="text-xs text-[var(--primary)] hover:underline"
          >
            Open in compare →
          </Link>
        )}
      </div>

      {peers == null ? (
        <div className="text-sm text-[var(--text-muted)]">Loading…</div>
      ) : (
        <PeerSetEditor focus={ticker} peers={peers} busy={busy} onChange={handleChange} />
      )}
      {error && <div className="text-xs text-[var(--error)]">{error}</div>}
      {comp === undefined && peers != null && (
        <div className="text-xs text-[var(--error)]">
          Comparison data failed to load — edit the peer set or reload to retry.
        </div>
      )}

      {comp?.errors && comp.errors.length > 0 && (
        <div className="text-xs text-[var(--text-muted)]">
          Couldn&apos;t load: {comp.errors.map((e) => e.peer_ticker).join(", ")}
        </div>
      )}

      {peers != null && peers.length === 0 ? (
        <div className="rounded-lg border border-dashed border-[var(--border)] p-6 text-center text-sm text-[var(--text-muted)]">
          No peers yet — add tickers above to build the comparison.
        </div>
      ) : comp?.table ? (
        <PeerCompTable table={comp.table} />
      ) : comp === null ? (
        <div className="text-sm text-[var(--text-muted)]">Loading comparison…</div>
      ) : null}
    </div>
  );
}

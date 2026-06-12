"use client";

import type { DifferentiationOutput } from "@/lib/api";
import { PeerCompTable } from "@/components/peers/PeerCompTable";

const READ_THROUGH_LABEL: Record<string, string> = {
  earnings: "Earnings",
  run_complete: "Run completed",
};

export function DifferentiationCard({ output }: { output: DifferentiationOutput }) {
  const { peer_comp, read_throughs, per_peer_errors } = output;

  if (!peer_comp) {
    return (
      <div className="text-sm text-[var(--text-muted)] mt-2 italic">
        No peer comp data available.
      </div>
    );
  }

  return (
    <div className="space-y-4 mt-2">
      {/* Peer Comp Table — shared with the company Peers tab and /compare */}
      <div className="space-y-2">
        <h3 className="text-sm font-semibold text-[var(--text)]">Peer Comparison</h3>
        <PeerCompTable table={peer_comp} />
      </div>

      {/* Read-throughs */}
      {read_throughs.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-semibold text-[var(--text)]">Read-throughs</h3>
          <ul className="space-y-1">
            {read_throughs.map((rt, i) => (
              <li key={i} className="text-sm text-[var(--text)]">
                <span
                  title={rt.event_key}
                  className="text-xs px-1 rounded mr-2 bg-[var(--surface-alt)] text-[var(--text-muted)]"
                >
                  {READ_THROUGH_LABEL[rt.event_type] ?? rt.event_type} · {rt.event_date}
                </span>
                <span className="text-[var(--text-muted)]">
                  {rt.peer_ticker}
                  {typeof rt.payload.description === "string" ? ` — ${rt.payload.description}` : null}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Per-peer errors */}
      {per_peer_errors.length > 0 && (
        <details className="rounded border border-[var(--border)] bg-[var(--surface)] p-2">
          <summary className="text-sm font-medium text-[var(--text)] hover:text-[var(--primary)] cursor-pointer">
            Per-peer errors ({per_peer_errors.length})
          </summary>
          <ul className="mt-2 space-y-1">
            {per_peer_errors.map((e, i) => (
              <li key={i} className="text-xs text-[var(--text)]">
                <span className="font-mono text-[var(--text-muted)]">{e.peer_ticker}</span>:{" "}
                <span className="text-[var(--error)]">{e.error_message}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

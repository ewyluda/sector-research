"use client";

/**
 * Detail panel for a selected node on the theme force graph: outbound and
 * inbound relationship buckets grouped by type, with quotes, magnitude
 * chips, bilateral badges, and a root-graph deep link for tracked tickers.
 */
import Link from "next/link";
import type {
  SupplyChainGraphEdge,
  SupplyChainGraphNode,
} from "@/lib/api";

interface Props {
  node: SupplyChainGraphNode;
  edges: SupplyChainGraphEdge[];
  nodesById: Map<string, SupplyChainGraphNode>;
  onClose: () => void;
}

function groupByType(rows: SupplyChainGraphEdge[]) {
  const groups = new Map<string, SupplyChainGraphEdge[]>();
  for (const e of rows) {
    const list = groups.get(e.relationship_type) ?? [];
    list.push(e);
    groups.set(e.relationship_type, list);
  }
  return [...groups.entries()].sort((a, b) => b[1].length - a[1].length);
}

function EdgeRow({
  edge, other,
}: { edge: SupplyChainGraphEdge; other: SupplyChainGraphNode | undefined }) {
  return (
    <li className="rounded border border-[var(--color-border)] bg-[var(--color-bg)] px-2.5 py-2">
      <div className="flex items-center gap-2 text-sm">
        <span className="font-medium text-[var(--color-text-primary)]">
          {other?.ticker ?? other?.name ?? "?"}
        </span>
        {edge.magnitude_pct != null && (
          <span className="rounded bg-[var(--color-surface)] px-1.5 py-0.5 text-[11px] font-mono">
            {edge.magnitude_pct}%
          </span>
        )}
        {edge.confirmed_bilateral && (
          <span className="rounded bg-[var(--color-surface)] px-1.5 py-0.5 text-[11px] text-[var(--color-text-muted)]">
            bilateral
          </span>
        )}
        <span className="ml-auto text-[11px] text-[var(--color-text-muted)]">
          {edge.filing_date}
        </span>
      </div>
      {edge.verbatim_quote && (
        <p className="mt-1 line-clamp-2 text-xs text-[var(--color-text-muted)]">
          &ldquo;{edge.verbatim_quote}&rdquo;
        </p>
      )}
    </li>
  );
}

export default function ThemeGraphSidePanel({
  node, edges, nodesById, onClose,
}: Props) {
  const outbound = edges.filter((e) => e.from_id === node.id);
  const inbound = edges.filter((e) => e.to_id === node.id);

  return (
    <aside className="w-full lg:w-96 shrink-0 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4 space-y-4 max-h-[640px] overflow-y-auto">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="text-base font-semibold text-[var(--color-text-primary)]">
            {node.ticker ?? node.name}
          </h3>
          {node.ticker && node.name !== node.ticker && (
            <p className="text-xs text-[var(--color-text-muted)]">{node.name}</p>
          )}
        </div>
        <button
          onClick={onClose}
          className="text-sm text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]"
        >
          ✕
        </button>
      </div>

      {node.ticker && node.tracked && (
        <Link
          href={`/filings/graph?root=${encodeURIComponent(node.ticker)}`}
          className="inline-block text-sm text-[var(--color-accent)] hover:underline"
        >
          Open root graph →
        </Link>
      )}

      {([["Discloses", outbound], ["Disclosed by", inbound]] as const).map(
        ([title, rows]) =>
          rows.length > 0 && (
            <section key={title}>
              <h4 className="text-[11px] font-semibold uppercase text-[var(--color-text-muted)]">
                {title}
              </h4>
              {groupByType(rows).map(([type, group]) => (
                <div key={type} className="mt-2">
                  <p className="text-xs font-medium text-[var(--color-text-primary)] capitalize">
                    {type.replace("_", " ")} · {group.length}
                  </p>
                  <ul className="mt-1 space-y-1.5">
                    {group.map((e, i) => (
                      <EdgeRow
                        key={`${e.from_id}|${e.to_id}|${e.section_key}|${i}`}
                        edge={e}
                        other={nodesById.get(
                          title === "Discloses" ? e.to_id : e.from_id,
                        )}
                      />
                    ))}
                  </ul>
                </div>
              ))}
            </section>
          ),
      )}
    </aside>
  );
}

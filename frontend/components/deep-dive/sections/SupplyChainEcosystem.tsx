"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { relationships } from "@/lib/api";
import type { SupplyChainEntry, SupplyChainGraph } from "@/lib/api";

const TYPE_LABEL: Record<string, string> = {
  customer: "Customers",
  supplier: "Suppliers",
  partner: "Partners",
  competitor: "Competitors",
  licensor: "Licensors",
  licensee: "Licensees",
  distributor: "Distributors",
  reseller: "Resellers",
  joint_venture: "Joint ventures",
  other: "Other",
};

const TYPE_ORDER = [
  "customer",
  "supplier",
  "partner",
  "joint_venture",
  "distributor",
  "reseller",
  "licensor",
  "licensee",
  "competitor",
  "other",
];

interface Props {
  ticker: string;
}

export function SupplyChainEcosystem({ ticker }: Props) {
  const [graph, setGraph] = useState<SupplyChainGraph | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    relationships
      .getGraph(ticker, "both")
      .then((g) => {
        if (!cancelled) setGraph(g);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "load failed");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [ticker]);

  if (loading) {
    return (
      <section className="rounded-lg border border-[var(--color-border)] p-4">
        <h3 className="text-xs font-semibold uppercase text-[var(--color-text-muted)] mb-2">
          Supply Chain & Ecosystem
        </h3>
        <p className="text-[11px] text-[var(--color-text-muted)]">Loading…</p>
      </section>
    );
  }

  if (error) {
    return (
      <section className="rounded-lg border border-[var(--color-border)] p-4">
        <h3 className="text-xs font-semibold uppercase text-[var(--color-text-muted)] mb-2">
          Supply Chain & Ecosystem
        </h3>
        <p className="text-[11px] text-red-600">{error}</p>
      </section>
    );
  }

  if (!graph || graph.edges.length === 0) {
    return (
      <section className="rounded-lg border border-[var(--color-border)] p-4">
        <h3 className="text-xs font-semibold uppercase text-[var(--color-text-muted)] mb-2">
          Supply Chain & Ecosystem
        </h3>
        <p className="text-[11px] text-[var(--color-text-muted)]">
          No extracted relationships yet. Ingest filings and run extraction
          via the Filings page to populate this card.
        </p>
      </section>
    );
  }

  const typesPresent = TYPE_ORDER.filter((t) => graph.summary[t]);
  const totalOut = graph.edges.filter((e) => e.direction === "out").length;
  const totalIn = graph.edges.filter((e) => e.direction === "in").length;

  return (
    <section className="rounded-lg border border-[var(--color-border)] p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-semibold uppercase text-[var(--color-text-muted)]">
          Supply Chain & Ecosystem
        </h3>
        <div className="text-[10px] text-[var(--color-text-muted)]">
          {totalOut} disclosed · {totalIn} reciprocal
        </div>
      </div>

      <div className="space-y-3">
        {typesPresent.map((type) => {
          const bucket = graph.summary[type];
          const named = bucket.out_named;
          const unnamed = bucket.out_unnamed;
          const inbound = bucket.in_named;
          if (named.length === 0 && unnamed.length === 0 && inbound.length === 0) {
            return null;
          }

          return (
            <div key={type} className="space-y-1.5">
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-semibold uppercase text-[var(--color-text-muted)]">
                  {TYPE_LABEL[type] ?? type}
                </span>
                <span className="text-[10px] text-[var(--color-text-muted)]">
                  {named.length + unnamed.length}
                  {inbound.length > 0 && <> · ↩ {inbound.length}</>}
                </span>
              </div>

              <div className="space-y-1">
                {named.map((e) => (
                  <EdgeRow key={e.accession_number + e.to_id} entry={e} />
                ))}
                {unnamed.length > 0 && (
                  <UnnamedBucket type={type} entries={unnamed} />
                )}
                {inbound.map((e) => (
                  <EdgeRow key={"in:" + e.accession_number + e.from_id} entry={e} />
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function EdgeRow({ entry }: { entry: SupplyChainEntry }) {
  const tracked = entry.counterparty_tracked;
  const ticker = entry.counterparty_ticker;
  const name = entry.counterparty_name ?? "(unknown)";
  const magnitude = entry.magnitude_pct != null ? ` · ${entry.magnitude_pct}%` : "";
  const direction = entry.direction === "in" ? "← " : "";

  const nameNode = tracked && ticker ? (
    <Link
      href={`/pipeline/new?ticker=${encodeURIComponent(ticker)}`}
      className="text-[var(--color-accent)] hover:underline font-medium"
    >
      {name}
    </Link>
  ) : (
    <span>{name}</span>
  );

  return (
    <div
      className="rounded border border-[var(--color-border)] bg-[var(--color-bg)]/40 px-2.5 py-1.5"
      title={entry.verbatim_quote ?? ""}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="text-[11px] min-w-0 flex-1">
          <span className="text-[var(--color-text-muted)]">{direction}</span>
          {nameNode}
          {ticker && (
            <span className="ml-1 text-[10px] text-[var(--color-text-muted)] font-mono">
              ${ticker}
            </span>
          )}
          <span className="text-[10px] text-[var(--color-text-muted)]">{magnitude}</span>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          {entry.confirmed_bilateral && (
            <span className="text-[9px] text-emerald-600 uppercase tracking-wide" title="Reciprocal disclosure found">
              ↔ bilateral
            </span>
          )}
          {entry.direction === "in" && (
            <span className="text-[9px] text-[var(--color-text-muted)] uppercase tracking-wide">
              inbound
            </span>
          )}
        </div>
      </div>
      {entry.verbatim_quote && (
        <p className="text-[10px] text-[var(--color-text-muted)] mt-1 italic line-clamp-2">
          "{entry.verbatim_quote}"
        </p>
      )}
    </div>
  );
}

function UnnamedBucket({
  type,
  entries,
}: {
  type: string;
  entries: SupplyChainEntry[];
}) {
  return (
    <div className="rounded border border-dashed border-[var(--color-border)] bg-[var(--color-bg)]/30 px-2.5 py-1.5 space-y-0.5">
      <div className="text-[10px] font-semibold text-[var(--color-text-muted)]">
        Disclosed but unnamed · {TYPE_LABEL[type] ?? type}
      </div>
      {entries.map((e, i) => (
        <div key={i} className="text-[10px] text-[var(--color-text-muted)]">
          {e.magnitude_pct != null ? `${e.magnitude_pct}% concentration — ` : ""}
          <span className="italic">"{e.verbatim_quote ?? "(no quote)"}"</span>
        </div>
      ))}
    </div>
  );
}

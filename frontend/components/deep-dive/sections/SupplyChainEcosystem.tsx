"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { relationships } from "@/lib/api";
import type { SupplyChainEntry, SupplyChainGraph } from "@/lib/api";
import { usePersistedCollapse } from "../usePersistedCollapse";

const TYPE_LABEL: Record<string, string> = {
  customer: "Customers",
  supplier: "Suppliers",
  partner: "Partners",
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
  "other",
];

interface Props {
  ticker: string;
}

function SectionShell({
  children,
  stat,
  collapsed,
  onToggle,
}: {
  children: React.ReactNode;
  stat?: React.ReactNode;
  collapsed: boolean;
  onToggle: () => void;
}) {
  return (
    <section
      id="supply_chain"
      className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] overflow-hidden"
    >
      <div
        className="px-5 py-3 border-b border-[var(--color-border)] bg-[var(--color-bg)]/40 flex items-center justify-between cursor-pointer select-none"
        onClick={onToggle}
      >
        <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">
          Supply Chain & Ecosystem
        </h3>
        <div className="flex items-center gap-2">
          {stat && (
            <span className="text-[11px] font-mono text-[var(--color-text-muted)]">
              {stat}
            </span>
          )}
          <svg
            className={`w-4 h-4 text-[var(--color-text-muted)] transition-transform ${collapsed ? "" : "rotate-180"}`}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
          </svg>
        </div>
      </div>
      {!collapsed && <div className="p-5 space-y-3">{children}</div>}
    </section>
  );
}

export function SupplyChainEcosystem({ ticker }: Props) {
  const [graph, setGraph] = useState<SupplyChainGraph | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [collapsed, setCollapsed] = usePersistedCollapse("supply_chain");

  useEffect(() => {
    let cancelled = false;
    // Fetch-on-mount pattern: reset the loading + error UI before kicking
    // off the request. Safe because the render is a no-op unless these
    // values differ from defaults on the first mount.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true);
    setError(null);
    relationships
      .getGraph(ticker, { direction: "both" })
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

  const toggle = () => setCollapsed((c) => !c);

  if (loading) {
    return (
      <SectionShell collapsed={collapsed} onToggle={toggle}>
        <p className="text-[11px] text-[var(--color-text-muted)]">Loading…</p>
      </SectionShell>
    );
  }

  if (error) {
    return (
      <SectionShell collapsed={collapsed} onToggle={toggle}>
        <p className="text-[11px] text-[var(--error-text)]">{error}</p>
      </SectionShell>
    );
  }

  if (!graph || graph.edges.length === 0) {
    return (
      <SectionShell collapsed={collapsed} onToggle={toggle}>
        <p className="text-[11px] text-[var(--color-text-muted)] leading-relaxed">
          No extracted relationships yet.{" "}
          <Link
            href="/filings"
            className="text-[var(--color-primary)] hover:underline font-medium"
          >
            Open the Filings page
          </Link>
          {" "}to ingest {ticker} filings and run relationship extraction.
        </p>
      </SectionShell>
    );
  }

  const typesPresent = TYPE_ORDER.filter((t) => graph.summary[t]);
  const totalOut = graph.edges.filter((e) => e.direction === "out").length;
  const totalIn = graph.edges.filter((e) => e.direction === "in").length;

  return (
    <SectionShell
      collapsed={collapsed}
      onToggle={toggle}
      stat={`${totalOut} disclosed · ${totalIn} reciprocal`}
    >
      <div className="space-y-3">
        <div className="flex justify-end">
          <Link
            href={`/filings/graph?root=${encodeURIComponent(ticker)}`}
            className="text-[11px] text-[var(--color-primary)] hover:underline font-medium"
          >
            Explore 2-hop graph →
          </Link>
        </div>
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
    </SectionShell>
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
            <span className="text-[9px] text-emerald-400 uppercase tracking-wide" title="Reciprocal disclosure found">
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
          &ldquo;{entry.verbatim_quote}&rdquo;
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
          <span className="italic">&ldquo;{e.verbatim_quote ?? "(no quote)"}&rdquo;</span>
        </div>
      ))}
    </div>
  );
}

"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { relationships } from "@/lib/api";
import type {
  SupplyChainGraph,
  SupplyChainGraphEdge,
  SupplyChainGraphNode,
  Theme,
} from "@/lib/api";

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

type Direction = "out" | "in" | "both";
type Depth = 1 | 2;

interface Props {
  themes: Theme[];
}

export default function MultiHopGraphView({ themes }: Props) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const rootFromUrl = (searchParams.get("root") ?? "").toUpperCase();
  const themeFromUrl = searchParams.get("theme") ?? "";
  // Default depth is 2 — absence of ?depth means the full 2-hop view.
  const depthFromUrl =
    searchParams.get("depth") === "1" ? (1 as Depth) : (2 as Depth);
  const directionFromUrl: Direction = (() => {
    const d = searchParams.get("direction");
    return d === "out" || d === "in" || d === "both" ? d : "both";
  })();

  // Local form state for the ticker input — committed to the URL on Enter.
  const [tickerInput, setTickerInput] = useState(rootFromUrl);
  useEffect(() => {
    setTickerInput(rootFromUrl);
  }, [rootFromUrl]);

  const [graph, setGraph] = useState<SupplyChainGraph | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch when committed URL params change.
  useEffect(() => {
    if (!rootFromUrl) {
      setGraph(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    relationships
      .getGraph(rootFromUrl, {
        direction: directionFromUrl,
        depth: depthFromUrl,
        themeId: themeFromUrl || undefined,
      })
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
  }, [rootFromUrl, themeFromUrl, depthFromUrl, directionFromUrl]);

  const updateParams = useCallback(
    (next: Record<string, string | null>) => {
      const params = new URLSearchParams(searchParams.toString());
      for (const [k, v] of Object.entries(next)) {
        if (v === null || v === "") params.delete(k);
        else params.set(k, v);
      }
      const qs = params.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [searchParams, pathname, router]
  );

  const onCommitTicker = () => {
    const next = tickerInput.trim().toUpperCase();
    updateParams({ root: next || null });
  };

  const themesWithTickers = useMemo(
    () =>
      themes.filter(
        (t) => Array.isArray(t.seed_tickers) && t.seed_tickers.length > 0
      ),
    [themes]
  );

  return (
    <div className="space-y-6">
      <Controls
        tickerInput={tickerInput}
        onTickerInput={setTickerInput}
        onCommitTicker={onCommitTicker}
        themes={themesWithTickers}
        themeId={themeFromUrl}
        onThemeChange={(id) => updateParams({ theme: id || null })}
        depth={depthFromUrl}
        onDepthChange={(d) => updateParams({ depth: d === 1 ? "1" : null })}
        direction={directionFromUrl}
        onDirectionChange={(d) =>
          updateParams({ direction: d === "both" ? null : d })
        }
      />

      {!rootFromUrl && (
        <div className="rounded-xl border-2 border-dashed border-[var(--color-border)] py-12 text-center">
          <p className="text-sm text-[var(--color-text-muted)]">
            Enter a ticker above to load its supply-chain graph.
          </p>
        </div>
      )}

      {rootFromUrl && loading && (
        <p className="text-sm text-[var(--color-text-muted)]">Loading…</p>
      )}

      {rootFromUrl && error && (
        <div className="rounded-lg border border-[var(--error-border)] bg-[var(--error-bg)] px-4 py-3 text-sm text-[var(--error-text)]">
          {error}
        </div>
      )}

      {rootFromUrl && !loading && !error && graph && (
        <GraphRender graph={graph} depth={depthFromUrl} />
      )}
    </div>
  );
}

// ── Controls ────────────────────────────────────────────────────────────────

function Controls({
  tickerInput,
  onTickerInput,
  onCommitTicker,
  themes,
  themeId,
  onThemeChange,
  depth,
  onDepthChange,
  direction,
  onDirectionChange,
}: {
  tickerInput: string;
  onTickerInput: (v: string) => void;
  onCommitTicker: () => void;
  themes: Theme[];
  themeId: string;
  onThemeChange: (id: string) => void;
  depth: Depth;
  onDepthChange: (d: Depth) => void;
  direction: Direction;
  onDirectionChange: (d: Direction) => void;
}) {
  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4 grid grid-cols-1 md:grid-cols-4 gap-3">
      <label className="flex flex-col gap-1">
        <span className="text-[11px] font-semibold uppercase text-[var(--color-text-muted)]">
          Root ticker
        </span>
        <input
          value={tickerInput}
          onChange={(e) => onTickerInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") onCommitTicker();
          }}
          onBlur={onCommitTicker}
          placeholder="NVDA"
          className="rounded border border-[var(--color-border)] bg-[var(--color-bg)] px-2 py-1.5 text-sm font-mono uppercase"
        />
      </label>

      <label className="flex flex-col gap-1">
        <span className="text-[11px] font-semibold uppercase text-[var(--color-text-muted)]">
          Theme scope
        </span>
        <select
          value={themeId}
          onChange={(e) => onThemeChange(e.target.value)}
          className="rounded border border-[var(--color-border)] bg-[var(--color-bg)] px-2 py-1.5 text-sm"
        >
          <option value="">All tracked tickers</option>
          {themes.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name}
            </option>
          ))}
        </select>
      </label>

      <label className="flex flex-col gap-1">
        <span className="text-[11px] font-semibold uppercase text-[var(--color-text-muted)]">
          Depth
        </span>
        <div className="flex rounded border border-[var(--color-border)] overflow-hidden">
          {([1, 2] as const).map((d) => (
            <button
              key={d}
              type="button"
              onClick={() => onDepthChange(d)}
              className={`flex-1 px-2 py-1.5 text-sm ${
                depth === d
                  ? "bg-[var(--color-accent)] text-white"
                  : "bg-[var(--color-bg)] text-[var(--color-text-primary)]"
              }`}
            >
              {d} hop
            </button>
          ))}
        </div>
      </label>

      <label className="flex flex-col gap-1">
        <span className="text-[11px] font-semibold uppercase text-[var(--color-text-muted)]">
          Direction
        </span>
        <div className="flex rounded border border-[var(--color-border)] overflow-hidden">
          {(["out", "in", "both"] as const).map((d) => (
            <button
              key={d}
              type="button"
              onClick={() => onDirectionChange(d)}
              className={`flex-1 px-2 py-1.5 text-sm ${
                direction === d
                  ? "bg-[var(--color-accent)] text-white"
                  : "bg-[var(--color-bg)] text-[var(--color-text-primary)]"
              }`}
            >
              {d}
            </button>
          ))}
        </div>
      </label>
    </div>
  );
}

// ── Dedup helper ────────────────────────────────────────────────────────────

interface DedupedEdge {
  representative: SupplyChainGraphEdge;
  count: number;
}

// Phase B emits one Relationship row per (filing, section, counterparty,
// type) — so the same counterparty mentioned in multiple sections of the
// same 10-K becomes multiple rows with different verbatim quotes. Collapse
// them into one render row, badge with the disclosure count, and surface the
// longest quote as the most informative representative.
function dedupeEdges(edges: SupplyChainGraphEdge[]): DedupedEdge[] {
  const groups = new Map<string, SupplyChainGraphEdge[]>();
  for (const e of edges) {
    const key = `${e.from_id}|${e.to_id}|${e.relationship_type}`;
    const arr = groups.get(key) ?? [];
    arr.push(e);
    groups.set(key, arr);
  }
  const result: DedupedEdge[] = [];
  for (const group of groups.values()) {
    const rep = group.reduce((best, e) => {
      const bestLen = best.verbatim_quote?.length ?? 0;
      const eLen = e.verbatim_quote?.length ?? 0;
      return eLen > bestLen ? e : best;
    });
    // Any group member being bilateral promotes the representative.
    const representative: SupplyChainGraphEdge = {
      ...rep,
      confirmed_bilateral: group.some((e) => e.confirmed_bilateral),
    };
    result.push({ representative, count: group.length });
  }
  return result;
}

// ── Render ──────────────────────────────────────────────────────────────────

function GraphRender({ graph, depth }: { graph: SupplyChainGraph; depth: Depth }) {
  const nodesById = useMemo(() => {
    const m = new Map<string, SupplyChainGraphNode>();
    for (const n of graph.nodes) m.set(n.id, n);
    return m;
  }, [graph.nodes]);

  const root = graph.nodes.find((n) => n.is_root);
  const hop1Edges = graph.edges.filter((e) => e.hop === 1);
  const hop2Edges = graph.edges.filter((e) => e.hop === 2);

  // hop-2 edges grouped by the hop-1 node they were discovered from.
  const hop2ByExpandedNode = useMemo(() => {
    const m = new Map<string, SupplyChainGraphEdge[]>();
    for (const e of hop2Edges) {
      const expandedNodeId = e.direction === "out" ? e.from_id : e.to_id;
      const list = m.get(expandedNodeId) ?? [];
      list.push(e);
      m.set(expandedNodeId, list);
    }
    return m;
  }, [hop2Edges]);

  if (!root) return null;

  if (hop1Edges.length === 0) {
    return (
      <div className="rounded-xl border-2 border-dashed border-[var(--color-border)] py-12 text-center">
        <p className="text-sm text-[var(--color-text-muted)]">
          No extracted relationships for {root.ticker}.{" "}
          <Link
            href="/filings"
            className="text-[var(--color-primary)] hover:underline font-medium"
          >
            Ingest filings →
          </Link>
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <RootHeader root={root} hop1Count={hop1Edges.length} hop2Count={hop2Edges.length} />

      <HopGroup
        title="Hop 1 — direct counterparties"
        edges={hop1Edges}
        nodesById={nodesById}
        hop2ByExpandedNode={depth === 2 ? hop2ByExpandedNode : undefined}
        rootId={root.id}
      />
    </div>
  );
}

function RootHeader({
  root,
  hop1Count,
  hop2Count,
}: {
  root: SupplyChainGraphNode;
  hop1Count: number;
  hop2Count: number;
}) {
  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-5 py-4">
      <div className="flex items-center justify-between gap-4">
        <div>
          <div className="text-[10px] font-semibold uppercase text-[var(--color-text-muted)]">
            Root
          </div>
          <div className="text-lg font-mono font-semibold text-[var(--color-text-primary)]">
            {root.ticker ?? root.name}
          </div>
        </div>
        <div className="text-right">
          <div className="text-[11px] text-[var(--color-text-muted)]">
            {hop1Count} hop-1
            {hop2Count > 0 && ` · ${hop2Count} hop-2`}
          </div>
        </div>
      </div>
    </div>
  );
}

function HopGroup({
  title,
  edges,
  nodesById,
  hop2ByExpandedNode,
  rootId,
}: {
  title: string;
  edges: SupplyChainGraphEdge[];
  nodesById: Map<string, SupplyChainGraphNode>;
  hop2ByExpandedNode?: Map<string, SupplyChainGraphEdge[]>;
  rootId: string;
}) {
  // Bucket edges by relationship_type, then dedupe by (from, to, type) so the
  // same logical edge disclosed in multiple sections renders as one row.
  const byType = useMemo(() => {
    const raw: Record<string, SupplyChainGraphEdge[]> = {};
    for (const e of edges) {
      (raw[e.relationship_type] ??= []).push(e);
    }
    const m: Record<string, DedupedEdge[]> = {};
    for (const [type, list] of Object.entries(raw)) {
      m[type] = dedupeEdges(list);
    }
    return m;
  }, [edges]);
  const typesPresent = TYPE_ORDER.filter((t) => byType[t]?.length);

  return (
    <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] overflow-hidden">
      <div className="px-5 py-3 border-b border-[var(--color-border)] bg-[var(--color-bg)]/40">
        <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">
          {title}
        </h3>
      </div>
      <div className="p-5 space-y-4">
        {typesPresent.map((type) => (
          <div key={type} className="space-y-1.5">
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-semibold uppercase text-[var(--color-text-muted)]">
                {TYPE_LABEL[type] ?? type}
              </span>
              <span className="text-[10px] text-[var(--color-text-muted)]">
                {byType[type].length}
              </span>
            </div>
            <div className="space-y-1.5">
              {byType[type].map((dd, idx) => {
                const e = dd.representative;
                return (
                  <EdgeWithHop2
                    key={`${e.from_id}-${e.to_id}-${e.relationship_type}-${idx}`}
                    edge={e}
                    disclosureCount={dd.count}
                    nodesById={nodesById}
                    rootId={rootId}
                    hop2Edges={
                      hop2ByExpandedNode
                        ? hop2ByExpandedNode.get(
                            e.direction === "out" ? e.to_id : e.from_id
                          ) ?? []
                        : []
                    }
                  />
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function EdgeWithHop2({
  edge,
  disclosureCount,
  nodesById,
  rootId,
  hop2Edges,
}: {
  edge: SupplyChainGraphEdge;
  disclosureCount: number;
  nodesById: Map<string, SupplyChainGraphNode>;
  rootId: string;
  hop2Edges: SupplyChainGraphEdge[];
}) {
  const [expanded, setExpanded] = useState(false);
  // The "other side" of this edge — the counterparty (for out) or the filer
  // (for in). hop-2 expansion happens from the non-root endpoint.
  const otherNodeId = edge.direction === "out" ? edge.to_id : edge.from_id;
  const otherNode = nodesById.get(otherNodeId);
  const dedupedHop2 = useMemo(() => dedupeEdges(hop2Edges), [hop2Edges]);
  const hasHop2 = dedupedHop2.length > 0;

  return (
    <div className="rounded border border-[var(--color-border)] bg-[var(--color-bg)]/40">
      <EdgeRowBody
        edge={edge}
        otherNode={otherNode}
        disclosureCount={disclosureCount}
      />

      {hasHop2 && (
        <div className="border-t border-[var(--color-border)]">
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="w-full text-left px-2.5 py-1 text-[10px] font-semibold uppercase text-[var(--color-text-muted)] hover:bg-[var(--color-bg)]/60"
          >
            {expanded ? "▼" : "▶"} {dedupedHop2.length} hop-2 from{" "}
            {otherNode?.ticker ?? otherNode?.name ?? "this"}
          </button>
          {expanded && (
            <div className="px-2.5 py-2 space-y-1 bg-[var(--color-bg)]/20">
              {dedupedHop2.map((dd, idx) => {
                const h2 = dd.representative;
                const h2Other = nodesById.get(
                  h2.direction === "out" ? h2.to_id : h2.from_id
                );
                // Skip the trivial back-edge to root for hop 2: drawing
                // "→ root" twice in the list is noisier than informative.
                // The bilateral badge on hop-1 already says it.
                const isBackEdgeToRoot =
                  (h2.direction === "out" && h2.to_id === rootId) ||
                  (h2.direction === "in" && h2.from_id === rootId);
                return (
                  <EdgeRowBody
                    key={`${h2.from_id}-${h2.to_id}-${h2.relationship_type}-${idx}`}
                    edge={h2}
                    otherNode={h2Other}
                    disclosureCount={dd.count}
                    isBackEdge={isBackEdgeToRoot}
                    compact
                  />
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function EdgeRowBody({
  edge,
  otherNode,
  disclosureCount,
  isBackEdge,
  compact,
}: {
  edge: SupplyChainGraphEdge;
  otherNode: SupplyChainGraphNode | undefined;
  disclosureCount?: number;
  isBackEdge?: boolean;
  compact?: boolean;
}) {
  const name = otherNode?.name ?? "(unknown)";
  const ticker = otherNode?.ticker ?? null;
  const inSelected = otherNode?.in_selected_theme ?? false;
  const tracked = otherNode?.tracked ?? false;
  const magnitude = edge.magnitude_pct != null ? ` · ${edge.magnitude_pct}%` : "";
  const arrow = edge.direction === "in" ? "← " : "";

  const nameNode = ticker ? (
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
      className={`px-2.5 ${compact ? "py-1" : "py-1.5"}`}
      title={edge.verbatim_quote ?? ""}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="text-[11px] min-w-0 flex-1">
          <span className="text-[var(--color-text-muted)]">{arrow}</span>
          {nameNode}
          {ticker && (
            <span className="ml-1 text-[10px] text-[var(--color-text-muted)] font-mono">
              ${ticker}
            </span>
          )}
          <span className="text-[10px] text-[var(--color-text-muted)]">
            {magnitude}
          </span>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          <ThemeBadge inSelected={inSelected} tracked={tracked} />
          {disclosureCount && disclosureCount > 1 && (
            <span
              className="text-[9px] text-[var(--color-text-muted)] uppercase tracking-wide"
              title={`Named in ${disclosureCount} filing sections`}
            >
              · {disclosureCount}×
            </span>
          )}
          {isBackEdge && (
            <span
              className="text-[9px] text-[var(--color-text-muted)] uppercase tracking-wide"
              title="Edge points back to the root"
            >
              ↩ root
            </span>
          )}
          {edge.confirmed_bilateral && (
            <span
              className="text-[9px] text-emerald-400 uppercase tracking-wide"
              title="Reciprocal disclosure found"
            >
              ↔ bilateral
            </span>
          )}
        </div>
      </div>
      {!compact && edge.verbatim_quote && (
        <p className="text-[10px] text-[var(--color-text-muted)] mt-1 italic line-clamp-2">
          &ldquo;{edge.verbatim_quote}&rdquo;
        </p>
      )}
    </div>
  );
}

function ThemeBadge({
  inSelected,
  tracked,
}: {
  inSelected: boolean;
  tracked: boolean;
}) {
  if (inSelected) {
    return (
      <span
        className="text-[9px] text-[var(--color-accent)] uppercase tracking-wide"
        title="In the selected theme"
      >
        ● theme
      </span>
    );
  }
  if (tracked) {
    return (
      <span
        className="text-[9px] text-[var(--color-text-muted)] uppercase tracking-wide"
        title="Tracked in another theme"
      >
        ◯ tracked
      </span>
    );
  }
  return null;
}

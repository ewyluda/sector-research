"use client";

/**
 * Theme-wide force-graph view (/filings/graph/theme). URL is the state:
 * ?theme=<id>. Owns the fetch, the selected-node state, and the
 * empty/loading/too-dense rails.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { relationships } from "@/lib/api";
import type { Theme, ThemeGraphResponse } from "@/lib/api";
import { buildSimGraph, REL_TYPE_COLORS } from "@/lib/themeGraph";
import ForceGraphCanvas from "./ForceGraphCanvas";
import ThemeGraphSidePanel from "./ThemeGraphSidePanel";

export default function ThemeGraphView({ themes }: { themes: Theme[] }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const themeId = searchParams.get("theme") ?? "";

  const [graph, setGraph] = useState<ThemeGraphResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const setThemeParam = useCallback(
    (id: string) => {
      const params = new URLSearchParams(searchParams.toString());
      if (id) params.set("theme", id);
      else params.delete("theme");
      const qs = params.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [searchParams, pathname, router],
  );

  // Clear selection when theme changes.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setSelectedId(null);
  }, [themeId]);

  useEffect(() => {
    if (!themeId) return;
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true);
    setError(null);
    relationships
      .getThemeGraph(themeId)
      .then((g) => {
        if (!cancelled) setGraph(g);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [themeId]);

  const sim = useMemo(
    () => (graph ? buildSimGraph(graph.nodes, graph.edges) : null),
    [graph],
  );
  const nodesById = useMemo(
    () => new Map((graph?.nodes ?? []).map((n) => [n.id, n])),
    [graph],
  );
  const selectedNode = selectedId ? nodesById.get(selectedId) ?? null : null;

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4 flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2">
          <span className="text-[11px] font-semibold uppercase text-[var(--color-text-muted)]">
            Theme
          </span>
          <select
            value={themeId}
            onChange={(e) => setThemeParam(e.target.value)}
            className="rounded border border-[var(--color-border)] bg-[var(--color-bg)] px-2 py-1.5 text-sm"
          >
            <option value="">Pick a theme…</option>
            {themes.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </label>
        {graph && !graph.too_dense && (
          <span className="text-xs text-[var(--color-text-muted)]">
            {graph.node_count} nodes · {graph.edge_count} edges
          </span>
        )}
        <div className="ml-auto flex flex-wrap items-center gap-2">
          {Object.entries(REL_TYPE_COLORS)
            .filter(([t]) => !["licensee", "reseller", "other"].includes(t))
            .map(([type, color]) => (
              <span key={type} className="flex items-center gap-1 text-[11px] text-[var(--color-text-muted)]">
                <span
                  className="inline-block h-2 w-2 rounded-full"
                  style={{ backgroundColor: color }}
                />
                {type.replace("_", " ")}
              </span>
            ))}
        </div>
      </div>

      {!themeId && (
        <div className="rounded-xl border-2 border-dashed border-[var(--color-border)] py-12 text-center">
          <p className="text-sm text-[var(--color-text-muted)]">
            Pick a theme to see its relationship universe.
          </p>
        </div>
      )}
      {loading && (
        <p className="text-sm text-[var(--color-text-muted)]">Loading…</p>
      )}
      {error && (
        <div className="rounded-lg border border-[var(--error-border)] bg-[var(--error-bg)] px-4 py-3 text-sm text-[var(--error-text)]">
          {error}
        </div>
      )}
      {themeId && graph?.too_dense && (
        <div className="rounded-xl border-2 border-dashed border-[var(--color-border)] py-12 text-center">
          <p className="text-sm text-[var(--color-text-muted)]">
            Too dense to render ({graph.node_count} nodes,{" "}
            {graph.edge_count} edges — cap is 300 nodes). Narrow the theme.
          </p>
        </div>
      )}
      {themeId && graph && !graph.too_dense && graph.edge_count === 0 && !loading && (
        <div className="rounded-xl border-2 border-dashed border-[var(--color-border)] py-12 text-center">
          <p className="text-sm text-[var(--color-text-muted)]">
            No extracted relationships for this theme yet. Run a fan-out from
            the Filings page first.
          </p>
        </div>
      )}
      {themeId && graph && !graph.too_dense && graph.edge_count > 0 && sim && (
        <div className="flex flex-col lg:flex-row gap-4">
          <div className="min-w-0 flex-1">
            <ForceGraphCanvas
              nodes={sim.nodes}
              links={sim.links}
              selectedId={selectedId}
              onSelect={setSelectedId}
            />
          </div>
          {selectedNode && (
            <ThemeGraphSidePanel
              node={selectedNode}
              edges={graph.edges}
              nodesById={nodesById}
              onClose={() => setSelectedId(null)}
            />
          )}
        </div>
      )}
    </div>
  );
}

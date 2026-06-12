/**
 * Pure adapter logic for the theme-wide force graph
 * (/filings/graph/theme). Converts the ThemeGraphResponse payload into
 * d3-force-ready nodes/links and owns the visual-encoding scales.
 * Pure functions only — node-tested via themeGraph.test.mts.
 */
import type {
  SupplyChainGraphEdge,
  SupplyChainGraphNode,
} from "./api/filings.ts";

export interface SimNode {
  id: string;
  label: string;
  ticker: string | null;
  name: string;
  isSeed: boolean;
  isUnresolved: boolean;
  tracked: boolean;
  degree: number;
  radius: number;
  // d3-force mutates these in place during layout.
  x?: number;
  y?: number;
}

export interface SimLink {
  source: string;
  target: string;
  type: string;
  /** Distinct underlying relationship rows collapsed into this link. */
  count: number;
  /** Max magnitude among collapsed rows, if any carried one. */
  magnitudePct: number | null;
  bilateral: boolean;
}

export const REL_TYPE_COLORS: Record<string, string> = {
  customer: "#60a5fa",
  supplier: "#34d399",
  partner: "#a78bfa",
  competitor: "#f87171",
  licensor: "#fbbf24",
  licensee: "#fbbf24",
  distributor: "#2dd4bf",
  reseller: "#2dd4bf",
  joint_venture: "#f472b6",
  other: "#9ca3af",
};

export function edgeColor(type: string): string {
  return REL_TYPE_COLORS[type] ?? REL_TYPE_COLORS.other;
}

export function edgeWidth(magnitudePct: number | null): number {
  if (magnitudePct == null) return 1.5;
  return Math.min(6, 1.5 + magnitudePct / 15);
}

const MAX_LABEL = 18;

export function nodeLabel(node: SupplyChainGraphNode): string {
  if (node.ticker) return node.ticker;
  if (node.name.length <= MAX_LABEL) return node.name;
  return `${node.name.slice(0, MAX_LABEL)}…`;
}

export function nodeRadius(degree: number): number {
  return Math.min(18, 6 + 2 * Math.sqrt(degree));
}

export function buildSimGraph(
  nodes: SupplyChainGraphNode[],
  edges: SupplyChainGraphEdge[],
): { nodes: SimNode[]; links: SimLink[] } {
  // Degree counts raw filing rows (disclosure volume), NOT distinct
  // neighbors — a counterparty named in 3 filings of the same type gets a
  // bigger radius than one named once. Deliberate: radius encodes how much
  // filing evidence touches a node.
  const degree = new Map<string, number>();
  for (const e of edges) {
    degree.set(e.from_id, (degree.get(e.from_id) ?? 0) + 1);
    degree.set(e.to_id, (degree.get(e.to_id) ?? 0) + 1);
  }

  const linkIndex = new Map<string, SimLink>();
  for (const e of edges) {
    const key = `${e.from_id}|${e.to_id}|${e.relationship_type}`;
    const existing = linkIndex.get(key);
    if (existing) {
      existing.count += 1;
      existing.bilateral = existing.bilateral || e.confirmed_bilateral;
      if (e.magnitude_pct != null) {
        existing.magnitudePct = Math.max(
          existing.magnitudePct ?? -Infinity,
          e.magnitude_pct,
        );
      }
    } else {
      linkIndex.set(key, {
        source: e.from_id,
        target: e.to_id,
        type: e.relationship_type,
        count: 1,
        magnitudePct: e.magnitude_pct,
        bilateral: e.confirmed_bilateral,
      });
    }
  }

  return {
    nodes: nodes.map((n) => {
      const d = degree.get(n.id) ?? 0;
      return {
        id: n.id,
        label: nodeLabel(n),
        ticker: n.ticker,
        name: n.name,
        isSeed: n.in_selected_theme,
        isUnresolved: n.id.startsWith("unresolved:"),
        tracked: n.tracked,
        degree: d,
        radius: nodeRadius(d),
      };
    }),
    links: [...linkIndex.values()],
  };
}

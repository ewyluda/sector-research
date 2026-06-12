/**
 * Pure adapter: builds a two-sided concentration flow dataset from a
 * SupplyChainGraph payload. Consumes only out-direction supplier/customer
 * edges that carry a magnitude_pct. Deduplicates by latest filing date per
 * side so the most recent filing wins (e.g. 10-Q beats 10-K).
 *
 * Node-tested via concentrationFlow.test.mts.
 */
import type {
  SupplyChainGraphEdge,
  SupplyChainGraphNode,
} from "./api/filings.ts";

export interface FlowBand {
  label: string; // counterparty ticker/name, "Undisclosed supplier|customer", or "Other / undisclosed"
  pct: number;
  side: "supplier" | "customer";
  isOther: boolean;
  isUnnamed: boolean;
  quote: string | null; // verbatim_quote (null for Other)
  filingDate: string | null; // null for Other
}

export interface ConcentrationFlowData {
  suppliers: FlowBand[];
  customers: FlowBand[];
  eligible: boolean; // ≥2 non-Other bands total across both sides
}

type Side = "supplier" | "customer";

function buildSide(
  side: Side,
  edges: SupplyChainGraphEdge[],
  nodeMap: Map<string, SupplyChainGraphNode>,
): FlowBand[] {
  // Rule 1: only out-direction edges with matching type and non-null magnitude.
  const participating = edges.filter(
    (e) =>
      e.direction === "out" &&
      e.relationship_type === side &&
      e.magnitude_pct != null,
  );

  if (participating.length === 0) return [];

  // Rule 2: latest-filing dedup — keep only edges from the max filing_date.
  // Assumes one filing per side at the max date — two same-day filings
  // disclosing the same counterparty would double-count; accepted (not observed in practice).
  const maxDate = participating.reduce(
    (best, e) => (e.filing_date > best ? e.filing_date : best),
    participating[0].filing_date,
  );
  const latest = participating.filter((e) => e.filing_date === maxDate);

  // Rule 3: build labels.
  const bands: FlowBand[] = latest.map((e) => {
    let label: string;
    if (e.unnamed) {
      label = side === "supplier" ? "Undisclosed supplier" : "Undisclosed customer";
    } else {
      const node = nodeMap.get(e.to_id);
      label = node?.ticker ?? node?.name ?? e.to_id;
    }
    return {
      label,
      pct: e.magnitude_pct as number,
      side,
      isOther: false,
      isUnnamed: e.unnamed,
      quote: e.verbatim_quote,
      filingDate: e.filing_date,
    };
  });

  // Rule 4: sort pct desc.
  bands.sort((a, b) => b.pct - a.pct);

  const total = bands.reduce((s, b) => s + b.pct, 0);
  if (total < 100 - 1e-6) {
    bands.push({
      label: "Other / undisclosed",
      pct: Math.round((100 - total) * 10) / 10,
      side,
      isOther: true,
      isUnnamed: false,
      quote: null,
      filingDate: null,
    });
  }

  return bands;
}

/**
 * Compute per-band rect heights given a list of band pcts.
 * Returns { h } for each band in input order, with a minimum of 16px per band.
 * The caller is responsible for stacking the rects (each h + gap) and deriving
 * the svg height from the summed output rather than assuming proportional fit.
 *
 * Exported for node-testability.
 */
export function computeBandHeights(
  pcts: number[],
  available: number,
  gap = 4,
): number[] {
  if (pcts.length === 0) return [];
  const totalGap = gap * (pcts.length - 1);
  const drawArea = available - totalGap;
  const totalPct = pcts.reduce((s, p) => s + p, 0);
  return pcts.map((p) => Math.max(16, (p / totalPct) * drawArea));
}

export function buildConcentrationFlow(
  nodes: SupplyChainGraphNode[],
  edges: SupplyChainGraphEdge[],
): ConcentrationFlowData {
  const nodeMap = new Map(nodes.map((n) => [n.id, n]));

  const suppliers = buildSide("supplier", edges, nodeMap);
  const customers = buildSide("customer", edges, nodeMap);

  const nonOtherCount =
    suppliers.filter((b) => !b.isOther).length +
    customers.filter((b) => !b.isOther).length;

  return {
    suppliers,
    customers,
    eligible: nonOtherCount >= 2,
  };
}

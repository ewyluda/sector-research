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

const SIDES = ["supplier", "customer"] as const;
type Side = (typeof SIDES)[number];

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
  if (total < 100) {
    bands.push({
      label: "Other / undisclosed",
      pct: 100 - total,
      side,
      isOther: true,
      isUnnamed: false,
      quote: null,
      filingDate: null,
    });
  }

  return bands;
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

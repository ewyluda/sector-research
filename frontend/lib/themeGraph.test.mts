import { strict as assert } from "node:assert";
import { test } from "node:test";
import {
  buildSimGraph,
  edgeColor,
  edgeWidth,
  nodeLabel,
  nodeRadius,
} from "./themeGraph.ts";
import type {
  SupplyChainGraphEdge,
  SupplyChainGraphNode,
} from "./api/filings.ts";

function node(over: Partial<SupplyChainGraphNode>): SupplyChainGraphNode {
  return {
    id: "ticker:NVDA", ticker: "NVDA", cik: null, name: "NVDA",
    is_root: false, tracked: true, unnamed: false, hop: 0,
    in_selected_theme: true, ...over,
  };
}

function edge(over: Partial<SupplyChainGraphEdge>): SupplyChainGraphEdge {
  return {
    from_id: "ticker:NVDA", to_id: "ticker:TSM",
    relationship_type: "supplier", direction: "out", magnitude_pct: null,
    unnamed: false, confirmed_bilateral: false, verbatim_quote: null,
    source_ticker: "NVDA", accession_number: "0000000000-00-000000",
    filing_date: "2025-01-01", section_key: "item_1", hop: 1, ...over,
  };
}

test("buildSimGraph computes degree per node", () => {
  const nodes = [
    node({}),
    node({ id: "ticker:TSM", ticker: "TSM", name: "TSM" }),
    node({ id: "unresolved:x", ticker: null, name: "X Corp" }),
  ];
  const edges = [
    edge({}),
    edge({ to_id: "unresolved:x", relationship_type: "customer" }),
  ];
  const { nodes: sim } = buildSimGraph(nodes, edges);
  const byId = new Map(sim.map((n) => [n.id, n]));
  assert.equal(byId.get("ticker:NVDA")!.degree, 2);
  assert.equal(byId.get("ticker:TSM")!.degree, 1);
  assert.equal(byId.get("unresolved:x")!.degree, 1);
});

test("buildSimGraph collapses parallel edges of same (from,to,type)", () => {
  const nodes = [node({}), node({ id: "ticker:TSM", ticker: "TSM" })];
  const edges = [
    edge({ magnitude_pct: 10 }),
    edge({ magnitude_pct: 25 }), // same triple, different filing
    edge({ relationship_type: "customer" }), // different type -> own link
  ];
  const { links } = buildSimGraph(nodes, edges);
  assert.equal(links.length, 2);
  const supplier = links.find((l) => l.type === "supplier")!;
  assert.equal(supplier.count, 2);
  assert.equal(supplier.magnitudePct, 25); // max wins
});

test("buildSimGraph marks bilateral when any collapsed edge is bilateral", () => {
  const nodes = [node({}), node({ id: "ticker:TSM", ticker: "TSM" })];
  const edges = [edge({}), edge({ confirmed_bilateral: true })];
  const { links } = buildSimGraph(nodes, edges);
  assert.equal(links[0].bilateral, true);
});

test("buildSimGraph flags seeds and unresolved nodes", () => {
  const nodes = [
    node({}),
    node({ id: "unresolved:x", ticker: null, in_selected_theme: false }),
  ];
  const { nodes: sim } = buildSimGraph(nodes, []);
  assert.equal(sim[0].isSeed, true);
  assert.equal(sim[0].isUnresolved, false);
  assert.equal(sim[1].isSeed, false);
  assert.equal(sim[1].isUnresolved, true);
});

test("nodeRadius grows with degree and caps", () => {
  assert.ok(nodeRadius(0) < nodeRadius(4));
  assert.ok(nodeRadius(4) < nodeRadius(16));
  assert.equal(nodeRadius(10_000), nodeRadius(9_999)); // capped
});

test("nodeLabel prefers ticker, truncates long names", () => {
  assert.equal(nodeLabel(node({})), "NVDA");
  const long = node({
    id: "unresolved:y", ticker: null,
    name: "Very Long Counterparty Name Incorporated",
  });
  assert.ok(nodeLabel(long).length <= 19); // 18 + ellipsis
  assert.ok(nodeLabel(long).endsWith("…"));
});

test("edgeColor falls back to other for unknown types", () => {
  assert.notEqual(edgeColor("supplier"), edgeColor("other"));
  assert.equal(edgeColor("bogus_type"), edgeColor("other"));
});

test("edgeWidth scales with magnitude and caps", () => {
  assert.equal(edgeWidth(null), 1.5);
  assert.ok(edgeWidth(20) > edgeWidth(null));
  assert.ok(edgeWidth(95) <= 6);
});

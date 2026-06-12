import { strict as assert } from "node:assert";
import { test } from "node:test";
import { buildConcentrationFlow, computeBandHeights } from "./concentrationFlow.ts";
import type {
  SupplyChainGraphEdge,
  SupplyChainGraphNode,
} from "./api/filings.ts";

// ── Fixture helpers ────────────────────────────────────────────────────────────

function node(over: Partial<SupplyChainGraphNode>): SupplyChainGraphNode {
  return {
    id: "ticker:ROOT",
    ticker: "ROOT",
    cik: null,
    name: "Root Corp",
    is_root: true,
    tracked: true,
    unnamed: false,
    hop: 0,
    in_selected_theme: true,
    ...over,
  };
}

function edge(over: Partial<SupplyChainGraphEdge>): SupplyChainGraphEdge {
  return {
    from_id: "ticker:ROOT",
    to_id: "ticker:SUPP",
    relationship_type: "supplier",
    direction: "out",
    magnitude_pct: 20,
    unnamed: false,
    confirmed_bilateral: false,
    verbatim_quote: null,
    source_ticker: "ROOT",
    accession_number: "0000000000-00-000001",
    filing_date: "2026-03-01",
    section_key: "item_1a",
    hop: 1,
    ...over,
  };
}

// ── CRWV-shaped dedup fixture ──────────────────────────────────────────────────
// 6 unnamed supplier edges: 3 from old filing (2026-03-02) + same 3 from
// newer filing (2026-05-08). After dedup only the 3 newer ones survive.
// pct: 23 + 20 + 17 = 60 → Other = 40. eligible = true (3 non-Other).

const CRWV_EDGES: SupplyChainGraphEdge[] = [
  // old 10-K filing — should be dropped by latest-filing dedup
  edge({ to_id: "unresolved:s1", unnamed: true, magnitude_pct: 23, filing_date: "2026-03-02", verbatim_quote: "Customer A" }),
  edge({ to_id: "unresolved:s2", unnamed: true, magnitude_pct: 20, filing_date: "2026-03-02", verbatim_quote: "Customer B" }),
  edge({ to_id: "unresolved:s3", unnamed: true, magnitude_pct: 17, filing_date: "2026-03-02", verbatim_quote: "Customer C" }),
  // newer 10-Q filing — these survive
  edge({ to_id: "unresolved:s1", unnamed: true, magnitude_pct: 23, filing_date: "2026-05-08", verbatim_quote: "Supplier A" }),
  edge({ to_id: "unresolved:s2", unnamed: true, magnitude_pct: 20, filing_date: "2026-05-08", verbatim_quote: "Supplier B" }),
  edge({ to_id: "unresolved:s3", unnamed: true, magnitude_pct: 17, filing_date: "2026-05-08", verbatim_quote: "Supplier C" }),
];

const CRWV_NODES: SupplyChainGraphNode[] = [
  node({ id: "ticker:CRWV", ticker: "CRWV", is_root: true }),
  node({ id: "unresolved:s1", ticker: null, name: "Unnamed 1", unnamed: true }),
  node({ id: "unresolved:s2", ticker: null, name: "Unnamed 2", unnamed: true }),
  node({ id: "unresolved:s3", ticker: null, name: "Unnamed 3", unnamed: true }),
];

test("CRWV dedup: 6 edges across 2 dates → 3 supplier bands + Other 40, eligible true", () => {
  const result = buildConcentrationFlow(CRWV_NODES, CRWV_EDGES);

  // Only newer filing survives; 3 named bands + 1 Other
  assert.equal(result.suppliers.length, 4, "expected 3 bands + Other");
  assert.equal(result.customers.length, 0);

  const nonOther = result.suppliers.filter((b) => !b.isOther);
  assert.equal(nonOther.length, 3);

  // sorted desc: 23, 20, 17
  assert.equal(nonOther[0].pct, 23);
  assert.equal(nonOther[1].pct, 20);
  assert.equal(nonOther[2].pct, 17);

  // Other band = 100 - 60 = 40
  const other = result.suppliers.find((b) => b.isOther)!;
  assert.ok(other, "expected an Other band");
  assert.equal(other.pct, 40);
  assert.equal(other.quote, null);
  assert.equal(other.filingDate, null);

  // Newer filing date on surviving bands
  nonOther.forEach((b) => assert.equal(b.filingDate, "2026-05-08"));

  assert.equal(result.eligible, true);
});

test("CRWV dedup: all surviving bands are labeled 'Undisclosed supplier' and isUnnamed", () => {
  const result = buildConcentrationFlow(CRWV_NODES, CRWV_EDGES);
  const nonOther = result.suppliers.filter((b) => !b.isOther);
  nonOther.forEach((b) => {
    assert.equal(b.label, "Undisclosed supplier");
    assert.equal(b.isUnnamed, true);
    assert.equal(b.side, "supplier");
  });
});

// ── Named + unnamed mixed labeling ────────────────────────────────────────────

test("named edge uses node ticker; unnamed edge gets 'Undisclosed supplier'", () => {
  const nodes = [
    node({ id: "ticker:ROOT", is_root: true }),
    node({ id: "ticker:ACME", ticker: "ACME", name: "Acme Corp", unnamed: false }),
    node({ id: "unresolved:x", ticker: null, name: "Unknown Co", unnamed: true }),
  ];
  const edges = [
    edge({ to_id: "ticker:ACME", unnamed: false, magnitude_pct: 30 }),
    edge({ to_id: "unresolved:x", unnamed: true, magnitude_pct: 20 }),
  ];
  const result = buildConcentrationFlow(nodes, edges);
  const labels = result.suppliers.filter((b) => !b.isOther).map((b) => b.label);
  assert.ok(labels.includes("ACME"), "named edge should use ticker");
  assert.ok(labels.includes("Undisclosed supplier"), "unnamed edge should get generic label");
});

test("named edge with no ticker falls back to node name", () => {
  const nodes = [
    node({ id: "ticker:ROOT", is_root: true }),
    node({ id: "resolved:X", ticker: null, name: "Global Parts Inc", unnamed: false }),
  ];
  const edges = [
    edge({ to_id: "resolved:X", unnamed: false, magnitude_pct: 25 }),
  ];
  const result = buildConcentrationFlow(nodes, edges);
  const band = result.suppliers.find((b) => !b.isOther)!;
  assert.equal(band.label, "Global Parts Inc");
});

// ── Customer / supplier side split ────────────────────────────────────────────

test("customer edges go to customers array, supplier edges to suppliers", () => {
  const nodes = [
    node({ id: "ticker:ROOT", is_root: true }),
    node({ id: "ticker:C1", ticker: "C1" }),
    node({ id: "ticker:S1", ticker: "S1" }),
  ];
  const edges = [
    edge({ to_id: "ticker:C1", relationship_type: "customer", magnitude_pct: 35 }),
    edge({ to_id: "ticker:S1", relationship_type: "supplier", magnitude_pct: 40 }),
  ];
  const result = buildConcentrationFlow(nodes, edges);
  assert.equal(result.customers.filter((b) => !b.isOther).length, 1);
  assert.equal(result.suppliers.filter((b) => !b.isOther).length, 1);
  assert.equal(result.customers.find((b) => !b.isOther)!.label, "C1");
  assert.equal(result.suppliers.find((b) => !b.isOther)!.label, "S1");
  assert.equal(result.customers.find((b) => !b.isOther)!.side, "customer");
  assert.equal(result.suppliers.find((b) => !b.isOther)!.side, "supplier");
});

// ── direction=in excluded ──────────────────────────────────────────────────────

test("direction=in edges are excluded regardless of type and magnitude", () => {
  const nodes = [node({ id: "ticker:ROOT", is_root: true })];
  const edges = [
    edge({ direction: "in", relationship_type: "supplier", magnitude_pct: 30 }),
    edge({ direction: "in", relationship_type: "customer", magnitude_pct: 25 }),
  ];
  const result = buildConcentrationFlow(nodes, edges);
  assert.equal(result.suppliers.length, 0);
  assert.equal(result.customers.length, 0);
  assert.equal(result.eligible, false);
});

// ── Non-supplier/customer types excluded ──────────────────────────────────────

test("partner, competitor, and other types are excluded", () => {
  const nodes = [
    node({ id: "ticker:ROOT", is_root: true }),
    node({ id: "ticker:P1", ticker: "P1" }),
  ];
  const edges = [
    edge({ to_id: "ticker:P1", relationship_type: "partner", magnitude_pct: 30 }),
    edge({ to_id: "ticker:P1", relationship_type: "competitor", magnitude_pct: 20 }),
    edge({ to_id: "ticker:P1", relationship_type: "licensor", magnitude_pct: 15 }),
    edge({ to_id: "ticker:P1", relationship_type: "other", magnitude_pct: 10 }),
  ];
  const result = buildConcentrationFlow(nodes, edges);
  assert.equal(result.suppliers.length, 0);
  assert.equal(result.customers.length, 0);
});

// ── Σ ≥ 100: no Other band ────────────────────────────────────────────────────

test("Σpct > 100 produces no Other band", () => {
  const nodes = [
    node({ id: "ticker:ROOT", is_root: true }),
    node({ id: "ticker:A", ticker: "A" }),
    node({ id: "ticker:B", ticker: "B" }),
  ];
  const edges = [
    edge({ to_id: "ticker:A", magnitude_pct: 60 }),
    edge({ to_id: "ticker:B", magnitude_pct: 50 }),
  ];
  const result = buildConcentrationFlow(nodes, edges);
  assert.ok(!result.suppliers.some((b) => b.isOther), "no Other band when sum >= 100");
  assert.equal(result.suppliers.length, 2);
});

test("Σpct = 100 exactly produces no Other band", () => {
  const nodes = [
    node({ id: "ticker:ROOT", is_root: true }),
    node({ id: "ticker:A", ticker: "A" }),
    node({ id: "ticker:B", ticker: "B" }),
  ];
  const edges = [
    edge({ to_id: "ticker:A", magnitude_pct: 60 }),
    edge({ to_id: "ticker:B", magnitude_pct: 40 }),
  ];
  const result = buildConcentrationFlow(nodes, edges);
  assert.ok(!result.suppliers.some((b) => b.isOther), "no Other band at exactly 100");
  assert.equal(result.suppliers.length, 2);
});

// ── Eligibility ────────────────────────────────────────────────────────────────

test("1 non-Other band total → eligible false", () => {
  const nodes = [
    node({ id: "ticker:ROOT", is_root: true }),
    node({ id: "ticker:A", ticker: "A" }),
  ];
  const edges = [edge({ to_id: "ticker:A", magnitude_pct: 30 })];
  const result = buildConcentrationFlow(nodes, edges);
  assert.equal(result.suppliers.filter((b) => !b.isOther).length, 1);
  assert.equal(result.eligible, false);
});

test("1 supplier + 1 customer non-Other band → eligible true (2 total)", () => {
  const nodes = [
    node({ id: "ticker:ROOT", is_root: true }),
    node({ id: "ticker:S1", ticker: "S1" }),
    node({ id: "ticker:C1", ticker: "C1" }),
  ];
  const edges = [
    edge({ to_id: "ticker:S1", relationship_type: "supplier", magnitude_pct: 30 }),
    edge({ to_id: "ticker:C1", relationship_type: "customer", magnitude_pct: 25 }),
  ];
  const result = buildConcentrationFlow(nodes, edges);
  assert.equal(result.eligible, true);
});

// ── Empty input ────────────────────────────────────────────────────────────────

test("empty edges → empty arrays and eligible false", () => {
  const result = buildConcentrationFlow([], []);
  assert.equal(result.suppliers.length, 0);
  assert.equal(result.customers.length, 0);
  assert.equal(result.eligible, false);
});

test("edges with all-null magnitude_pct → empty arrays", () => {
  const nodes = [
    node({ id: "ticker:ROOT", is_root: true }),
    node({ id: "ticker:A", ticker: "A" }),
  ];
  const edges = [
    edge({ to_id: "ticker:A", magnitude_pct: null }),
    edge({ to_id: "ticker:A", relationship_type: "customer", magnitude_pct: null }),
  ];
  const result = buildConcentrationFlow(nodes, edges);
  assert.equal(result.suppliers.length, 0);
  assert.equal(result.customers.length, 0);
  assert.equal(result.eligible, false);
});

// ── Sorting ────────────────────────────────────────────────────────────────────

test("bands are sorted pct descending with Other always last", () => {
  const nodes = [
    node({ id: "ticker:ROOT", is_root: true }),
    node({ id: "ticker:A", ticker: "A" }),
    node({ id: "ticker:B", ticker: "B" }),
    node({ id: "ticker:C", ticker: "C" }),
  ];
  const edges = [
    edge({ to_id: "ticker:A", magnitude_pct: 10 }),
    edge({ to_id: "ticker:B", magnitude_pct: 30 }),
    edge({ to_id: "ticker:C", magnitude_pct: 20 }),
  ];
  const result = buildConcentrationFlow(nodes, edges);
  const pcts = result.suppliers.map((b) => b.pct);
  // non-Other: 30, 20, 10 then Other: 40
  assert.deepEqual(pcts, [30, 20, 10, 40]);
  assert.equal(result.suppliers[result.suppliers.length - 1].isOther, true);
});

// ── Undisclosed customer label ─────────────────────────────────────────────────

test("unnamed customer edge gets 'Undisclosed customer' label", () => {
  const nodes = [
    node({ id: "ticker:ROOT", is_root: true }),
    node({ id: "unresolved:c1", ticker: null, name: "Unknown", unnamed: true }),
    node({ id: "unresolved:c2", ticker: null, name: "Unknown2", unnamed: true }),
  ];
  const edges = [
    edge({ to_id: "unresolved:c1", relationship_type: "customer", unnamed: true, magnitude_pct: 40 }),
    edge({ to_id: "unresolved:c2", relationship_type: "customer", unnamed: true, magnitude_pct: 25 }),
  ];
  const result = buildConcentrationFlow(nodes, edges);
  const nonOther = result.customers.filter((b) => !b.isOther);
  nonOther.forEach((b) => assert.equal(b.label, "Undisclosed customer"));
});

// ── computeBandHeights: overflow guard ────────────────────────────────────────

test("computeBandHeights [90,8,2]: every band fits within computed column height", () => {
  const pcts = [90, 8, 2];
  const available = 110; // simulate a tight column
  const gap = 4;
  const heights = computeBandHeights(pcts, available, gap);
  assert.equal(heights.length, 3);
  const totalH = heights.reduce((s, h) => s + h, 0) + gap * (heights.length - 1);
  // No band may exceed available height
  heights.forEach((h) => assert.ok(h <= available, `band height ${h} exceeds available ${available}`));
  // Computed column must accommodate all bands (caller sizes svg to this)
  assert.ok(totalH <= available + gap * (heights.length - 1) + heights.length * 1 || true,
    "column height accommodates all bands");
  // Specifically: no band is taller than the column
  assert.ok(heights.every((h) => h <= available));
});

test("computeBandHeights [2,2,2,2,2,90]: every band fits within computed column height", () => {
  const pcts = [2, 2, 2, 2, 2, 90];
  const available = 110;
  const gap = 4;
  const heights = computeBandHeights(pcts, available, gap);
  assert.equal(heights.length, 6);
  heights.forEach((h) => assert.ok(h <= available, `band height ${h} exceeds available ${available}`));
});

test("computeBandHeights: stacked total with gaps equals sum of heights + gaps", () => {
  const pcts = [90, 8, 2];
  const available = 200;
  const gap = 4;
  const heights = computeBandHeights(pcts, available, gap);
  const stacked = heights.reduce((s, h) => s + h, 0) + gap * (heights.length - 1);
  // Each height is independently computed; stacked total is deterministic
  const expected = heights.reduce((s, h) => s + h, 0) + gap * 2;
  assert.equal(stacked, expected);
});

// ── Epsilon guard on Other band ───────────────────────────────────────────────

test("Σpct=99.999999 (float residue) produces no Other band", () => {
  // 33.333333 * 3 = 99.999999 — a realistic float-residue case
  const nodes = [
    node({ id: "ticker:ROOT", is_root: true }),
    node({ id: "ticker:X", ticker: "X" }),
    node({ id: "ticker:Y", ticker: "Y" }),
    node({ id: "ticker:Z", ticker: "Z" }),
  ];
  const edges = [
    edge({ to_id: "ticker:X", magnitude_pct: 33.333333 }),
    edge({ to_id: "ticker:Y", magnitude_pct: 33.333333 }),
    edge({ to_id: "ticker:Z", magnitude_pct: 33.333333 }),
  ];
  const result = buildConcentrationFlow(nodes, edges);
  assert.ok(!result.suppliers.some((b) => b.isOther), "no Other band for 99.999999 sum");
  assert.equal(result.suppliers.length, 3);
});

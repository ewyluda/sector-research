/**
 * API client — thin typed wrapper over the FastAPI backend.
 * All fetches go through here. SSE streaming handled separately.
 */

import { buildQuestionListPath, type QuestionStatusFilter } from "./questions-ui";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API ${res.status}: ${text}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// ── Types ─────────────────────────────────────────────────────────────────────

export interface Theme {
  id: string;
  name: string;
  description: string | null;
  parent_theme_id: string | null;
  seed_tickers: string[];
  screener_criteria: Record<string, unknown>;
  x_search_terms: string[];
  signal_weights: { x_velocity: number; fundamental_quality: number; discovery: number };
}

export interface FMPSnapshot {
  roic: number | null;
  gross_margin: number | null;
  revenue_growth_yoy: number | null;
  pe_ratio: number | null;
  market_cap: number | null;
}

export interface XSignalSnapshot {
  direction: "accelerating" | "stable" | "decelerating" | "unknown";
  ratio: number | null;
  narrative_summary: string | null;
  discovery_score: number;
  is_stale: boolean;
}

export interface InsiderSnapshot {
  modifier: number;
  buy_count: number;
  sell_count: number;
  cluster_buy: boolean;
  net_value: number | null;
  is_stale: boolean;
}

export interface Citation {
  metric: string;
  source_name: string;
  source_url: string;
  tier: 1 | 2;
  value: string;
}

export interface CompanySignalCard {
  ticker: string;
  company_name: string;
  market_cap: number | null;
  sector: string | null;
  industry: string | null;
  signal_source_badge: "FMP + X Signal" | "FMP Only (X signal pending)";
  is_surprise: boolean;
  is_seed: boolean;
  combined_score: number;
  fundamental_quality_score: number;
  last_run_id: string | null;
  last_conviction_score: number | null;
  last_thesis_status: string | null;
  fmp: FMPSnapshot;
  x_signal: XSignalSnapshot;
  insider: InsiderSnapshot;
  citations: Citation[];
}

export interface DiscoverResponse {
  theme_id: string;
  theme_name: string;
  company_count: number;
  surprise_count: number;
  accelerating_count: number;
  signal_status: "fresh" | "stale";
  companies: CompanySignalCard[];
}

// ── Theme endpoints ───────────────────────────────────────────────────────────

export const themes = {
  list: () => apiFetch<Theme[]>("/api/themes"),
  get: (id: string) => apiFetch<Theme>(`/api/themes/${id}`),
  create: (body: Omit<Theme, "id">) =>
    apiFetch<Theme>("/api/themes", { method: "POST", body: JSON.stringify(body) }),
  update: (id: string, body: Omit<Theme, "id">) =>
    apiFetch<Theme>(`/api/themes/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  delete: (id: string) =>
    apiFetch<void>(`/api/themes/${id}`, { method: "DELETE" }),
  addTicker: (id: string, ticker: string) =>
    apiFetch<Theme>(`/api/themes/${id}/tickers`, {
      method: "POST",
      body: JSON.stringify({ ticker }),
    }),
  removeTicker: (id: string, ticker: string) =>
    apiFetch<Theme>(
      `/api/themes/${id}/tickers/${encodeURIComponent(ticker)}`,
      { method: "DELETE" },
    ),
};

// ── Filings (SEC EDGAR narrative section extracts) ────────────────────────────

export interface FilingSectionSummary {
  section_key: string;
  heading: string | null;
  char_count: number;
  extraction_method: string;
}

export interface FilingRecord {
  id: string;
  accession_number: string;
  ticker: string;
  form_type: string;
  filing_date: string;
  period_of_report: string | null;
  primary_document_url: string | null;
  sections: FilingSectionSummary[];
}

export interface FilingSectionText {
  section_key: string;
  heading: string | null;
  text: string;
  char_count: number;
  extraction_method: string;
  extracted_at: string;
}

export interface FilingIngestFormResult {
  accession_number: string | null;
  filing_date: string | null;
  sections_added: number;
  sections_skipped_existing: number;
  error: string | null;
}

export interface FilingIngestSummary {
  ticker: string;
  cik: string | null;
  filings_processed: number;
  sections_added: number;
  sections_skipped_existing: number;
  per_form: Record<string, FilingIngestFormResult>;
  errors: string[];
}

export const filings = {
  list: (ticker: string) =>
    apiFetch<FilingRecord[]>(`/api/filings/${encodeURIComponent(ticker)}`),
  getSection: (ticker: string, accession: string, sectionKey: string) =>
    apiFetch<FilingSectionText>(
      `/api/filings/${encodeURIComponent(ticker)}/${encodeURIComponent(accession)}/sections/${encodeURIComponent(sectionKey)}`
    ),
  ingestTicker: (ticker: string) =>
    apiFetch<FilingIngestSummary>(
      `/api/filings/ingest/${encodeURIComponent(ticker)}`,
      { method: "POST" }
    ),
  ingestBatch: (tickers: string[]) =>
    apiFetch<FilingIngestSummary[]>(`/api/filings/ingest/batch`, {
      method: "POST",
      body: JSON.stringify({ tickers }),
    }),
};

// ── Relationships + Counterparty Resolution (Phase B + C) ─────────────────────

export interface RelationshipRecord {
  id: string;
  accession_number: string;
  form_type: string;
  filing_date: string;
  section_key: string;
  counterparty_name: string;
  relationship_type: string;
  magnitude_pct: number | null;
  unnamed: boolean;
  verbatim_quote: string | null;
  confirmed_bilateral: boolean;
  resolved_to_cik: string | null;
  resolved_to_ticker: string | null;
  extracted_at: string;
}

export interface ResolutionCandidate {
  cik: string;
  ticker: string | null;
  canonical_name: string;
  score: number;
  source: string;
}

export interface UnresolvedCounterparty {
  counterparty_name: string;
  alias_normalized: string;
  occurrence_count: number;
  tickers: string[];
  candidates: ResolutionCandidate[];
}

export interface ManualAliasRequest {
  alias_name: string;
  canonical_cik: string;
  canonical_ticker: string | null;
  canonical_name: string;
  created_by?: string | null;
}

export interface ResolveSummary {
  ticker: string;
  rows_considered: number;
  already_resolved: number;
  resolved_via_alias: number;
  resolved_via_exact: number;
  resolved_via_fuzzy: number;
  unresolved_surfaced_to_queue: number;
  unnamed_skipped: number;
  relationships_updated: number;
  aliases_created: number;
}

export interface CompetitionResolveSummary {
  ticker: string;
  rows_considered: number;
  competitors_considered: number;
  already_resolved: number;
  resolved_via_alias: number;
  resolved_via_exact: number;
  resolved_via_fuzzy: number;
  unresolved: number;
  rows_updated: number;
  aliases_created: number;
  relationships_updated: number;
}

export interface CombinedResolveSummary {
  relationships: ResolveSummary;
  competition: CompetitionResolveSummary;
}

// ── Competition extraction (Phase A for competitive landscape) ─────────────────

export interface CompetitorChip {
  name: string;
  ticker: string | null;
  magnitude_pct: number | null;
  verbatim_quote: string | null;
  tracked: boolean;
}

export interface CompetitionArea {
  area_of_competition: string;
  competitors: CompetitorChip[];
}

export interface CompetitionSegment {
  segment_name: string;
  narrative: string;
  areas: CompetitionArea[];
}

export interface CompetitionFiling {
  accession_number: string;
  form_type: string;
  filing_date: string;
  sec_filing_url: string | null;
}

export interface CompetitionData {
  ticker: string;
  filing: CompetitionFiling | null;
  extracted_at: string | null;
  segments: CompetitionSegment[];
}

export interface CompetitionExtractionSummary {
  ticker: string;
  filing_id: string | null;
  segments_extracted: number;
  areas_extracted: number;
  competitors_extracted: number;
  skipped: boolean;
  errors: string[];
  resolver: CompetitionResolveSummary | null;
}

// ── Fan-out (bulk ingest + extract + resolve per theme or ticker) ─────────────

export type FanoutStatusLiteral = "running" | "completed" | "failed";
export type FanoutStage = "ingest" | "extract" | "extract_transcripts" | "resolve";

export type FanoutScope =
  | { kind: "theme"; theme_id: string }
  | { kind: "ticker"; ticker: string };

export interface FanoutError {
  ticker: string;
  stage: FanoutStage;
  message: string;
}

export interface FanoutStatus {
  fanout_id: string;
  status: FanoutStatusLiteral;
  scope: FanoutScope;
  total_tickers: number;
  completed_tickers: number;
  current_ticker: string | null;
  current_stage: FanoutStage | null;
  errors: FanoutError[];
  started_at: string;
  finished_at: string | null;
}

export type TranscriptExtractionSummary = {
  ticker: string;
  transcripts_considered: number;
  transcripts_extracted: number;
  transcripts_skipped_existing: number;
  relationships_added: number;
  relationships_dropped: number;
  per_transcript: Array<{
    year: number | null;
    quarter: number | null;
    date: string;
    relationships_added: number;
    relationships_dropped: number;
    skipped: string | null;
    error: string | null;
  }>;
  errors: string[];
};

export const relationships = {
  listForTicker: (ticker: string) =>
    apiFetch<RelationshipRecord[]>(
      `/api/filings/${encodeURIComponent(ticker)}/relationships`
    ),
  extractTicker: (ticker: string, force = false) =>
    apiFetch<unknown>(
      `/api/filings/extract-relationships/${encodeURIComponent(ticker)}${force ? "?force=true" : ""}`,
      { method: "POST" }
    ),
  resolveTicker: (ticker: string) =>
    apiFetch<CombinedResolveSummary>(
      `/api/relationships/resolve/${encodeURIComponent(ticker)}`,
      { method: "POST" }
    ),
  listUnresolved: (limit = 50) =>
    apiFetch<UnresolvedCounterparty[]>(
      `/api/relationships/unresolved?limit=${limit}`
    ),
  createAlias: (body: ManualAliasRequest) =>
    apiFetch<{ alias_id: string; relationships_updated: number }>(
      `/api/relationships/alias`,
      { method: "POST", body: JSON.stringify(body) }
    ),
  getGraph: (
    ticker: string,
    options: {
      direction?: "out" | "in" | "both";
      depth?: 1 | 2;
      themeId?: string;
    } = {}
  ) => {
    const direction = options.direction ?? "both";
    const params = new URLSearchParams({ direction });
    if (options.depth) params.set("depth", String(options.depth));
    if (options.themeId) params.set("theme_id", options.themeId);
    return apiFetch<SupplyChainGraph>(
      `/api/relationships/graph/${encodeURIComponent(ticker)}?${params.toString()}`
    );
  },
  reconcile: () =>
    apiFetch<{ pairs_reconciled: number; rows_flipped: number }>(
      `/api/relationships/reconcile`,
      { method: "POST" }
    ),
};

export const competition = {
  get: (ticker: string) =>
    apiFetch<CompetitionData>(
      `/api/competition/${encodeURIComponent(ticker)}`
    ),
  extract: (ticker: string, force = false) =>
    apiFetch<CompetitionExtractionSummary>(
      `/api/filings/extract-competition/${encodeURIComponent(ticker)}${force ? "?force=true" : ""}`,
      { method: "POST" }
    ),
};

export const transcripts = {
  extract: (ticker: string, force = false) =>
    apiFetch<TranscriptExtractionSummary>(
      `/api/transcripts/extract-relationships/${encodeURIComponent(ticker)}${force ? "?force=true" : ""}`,
      { method: "POST" }
    ),
};

export const fanouts = {
  startTheme: (themeId: string, force: boolean = false) =>
    apiFetch<FanoutStatus>(
      `/api/themes/${encodeURIComponent(themeId)}/relationships/fanout${force ? "?force=true" : ""}`,
      { method: "POST" }
    ),
  startTicker: (ticker: string, force: boolean = false) =>
    apiFetch<FanoutStatus>(
      `/api/tickers/${encodeURIComponent(ticker)}/relationships/fanout${force ? "?force=true" : ""}`,
      { method: "POST" }
    ),
  get: (fanoutId: string) =>
    apiFetch<FanoutStatus>(`/api/fanouts/${encodeURIComponent(fanoutId)}`),
};

// ── Supply-chain graph (Phase D) ─────────────────────────────────────────────

export interface SupplyChainGraphNode {
  id: string;
  ticker: string | null;
  cik: string | null;
  name: string;
  is_root: boolean;
  tracked: boolean;
  unnamed: boolean;
  hop: number;
  in_selected_theme: boolean;
}

export interface SupplyChainGraphEdge {
  from_id: string;
  to_id: string;
  relationship_type: string;
  direction: "out" | "in";
  magnitude_pct: number | null;
  unnamed: boolean;
  confirmed_bilateral: boolean;
  verbatim_quote: string | null;
  source_ticker: string;
  accession_number: string;
  filing_date: string;
  section_key: string;
  hop: number;
}

export interface SupplyChainEntry {
  from_id: string;
  to_id: string;
  direction: "out" | "in";
  magnitude_pct: number | null;
  confirmed_bilateral: boolean;
  verbatim_quote: string | null;
  source_ticker: string;
  accession_number: string;
  filing_date: string;
  section_key: string;
  unnamed: boolean;
  counterparty_name?: string;
  counterparty_ticker?: string | null;
  counterparty_cik?: string | null;
  counterparty_tracked?: boolean;
}

export interface SupplyChainGraph {
  root_ticker: string;
  nodes: SupplyChainGraphNode[];
  edges: SupplyChainGraphEdge[];
  summary: Record<
    string,
    {
      out_named: SupplyChainEntry[];
      out_unnamed: SupplyChainEntry[];
      in_named: SupplyChainEntry[];
    }
  >;
}

// ── Discovery endpoints ───────────────────────────────────────────────────────

export const discovery = {
  run: (
    themeId: string,
    opts?: { sort_by?: string; filter_surprise?: boolean; filter_researched?: boolean }
  ) => {
    const params = new URLSearchParams();
    if (opts?.sort_by) params.set("sort_by", opts.sort_by);
    if (opts?.filter_surprise) params.set("filter_surprise", "true");
    if (opts?.filter_researched) params.set("filter_researched", "true");
    return apiFetch<DiscoverResponse>(`/api/themes/${themeId}/discover?${params}`);
  },
};

// ── Pipeline types ────────────────────────────────────────────────────────────

export type PhaseStatus = "pending" | "in_progress" | "awaiting_approval" | "completed" | "watchlist" | "error";
export type ThesisStatus = "STRONG_BUY" | "BUY" | "WATCHLIST" | "PASS" | "BROKEN" | "PENDING";
export type AdvanceAction = "approve" | "flag" | "stop";

export interface RunSummary {
  id: string;
  ticker: string;
  theme_id: string | null;
  theme_name: string | null;
  phase: string;
  status: PhaseStatus;
  loop_count: number;
  conviction_score: number | null;
  thesis_status: ThesisStatus | null;
  gap_count: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface DataGap {
  gap_type: "hard_error" | "soft_gap";
  category: string;
  field: string | null;
  description: string;
  occurrences: number;
  frequency: number;
  example_tickers: string[];
}

export interface DataGapsResponse {
  total_runs_scanned: number;
  gaps: DataGap[];
}

// ── Phase-specific structured output (Quick Screen first) ─────────────────────

export interface QuickScreenDimension {
  name: string;
  score: number;
  max_score: number;
  rationale: string;
}

export interface QuickScreenStructured {
  overall_score: number;
  recommendation: "GO" | "WATCHLIST" | "PASS";
  dimensions: QuickScreenDimension[];
  thesis: string;
  key_risk: string;
}

// ── Thesis Construction structured output ─────────────────────────────────────

export interface ThesisPoint {
  title: string;
  evidence: string;
}

export type CatalystType =
  | "earnings"
  | "product"
  | "regulatory"
  | "m_and_a"
  | "macro"
  | "other";

export interface Catalyst {
  timeframe: string;
  description: string;
  type?: CatalystType | null;
  signposts?: string[];
  linked_pillar?: string | null; // "bull:N" or "bear:N"
}

export interface KillCriterion {
  condition: string;
  threshold: string;
  monitoring_source: string;
  kills_pillar?: string | null; // "bull:N" or "bear:N"
}

export interface FailureMode {
  mode: string;
  leading_indicator: string;
  probability: "Low" | "Medium" | "High";
}

export interface PreMortem {
  framing: string;
  failure_modes: FailureMode[];
}

export interface ThesisStructured {
  core_thesis: string;
  bull_case: ThesisPoint[];
  bear_case: ThesisPoint[];
  variant_perception: string;
  catalysts: Catalyst[];
  conviction_score: number;
  conviction_rationale: string;
  kill_criteria?: KillCriterion[];
  pre_mortem?: PreMortem | null;
}

// ── Risk Stress-Test structured output ───────────────────────────────────────

export interface RiskEntry {
  risk: string;
  category: string;
  probability: "Low" | "Medium" | "High";
  impact: string;
  mitigation: string;
}

export interface RiskStressTestStructured {
  risks: RiskEntry[];
  rr_ratio: number;
  rr_verdict: string;
  loop_required: boolean;
  loop_categories: string[];
  loop_reason: string;
}

// ── Position Monitor structured output ──────────────────────────────────────

export interface MonitoringItem {
  metric: string;
  cadence: string;
  threshold: string;
}

export interface PositionMonitorStructured {
  entry_price_low: string;
  entry_price_high: string;
  entry_rationale: string;
  position_size_pct: number;
  sizing_rationale: string;
  add_triggers: string[];
  stop_loss_level: string;
  stop_loss_rationale: string;
  invalidation_conditions: string[];
  monitoring: MonitoringItem[];
  exit_conditions: string[];
  time_horizon: string;
}

// ── Deep Dive structured output ─────────────────────────────────────────────

export interface DeepDiveFinding {
  finding: string;
  evidence: string;
}

export interface DeepDiveCategoryStructured {
  score: number;
  score_rationale: string;
  key_findings: DeepDiveFinding[];
  analysis: string;
  data_gaps: string[];
}

// ── Transcript analysis types ─────────────────────────────────────────────────

export interface TranscriptClaim {
  quote: string;
  speaker: string;
  type: "guidance" | "market_share" | "customer" | "timeline" | "margin" | "other";
  prompted: boolean;
}

export interface TranscriptTension {
  question_summary: string;
  tension_type: "deflected" | "reframed" | "evasive";
  significance: "high" | "medium" | "low";
  verbatim_excerpt: string;
}

export interface TranscriptValidation {
  claim: string;
  status: "validated" | "missed" | "unvalidated";
  delta: string;
  evidence: string;
}

export interface TranscriptTheme {
  theme: string;
  status: "consistent" | "evolved" | "drifted";
  evidence: string;
  risk_signal: boolean;
}

export interface TranscriptBOMEntry {
  category: string;
  pct_estimate: number | null;
  vendors: string[];
  confidence: "confirmed" | "inferred" | "speculative";
}

export interface TranscriptBOMItem {
  program: string;
  total_value: string;
  bom: TranscriptBOMEntry[];
}

export interface TranscriptAnalysis {
  pass1_claims: TranscriptClaim[] | string;
  pass2_tiers: { claims_with_tiers: unknown[]; hedging_patterns: string[] } | string;
  pass3_qa_tensions: TranscriptTension[] | string;
  pass4_validation: { validations: TranscriptValidation[] } | string;
  pass5_consistency: { themes: TranscriptTheme[] } | string;
  pass6_bom: { commitments: TranscriptBOMItem[] } | null | string;
}

// ── Curated financial data for dashboard charts ───────────────────────────────

export interface QuarterlyMetric {
  period: string;
  value: number;
  yoy_growth: number | null;
}

export interface EstimateMetric {
  period: string;
  estimate: number;
  actual: number | null;
}

export interface DailyPrice {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  sma_9: number | null;
  sma_20: number | null;
  sma_50: number | null;
  sma_100: number | null;
  sma_200: number | null;
  rsi: number | null;
}

export interface MacroDataPoint {
  date: string;
  value: number;
}

export interface MacroIndicators {
  fed_funds_rate: MacroDataPoint[];
  treasury_10y: MacroDataPoint[];
  treasury_2y: MacroDataPoint[];
  yield_curve_spread: MacroDataPoint[];
  cpi: MacroDataPoint[];
  unemployment: MacroDataPoint[];
  gdp_growth: MacroDataPoint[];
  m2_money_supply: MacroDataPoint[];
  nonfarm_payrolls: MacroDataPoint[];
}

export interface EdgarFact {
  value: number;
  unit: string;
  period_start?: string;
  period_end: string;
  fiscal_year: number | null;
  fiscal_period: string | null;
}

// Keyed by XBRL concept, e.g. "us-gaap:RevenueRemainingPerformanceObligation".
// Values are most-recent-first, up to 12 entries per concept (report endpoint cap).
export type EdgarFacts = Record<string, EdgarFact[]>;

export interface PiotroskiComponent {
  key: string;
  label: string;
  passed: boolean | null;
  detail: string;
}

export interface QuantFingerprint {
  piotroski: {
    score: number;
    components_evaluated: number;
    components: PiotroskiComponent[];
  };
  altman_z: {
    z: number | null;
    zone: "safe" | "grey" | "distress" | null;
    not_applicable_reason: string | null;
  };
  beneish_m: {
    m: number | null;
    zone: "unlikely" | "caution" | "flag" | null;
    ratios: Record<string, number | null>;
    inputs_missing: string[];
    not_applicable_reason: string | null;
  };
  accruals_ratio: number | null;
  fcf_conversion: number | null;
  sbc: { sbc_pct_revenue: number | null; share_growth_yoy_pct: number | null };
  margin_slopes: Record<
    "gross" | "operating" | "net",
    { slope_pp_per_quarter: number | null; quarters: number }
  >;
  meta: { quarters_available: number; basis: string; sector: string };
}

export interface CuratedFinancials {
  ticker: string;
  company_name: string;
  sector: string;
  industry: string;
  market_cap: number;
  current_price: number;
  quarterly_revenue: QuarterlyMetric[];
  quarterly_eps: QuarterlyMetric[];
  quarterly_gross_margin: QuarterlyMetric[];
  quarterly_operating_margin: QuarterlyMetric[];
  quarterly_net_margin: QuarterlyMetric[];
  quarterly_cash: QuarterlyMetric[];
  quarterly_total_debt: QuarterlyMetric[];
  quarterly_shareholders_equity: QuarterlyMetric[];
  quarterly_current_ratio: QuarterlyMetric[];
  debt_to_equity: number;
  quarterly_operating_cf: QuarterlyMetric[];
  quarterly_free_cf: QuarterlyMetric[];
  quarterly_capex: QuarterlyMetric[];
  dcf_intrinsic_value: number | null;
  dcf_gap_percent: number | null;
  forward_revenue_estimates: EstimateMetric[];
  forward_eps_estimates: EstimateMetric[];
  // Valuation ratios (from key-metrics-ttm)
  pe_ratio: number | null;
  ev_to_ebitda: number | null;
  price_to_book: number | null;
  price_to_fcf: number | null;
  price_to_sales: number | null;
  peg_ratio: number | null;
  // Return metrics
  roe: number | null;
  roic: number | null;
  roa: number | null;
  interest_coverage: number | null;
  dividend_yield: number | null;
  // Technical
  beta: number | null;
  fifty_two_week_high: number | null;
  fifty_two_week_low: number | null;
  volume_avg: number | null;
  daily_prices: DailyPrice[];
  macro_indicators: MacroIndicators | null;
  // Absent on runs persisted before the quant layer shipped.
  quant_fingerprint?: QuantFingerprint | null;
}

export interface CategoryOutput {
  score: number;
  content: string;
  key_findings: string[];
  citations: Citation[];
  // Quick Screen specifically may populate this; other phases leave it undefined.
  structured?: QuickScreenStructured | DeepDiveCategoryStructured;
  parse_error?: string | null;
  // error variant
  __type__?: "CategoryError";
  reason?: string;
}

export interface RunDetail extends RunSummary {
  phase_outputs: Record<string, CategoryOutput | { content: string; citations: Citation[] }>;
  scores: Record<string, number>;
  human_feedback: Record<string, string>;
  flags: string[];
  loop_context: Record<string, unknown> | null;
  citations: Citation[];
  failed_categories: string[];
}

export interface XSignalVelocity {
  ratio: number | null;
  count_7d: number | null;
  count_30d_approx: number | null;
  direction: "accelerating" | "stable" | "decelerating" | null;
  is_stale: boolean;
  computed_at: string | null;
}

export interface SignalHistoryPoint {
  computed_at: string;
  value: Record<string, unknown>;
}

export interface SignalHistoryResponse {
  theme_id: string;
  ticker: string;
  signal_type: "velocity" | "narrative" | "discovery";
  days: number;
  points: SignalHistoryPoint[];
}

export interface ReportResponse {
  run_id: string;
  ticker: string;
  theme_id: string | null;
  status: PhaseStatus;
  conviction_score: number;
  thesis_status: ThesisStatus;
  loop_count: number;
  x_signal_velocity?: XSignalVelocity | null;
  phases: {
    quick_screen: CategoryOutput;
    deep_dive: { categories: Record<string, CategoryOutput>; curated_financials: CuratedFinancials | null; transcript_analysis: TranscriptAnalysis | null; edgar_facts: EdgarFacts };
    thesis: CategoryOutput & { structured?: ThesisStructured };
    risk: CategoryOutput & { structured?: RiskStressTestStructured };
    position: { content: string; citations: Citation[]; structured?: PositionMonitorStructured; parse_error?: string | null };
  };
  scores: Record<string, number>;
  human_feedback: Record<string, string>;
  flags: string[];
  citations: Citation[];
  created_at: string | null;
  updated_at: string | null;
  obsidian: {
    ticker: string;
    theme_id: string | null;
    conviction_score: number;
    thesis_status: string;
    phase_reached: string;
    date_researched: string;
    loop_count: number;
  };
  kill_criterion_states?: KillCriterionStateOut[];
  questions?: Question[];
}

// ── SSE event types ────────────────────────────────────────────────────────────

export type SSEEvent =
  | { type: "phase_start"; phase: string; label: string }
  | { type: "deep_dive_start"; categories: string[]; loop_count: number; loop_context: unknown; curated_financials: CuratedFinancials | null; transcript_analysis: TranscriptAnalysis | null; edgar_facts: EdgarFacts }
  | { type: "category_complete"; category: string; score: number; key_findings: string[]; structured?: DeepDiveCategoryStructured | null }
  | { type: "category_error"; category: string; reason: string }
  | { type: "token"; text: string }
  | { type: "phase_complete"; phase: string; output: Record<string, unknown>; conviction_score: number }
  | { type: "interrupt"; phase: string; output: unknown; failed_categories: string[]; loop_count: number; loop_context: unknown; conviction_score: number }
  | { type: "complete"; status: string; conviction_score: number; thesis_status: string }
  | { type: "error"; phase: string; message: string }
  | { type: "heartbeat" };

// ── Pipeline endpoints ─────────────────────────────────────────────────────────

export const pipeline = {
  start: (ticker: string, theme_id: string) =>
    apiFetch<RunDetail>("/api/runs", {
      method: "POST",
      body: JSON.stringify({ ticker, theme_id }),
    }),

  get: (runId: string) => apiFetch<RunDetail>(`/api/runs/${runId}`),

  list: (opts?: { status?: string; theme_id?: string; ticker?: string; search?: string; limit?: number }) => {
    const params = new URLSearchParams();
    if (opts?.status)   params.set("status",   opts.status);
    if (opts?.theme_id) params.set("theme_id", opts.theme_id);
    if (opts?.ticker)   params.set("ticker",   opts.ticker);
    if (opts?.search)   params.set("search",   opts.search);
    if (opts?.limit)    params.set("limit",    String(opts.limit));
    return apiFetch<RunSummary[]>(`/api/runs?${params}`);
  },

  dataGaps: (opts?: { status?: string; theme_id?: string; ticker?: string }) => {
    const params = new URLSearchParams();
    if (opts?.status)   params.set("status",   opts.status);
    if (opts?.theme_id) params.set("theme_id", opts.theme_id);
    if (opts?.ticker)   params.set("ticker",   opts.ticker);
    return apiFetch<DataGapsResponse>(`/api/runs/data-gaps?${params}`);
  },

  advance: (runId: string, action: AdvanceAction, feedback?: string) =>
    apiFetch<RunDetail>(`/api/runs/${runId}/advance`, {
      method: "POST",
      body: JSON.stringify({ action, feedback }),
    }),

  report: (runId: string) => apiFetch<ReportResponse>(`/api/runs/${runId}/report`),

  streamUrl: (runId: string) =>
    `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/runs/${runId}/stream`,
};

// ── Formatting helpers ────────────────────────────────────────────────────────

export function fmtMarketCap(n: number | null): string {
  if (!n) return "—";
  if (n >= 1e12) return `$${(n / 1e12).toFixed(1)}T`;
  if (n >= 1e9)  return `$${(n / 1e9).toFixed(1)}B`;
  if (n >= 1e6)  return `$${(n / 1e6).toFixed(1)}M`;
  return `$${n.toFixed(0)}`;
}

export function fmtPct(n: number | null): string {
  if (n === null || n === undefined) return "—";
  return `${(n * 100).toFixed(1)}%`;
}

export function fmtScore(n: number): string {
  return n.toFixed(0);
}

// ── Catalysts (Tier 1.3) ──────────────────────────────────────────────────────

export type CatalystDateSource =
  | "fmp_earnings"
  | "parsed_quarter"
  | "parsed_relative"
  | "parsed_year"
  | "parsed_half"
  | "untimed";

export interface CatalystRow {
  id: string;
  run_id: string;
  ticker: string;
  ordinal: number;
  timeframe: string;
  description: string;
  type?: CatalystType | null;
  signposts: string[];
  linked_pillar?: string | null;
  expected_date: string | null;          // ISO date "YYYY-MM-DD"
  expected_window_start: string | null;
  expected_window_end: string | null;
  date_source: CatalystDateSource;
  created_at: string;                     // ISO datetime
}

export interface CatalystBuckets {
  this_week: CatalystRow[];
  next_30d: CatalystRow[];
  next_90d: CatalystRow[];
  later: CatalystRow[];
  untimed: CatalystRow[];
}

export interface CatalystListResponse {
  buckets: CatalystBuckets;
  total: number;
}

export async function getCatalysts(ticker?: string): Promise<CatalystListResponse> {
  const qs = ticker ? `?ticker=${encodeURIComponent(ticker)}` : "";
  return apiFetch<CatalystListResponse>(`/api/catalysts${qs}`);
}

export async function getCatalystsForRun(runId: string): Promise<CatalystListResponse> {
  return apiFetch<CatalystListResponse>(
    `/api/catalysts?run_id=${encodeURIComponent(runId)}`
  );
}

export async function getSignalHistory(
  themeId: string,
  ticker: string,
  opts: { signalType?: "velocity" | "narrative" | "discovery"; days?: number } = {},
): Promise<SignalHistoryResponse> {
  const params = new URLSearchParams();
  if (opts.signalType) params.set("signal_type", opts.signalType);
  if (opts.days != null) params.set("days", String(opts.days));
  const qs = params.toString();
  const path = `/api/themes/${encodeURIComponent(themeId)}/signals/${encodeURIComponent(ticker)}/history${qs ? `?${qs}` : ""}`;
  return apiFetch<SignalHistoryResponse>(path);
}

export async function getCatalyst(id: string): Promise<CatalystRow> {
  return apiFetch<CatalystRow>(`/api/catalysts/${encodeURIComponent(id)}`);
}

// ── Unified calendar (GET /api/catalysts/calendar) ──────────────────────────

export interface EconomicEventDetail {
  estimate: number | null;
  previous: number | null;
  actual: number | null;
  unit: string | null;
}

export interface EarningsEventDetail {
  eps_estimated: number | null;
  eps_actual: number | null;
  revenue_estimated: number | null;
  revenue_actual: number | null;
  has_thesis: boolean;
  run_id: string | null;
}

export interface CatalystEventDetail {
  run_id: string;
  catalyst_id: string;
  type: CatalystType | null;
  timeframe: string;
  linked_pillar: string | null;
  windowed: boolean;
  window_start: string | null;
  window_end: string | null;
}

interface CalendarEventBase {
  date: string;             // YYYY-MM-DD
  timestamp: string | null; // econ rows carry intraday UTC time
  title: string;
  citation: Citation | null;
}

export type CalendarEvent =
  | (CalendarEventBase & { kind: "economic"; ticker: null; detail: EconomicEventDetail })
  | (CalendarEventBase & { kind: "earnings"; ticker: string; detail: EarningsEventDetail })
  | (CalendarEventBase & { kind: "catalyst"; ticker: string; detail: CatalystEventDetail });

export type CalendarEventKind = CalendarEvent["kind"];

export interface CalendarResponse {
  events: CalendarEvent[];
  universe_size: number;
  warnings: string[];
}

export async function getCalendarEvents(
  start: string,
  end: string
): Promise<CalendarResponse> {
  return apiFetch<CalendarResponse>(
    `/api/catalysts/calendar?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`
  );
}

// ── Status board ─────────────────────────────────────────────────────────────

export type Health = "healthy" | "imminent" | "stale" | "triggered" | "broken";

export interface NextCatalyst {
  description: string;
  type: string | null;
  expected_date: string | null;
  expected_window_end: string | null;
  days_until: number | null;
}

export interface KillCriteriaSummary {
  total: number;
  triggered: number;
}

export interface MaterialEventsSummary {
  count_14d: number;
  max_materiality: "high" | "medium" | "low";
  latest_headline: string;
}

export interface StatusBoardEntry {
  ticker: string;
  theme_id: string;
  theme_name: string;
  run_id: string;
  thesis_status: string;
  conviction_score: number | null;
  completed_at: string;
  days_since_update: number;
  health: Health;
  health_reasons: string[];
  next_catalyst: NextCatalyst | null;
  kill_criteria_summary: KillCriteriaSummary;
  material_events: MaterialEventsSummary | null;
  archived_at: string | null;
}

export interface StatusBoardResponse {
  entries: StatusBoardEntry[];
  total: number;
  generated_at: string;
}

export interface KillCriterionStateOut {
  ordinal: number;
  status: "armed" | "triggered";
  flipped_at: string;
  note: string | null;
}

export interface RelationshipLink {
  relationship_type: string;
  direction: "outbound" | "inbound";
  verbatim_quote?: string | null;
  magnitude_pct?: number | null;
}

export interface ReadThroughItem {
  event_key: string;
  peer_ticker: string;
  event_type: "earnings" | "run_complete";
  event_date: string;
  payload: Record<string, unknown>;
  links: RelationshipLink[];
}

export type ReadThroughsByRun = Record<string, ReadThroughItem[]>;

export const status = {
  board: (opts?: { theme_id?: string; include_archived?: boolean }) => {
    const qs = new URLSearchParams();
    if (opts?.theme_id) qs.set("theme_id", opts.theme_id);
    if (opts?.include_archived) qs.set("include_archived", "true");
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return apiFetch<StatusBoardResponse>(`/api/status/board${suffix}`);
  },
  archive: (run_id: string) =>
    apiFetch<void>(`/api/runs/${encodeURIComponent(run_id)}/archive`, {
      method: "POST",
    }),
  unarchive: (run_id: string) =>
    apiFetch<void>(`/api/runs/${encodeURIComponent(run_id)}/unarchive`, {
      method: "POST",
    }),
};

export const killCriteria = {
  list: (run_id: string) =>
    apiFetch<KillCriterionStateOut[]>(
      `/api/runs/${encodeURIComponent(run_id)}/kill-criteria`,
    ),
  set: (
    run_id: string,
    ordinal: number,
    body: { status: "armed" | "triggered"; note?: string },
  ) =>
    apiFetch<KillCriterionStateOut>(
      `/api/runs/${encodeURIComponent(run_id)}/kill-criteria/${ordinal}`,
      {
        method: "PUT",
        body: JSON.stringify(body),
      },
    ),
};

export const readThroughs = {
  async list(params?: { since?: string; until?: string }): Promise<ReadThroughsByRun> {
    const qs = new URLSearchParams();
    if (params?.since) qs.set("since", params.since);
    if (params?.until) qs.set("until", params.until);
    const url = `/api/status/read-throughs${qs.toString() ? `?${qs}` : ""}`;
    return apiFetch<ReadThroughsByRun>(url);
  },

  async dismiss(run_id: string, event_key: string): Promise<void> {
    await apiFetch<void>("/api/status/read-throughs/dismiss", {
      method: "POST",
      body: JSON.stringify({ run_id, event_key }),
    });
  },

  async summarize(run_id: string, event_key: string): Promise<{ summary: string }> {
    return apiFetch<{ summary: string }>("/api/status/read-throughs/summary", {
      method: "POST",
      body: JSON.stringify({ run_id, event_key }),
    });
  },
};

// ── Material events (classified 8-Ks) ───────────────────────────────────────

export interface MaterialEvent {
  id: string;
  ticker: string;
  event_type: "guidance" | "personnel" | "ma" | "financing" | "other";
  materiality: "high" | "medium" | "low";
  headline: string;
  summary: string;
  item_codes: string | null;
  filing_date: string;
  document_url: string | null;
  dismissed_at: string | null;
}

export interface EventListResponse {
  events: MaterialEvent[];
  total: number;
}

export const events = {
  list: (params?: {
    since_days?: number;
    ticker?: string;
    materiality?: string;
    include_dismissed?: boolean;
  }) => {
    const qs = new URLSearchParams();
    if (params?.since_days) qs.set("since_days", String(params.since_days));
    if (params?.ticker) qs.set("ticker", params.ticker);
    if (params?.materiality) qs.set("materiality", params.materiality);
    if (params?.include_dismissed) qs.set("include_dismissed", "true");
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return apiFetch<EventListResponse>(`/api/events${suffix}`);
  },
  dismiss: (id: string) =>
    apiFetch<void>(`/api/events/${encodeURIComponent(id)}/dismiss`, {
      method: "POST",
    }),
};

// ── Earnings cycle navigator ────────────────────────────────────────────────

export type VerdictPhase = "pre" | "post" | "none";
export type Verdict = "confirms" | "threatens" | "neutral" | "insufficient";

export interface EarningsPrintRow {
  id: string;
  ticker: string;
  fiscal_year: number;
  fiscal_quarter: number;
  earnings_date: string; // YYYY-MM-DD
  eps_estimated: number | null;
  eps_actual: number | null;
  revenue_estimated: number | null;
  revenue_actual: number | null;
  eps_surprise_pct: number | null;
  revenue_surprise_pct: number | null;
  guidance_direction: "raised" | "maintained" | "lowered" | "n/a" | null;
}

export interface ThesisPrintVerdictRow {
  id: string;
  run_id: string;
  earnings_print_id: string;
  verdict: Verdict;
  summary_md: string;
  pillars_addressed: string[];
  generated_at: string; // ISO
}

export interface MatchedEarningsCatalyst {
  ordinal: number;
  signposts: string[];
  description: string;
}

export interface EarningsBoardEntry {
  run_id: string;
  ticker: string;
  theme_id: string;
  phase: VerdictPhase;
  print: EarningsPrintRow | null;
  matched_catalyst: MatchedEarningsCatalyst | null;
  verdict: ThesisPrintVerdictRow | null;
}

export interface EarningsBoardResponse {
  entries: EarningsBoardEntry[];
}

export interface BriefResponse {
  summary_md: string;
  pillars_addressed: string[];
  generated_at: string;
}

export const earnings = {
  board: async (windowDays: number = 14): Promise<EarningsBoardResponse> => {
    return apiFetch<EarningsBoardResponse>(`/api/earnings/board?window_days=${windowDays}`);
  },
  brief: async (runId: string, printId: string): Promise<BriefResponse> => {
    return apiFetch<BriefResponse>(
      `/api/runs/${encodeURIComponent(runId)}/earnings/${encodeURIComponent(printId)}/brief`,
      { method: "POST" }
    );
  },
  verdict: async (runId: string, printId: string): Promise<ThesisPrintVerdictRow> => {
    return apiFetch<ThesisPrintVerdictRow>(
      `/api/runs/${encodeURIComponent(runId)}/earnings/${encodeURIComponent(printId)}/verdict`,
      { method: "POST" }
    );
  },
  printsByTicker: async (ticker: string): Promise<EarningsPrintRow[]> => {
    return apiFetch<EarningsPrintRow[]>(`/api/earnings/prints/${encodeURIComponent(ticker)}`);
  },
  refresh: async (ticker: string): Promise<{ updated: number; ticker: string }> => {
    return apiFetch<{ updated: number; ticker: string }>(
      `/api/earnings/refresh/${encodeURIComponent(ticker)}`,
      { method: "POST" }
    );
  },
};

// ── Questions (Tier 1.2) ────────────────────────────────────────────────────

export type QuestionStatus =
  | "open"
  | "resolved_auto"
  | "resolved_inline"
  | "resolved_manual"
  | "dismissed";

export type QuestionAnswerSource =
  | "targeted_followup"
  | "deep_dive_resurfaced"
  | "manual"
  | null;

export interface Question {
  id: string;
  ticker: string;
  theme_id: string | null;
  category: string;
  question_text: string;
  priority: 1 | 2 | 3;
  auto_answerable: boolean;
  status: QuestionStatus;
  answer_text: string | null;
  answer_source: QuestionAnswerSource;
  created_run_id: string;
  resolved_run_id: string | null;
  created_at: string;
  resolved_at: string | null;
  dismissed_at: string | null;
  dismiss_note: string | null;
}

export interface QuestionTickerRollup {
  ticker: string;
  p1_count: number;
  p2_count: number;
  p3_count: number;
  open_count: number;
}

export const questions = {
  list: async (params: {
    ticker?: string;
    theme_id?: string;
    status?: QuestionStatusFilter;
    priority?: 1 | 2 | 3;
    category?: string;
    limit?: number;
  } = {}): Promise<{ questions: Question[] }> => {
    return apiFetch<{ questions: Question[] }>(buildQuestionListPath(params));
  },

  byTicker: async (params: { theme_id?: string } = {}): Promise<{ tickers: QuestionTickerRollup[] }> => {
    const qs = new URLSearchParams();
    if (params.theme_id) qs.set("theme_id", params.theme_id);
    const url = `/api/questions/by-ticker${qs.toString() ? `?${qs}` : ""}`;
    return apiFetch<{ tickers: QuestionTickerRollup[] }>(url);
  },

  dismiss: async (id: string, note?: string): Promise<Question> =>
    apiFetch<Question>(`/api/questions/${encodeURIComponent(id)}/dismiss`, {
      method: "POST",
      body: JSON.stringify({ note: note ?? null }),
    }),

  resolve: async (id: string, answer_text: string): Promise<Question> =>
    apiFetch<Question>(`/api/questions/${encodeURIComponent(id)}/resolve`, {
      method: "POST",
      body: JSON.stringify({ answer_text }),
    }),

  retryAuto: async (id: string): Promise<Question> =>
    apiFetch<Question>(`/api/questions/${encodeURIComponent(id)}/retry-auto`, {
      method: "POST",
    }),
};

// ============================================================================
// Model API — Tier 3.7 + 3.8 (editable financial model + reverse DCF)
// ============================================================================

export type CellSource = "historical" | "ai_baseline" | "driver" | "computed" | "override";

export interface ModelCell {
  value: number | null;
  source: CellSource;
  formula: string | null;
  citation_id: string | null;
  last_edited_at: string | null;
  last_edited_by: "system" | "ai_baseline" | "user" | null;
}

export interface Period {
  label: string;
  kind: "Q" | "Y";
  is_historical: boolean;
  quarter_index: number | null;
}

export interface ModelAssumptions {
  discount_rate: ModelCell;
  terminal_method: "exit_multiple" | "perpetuity";
  terminal_multiple: ModelCell;
  perpetuity_growth: ModelCell;
  tax_rate: ModelCell;
  plug_priority: Array<"debt_paydown" | "buyback" | "dividend" | "cash">;
}

export interface ModelState {
  periods: Period[];
  drivers: Record<string, Record<string, ModelCell>>;
  income_statement: Record<string, Record<string, ModelCell>>;
  balance_sheet: Record<string, Record<string, ModelCell>>;
  cash_flow: Record<string, Record<string, ModelCell>>;
  assumptions: ModelAssumptions;
}

export interface TickerModelVersion {
  id: string;
  ticker: string;
  version: number;
  label: string | null;
  state: ModelState;
  created_at: string;
}

export interface TickerModelDraft {
  base_version_id: string;
  state: ModelState;
  updated_at: string;
}

export interface SensitivityGrid {
  x_dim: string;
  y_dim: string;
  x_values: number[];
  y_values: number[];
  values: number[][];
}

export interface ReverseDcfResponse {
  price_used: number;
  price_source: "fmp_live" | "user_override";
  implied_drivers: { revenue_growth_pct: number | null; ebit_margin_pct: number | null; terminal_multiple: number | null };
  implied_irr: number | null;
  sensitivity_grids: {
    growth_margin: SensitivityGrid;
    growth_multiple: SensitivityGrid;
    margin_multiple: SensitivityGrid;
  };
  thesis_vs_priced_in: Array<{ dimension: string; thesis: number; priced_in: number | null; delta: number | null }>;
}

// Client functions (use the existing `apiFetch` helper from this file)
export async function getModel(ticker: string) {
  return apiFetch<{ latest_version: TickerModelVersion | null; draft: TickerModelDraft | null }>(`/api/models/${ticker}`);
}
export async function initializeModel(ticker: string, force = false) {
  return apiFetch<TickerModelVersion>(`/api/models/${ticker}/initialize?force=${force}`, { method: "POST" });
}
export async function putModelDraft(ticker: string, body: { cell_path: string; value: number | null; source?: string }) {
  return apiFetch<TickerModelDraft>(`/api/models/${ticker}/draft`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}
export async function saveModelVersion(ticker: string, label: string | null) {
  return apiFetch<{ id: string; version: number; label: string }>(`/api/models/${ticker}/save`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ label }),
  });
}
export async function discardModelDraft(ticker: string) {
  return apiFetch<{ ok: boolean }>(`/api/models/${ticker}/draft`, { method: "DELETE" });
}
export async function getReverseDcf(ticker: string, opts: { price?: number; from_draft?: boolean } = {}) {
  const qs = new URLSearchParams();
  if (opts.price !== undefined) qs.set("price", String(opts.price));
  if (opts.from_draft) qs.set("from_draft", "true");
  return apiFetch<ReverseDcfResponse>(`/api/models/${ticker}/reverse-dcf?${qs}`);
}
export async function getModelVersions(ticker: string) {
  return apiFetch<{ versions: Array<{ id: string; version: number; label: string | null; created_at: string }> }>(
    `/api/models/${ticker}/versions`
  );
}
export async function getModelDiff(ticker: string, version: number, against: number) {
  return apiFetch<{ added: string[]; removed: string[]; changed: Array<{ cell_path: string; before: { value: number | null; source: string } | null; after: { value: number | null; source: string } | null }> }>(
    `/api/models/${ticker}/versions/${version}/diff?against=${against}`
  );
}

// ----- Workspace -------------------------------------------------------

export type WorkspaceVerdict = "healthy" | "imminent" | "triggered" | "broken";
export type WorkspaceStep =
  | "update_refresh"
  | "research"
  | "validation"
  | "challenge"
  | "differentiation";

export interface ChangedCell {
  cell_path: string;
  prior_value: number | null;
  new_value: number | null;
  source: string;
  citation_id: string | null;
}

export interface UpdateRefreshOutput {
  version_before: number;
  version_after: number | null;
  changed_cells: ChangedCell[];
  removed_cells: string[];
  new_filings: { form: string; accession: string; fetched_at: string }[];
  consensus_delta: null | { metric: string; period: string; prior_consensus: number | null; new_consensus: number | null; delta_pct: number | null }[];
  summary: string;
}

export interface Highlight {
  text: string;
  classification: "confirms_thesis" | "threatens_thesis" | "new_unknown";
  citation_id: string | null;
}
export interface ResearchOutput {
  highlights: Highlight[];
  new_open_questions: { question: string; surfaced_by: string; classification: string }[];
  summary: string;
}

export interface ImpliedDriver {
  dimension: string;
  implied_value: number;
  baseline_value: number;
}
export interface WorkspaceSensitivityGrid {
  dim_x: string; dim_y: string;
  x_axis: number[]; y_axis: number[];
  values: number[][];
}
export interface ThesisVsPriced {
  metric: string; thesis_value: number; priced_in_value: number; delta_pct: number;
}
export interface ValidationOutput {
  implied_drivers: ImpliedDriver[];
  implied_irr: number | null;
  sensitivity_grids: WorkspaceSensitivityGrid[];
  thesis_vs_priced_in: ThesisVsPriced[];
  current_price: number;
  citation_ids: string[];
}

export interface KillCriterionWrite {
  ordinal: number;
  status: "armed" | "triggered";
  note: string | null;
}
export interface CatalystUpdate {
  catalyst_id: string;
  new_status: "still_pending" | "resolved" | "missed";
  note: string | null;
  description: string | null;
}
export interface ChallengeOutput {
  stress_test_summary: string;
  kill_criterion_writes: KillCriterionWrite[];
  catalyst_updates: CatalystUpdate[];
  proposed_verdict: WorkspaceVerdict;
}

export interface PeerCompRow {
  ticker: string;
  pe: number | null; ev_ebitda: number | null; p_b: number | null;
  p_fcf: number | null; p_s: number | null; peg: number | null;
  revenue_yoy: number | null; eps_yoy: number | null;
  gross_margin: number | null; operating_margin: number | null;
  ebitda_margin: number | null; fcf_margin: number | null;
  roe: number | null; roic: number | null; roa: number | null;
  market_cap: number | null;
}
export interface PeerCompTable {
  focus_ticker: string;
  rows: PeerCompRow[];
  median: PeerCompRow;
  delta_vs_median_pct: PeerCompRow;
}
export interface DifferentiationOutput {
  peer_comp: PeerCompTable | null;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  read_throughs: any[];
  per_peer_errors: { peer_ticker: string; error_message: string }[];
}

export interface PeerSetResponse {
  ticker: string;
  peers: string[];
  seeded: boolean;
}
export interface PeerCompResponse {
  table: PeerCompTable | null;
  errors: { peer_ticker: string; error_message: string }[];
}

export const peersApi = {
  get: (ticker: string) =>
    apiFetch<PeerSetResponse>(`/api/peers/${encodeURIComponent(ticker)}`),
  update: (ticker: string, peers: string[]) =>
    apiFetch<PeerSetResponse>(`/api/peers/${encodeURIComponent(ticker)}`, {
      method: "PUT",
      body: JSON.stringify({ peers }),
    }),
  comp: (ticker: string) =>
    apiFetch<PeerCompResponse>(`/api/peers/${encodeURIComponent(ticker)}/comp`),
  compare: (tickers: string[], focus?: string) =>
    apiFetch<PeerCompResponse>(
      `/api/peers/compare?tickers=${encodeURIComponent(tickers.join(","))}${
        focus ? `&focus=${encodeURIComponent(focus)}` : ""
      }`
    ),
};

export interface WorkspaceRun {
  id: string;
  ticker: string;
  parent_research_run_id: string | null;
  ticker_model_version_before: number;
  ticker_model_version_after: number | null;
  status: "running" | "completed" | "partial" | "failed";
  verdict: WorkspaceVerdict | null;
  step_outputs: {
    update_refresh?: UpdateRefreshOutput | { error: string };
    research?: ResearchOutput | { error: string };
    validation?: ValidationOutput | { error: string };
    challenge?: ChallengeOutput | { error: string };
    differentiation?: DifferentiationOutput | { error: string };
  };
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  citations: any[];
  error: string | null;
  created_at: string;
  updated_at: string;
}

export type WorkspaceSSE =
  | { type: "workspace_run_start"; run_id: string; ticker: string }
  | { type: "step_start"; step: WorkspaceStep }
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  | { type: "step_complete"; step: WorkspaceStep; output: any }
  | { type: "step_failed"; step: WorkspaceStep; error: string }
  | { type: "workspace_run_complete"; verdict: WorkspaceVerdict | null; version_after: number | null; status: "completed" | "partial" }
  | { type: "workspace_run_failed"; error: string };

export interface WorkspacePreflight {
  ok: boolean;
  missing: (
    | "no_completed_research_run"
    | "research_run_not_completed"
    | "research_run_ticker_mismatch"
    | "no_ticker_model"
    | "unsaved_model_draft"
    | "workspace_run_in_flight"
  )[];
  in_flight_run_id: string | null;
}

export const workspaceApi = {
  preflight: async (
    ticker: string,
    researchRunId?: string,
  ): Promise<WorkspacePreflight> => {
    const qs = researchRunId
      ? `?research_run_id=${encodeURIComponent(researchRunId)}`
      : "";
    const r = await fetch(
      `${BASE}/api/workspace/${encodeURIComponent(ticker)}/preflight${qs}`,
    );
    if (!r.ok) throw new Error(`preflight ${r.status}`);
    return r.json();
  },
  kickOff: async (
    ticker: string,
    researchRunId?: string,
  ): Promise<{ run_id: string }> => {
    const qs = researchRunId
      ? `?research_run_id=${encodeURIComponent(researchRunId)}`
      : "";
    const r = await fetch(
      `${BASE}/api/workspace/${encodeURIComponent(ticker)}/runs${qs}`,
      { method: "POST" },
    );
    if (!r.ok) throw new Error(`workspace kick-off failed: ${r.status} ${await r.text()}`);
    return r.json();
  },
  get: async (runId: string): Promise<WorkspaceRun> => {
    const r = await fetch(`${BASE}/api/workspace/runs/${runId}`);
    if (!r.ok) throw new Error(`workspace get failed: ${r.status}`);
    return r.json();
  },
  history: async (ticker: string): Promise<WorkspaceRun[]> => {
    const r = await fetch(`${BASE}/api/workspace/${encodeURIComponent(ticker)}/history`);
    if (!r.ok) throw new Error(`workspace history failed: ${r.status}`);
    return r.json();
  },
  recent: async (): Promise<WorkspaceRun[]> => {
    const r = await fetch(`${BASE}/api/workspace/recent`);
    if (!r.ok) throw new Error(`workspace recent failed: ${r.status}`);
    return r.json();
  },
  streamUrl: (runId: string) => `${BASE}/api/workspace/runs/${runId}/stream`,
};

// ============================================================================
// Outcome tracking
// ============================================================================

export type SnapshotOffset = "1d" | "1w" | "1m" | "3m" | "6m";
export type SourceType = "research_run" | "workspace_run";
export type Benchmark = "spy" | "sector" | "theme_basket";
export type Window = "30d" | "90d" | "1y" | "all";

export interface SnapshotRead {
  snapshot_offset: SnapshotOffset;
  snapshot_date: string;
  ticker_price: string;
  spy_price: string | null;
  sector_etf_price: string | null;
  theme_basket_value: string | null;
  ticker_return_pct: string;
  spy_excess_pct: string | null;
  sector_excess_pct: string | null;
  theme_basket_excess_pct: string | null;
}

export interface OutcomeListItem {
  id: string;
  source_type: SourceType;
  source_id: string;
  ticker: string;
  theme_id: string | null;
  verdict: string;
  verdict_emitted_at: string;
  entry_price_at: string;
  entry_price: string;
  sector_etf_ticker: string | null;
  superseded_at: string | null;
  closed_at: string | null;
  realized_ticker_return_pct: string | null;
  realized_spy_excess_pct: string | null;
  realized_sector_excess_pct: string | null;
  realized_theme_basket_excess_pct: string | null;
  snapshots: SnapshotRead[];
}

export interface OutcomeDetail extends OutcomeListItem {
  theme_basket_constituents: { ticker: string; entry_price: string }[] | null;
  signal_snapshot: Record<string, unknown> | null;
}

export interface StatGroup {
  n: number;
  mean_return_pct: number | null;
  mean_excess_pct: number | null;
  win_rate: number | null;
  median_excess_pct: number | null;
}

export interface ThemeStat {
  theme_id: string | null;
  theme_name: string | null;
  stats: StatGroup;
}

export interface SignalBucket {
  bucket: string;
  n: number;
  mean_excess_pct: number | null;
  win_rate: number | null;
}

export interface OutcomeSummary {
  window: Window;
  snapshot_offset: SnapshotOffset;
  benchmark: Benchmark;
  source_type: SourceType | "all";
  overall: StatGroup;
  by_verdict: Record<string, StatGroup | null>;
  by_theme: ThemeStat[];
  by_signal_bucket: Record<string, SignalBucket[]>;
}

export interface BackfillSummary {
  outcomes_created: number;
  outcomes_existed: number;
  snapshots_inserted: number;
  errors: { source_id?: string; outcome_id?: string; error: string }[];
}

export interface OutcomeSummaryQuery {
  themeId?: string;
  window?: Window;
  snapshotOffset?: SnapshotOffset;
  benchmark?: Benchmark;
  sourceType?: SourceType | "all";
}

export interface OutcomeListQuery {
  themeId?: string;
  verdict?: string;
  sourceType?: SourceType;
  superseded?: "true" | "false" | "all";
  closed?: "true" | "false" | "all";
  limit?: number;
  offset?: number;
}

export const outcomesApi = {
  async getSummary(q: OutcomeSummaryQuery = {}): Promise<OutcomeSummary> {
    const params = new URLSearchParams();
    if (q.themeId) params.set("theme_id", q.themeId);
    if (q.window) params.set("window", q.window);
    if (q.snapshotOffset) params.set("snapshot_offset", q.snapshotOffset);
    if (q.benchmark) params.set("benchmark", q.benchmark);
    if (q.sourceType) params.set("source_type", q.sourceType);
    return apiFetch(`/api/outcomes/summary?${params.toString()}`);
  },

  async list(q: OutcomeListQuery = {}): Promise<OutcomeListItem[]> {
    const params = new URLSearchParams();
    if (q.themeId) params.set("theme_id", q.themeId);
    if (q.verdict) params.set("verdict", q.verdict);
    if (q.sourceType) params.set("source_type", q.sourceType);
    if (q.superseded) params.set("superseded", q.superseded);
    if (q.closed) params.set("closed", q.closed);
    if (q.limit != null) params.set("limit", String(q.limit));
    if (q.offset != null) params.set("offset", String(q.offset));
    return apiFetch(`/api/outcomes?${params.toString()}`);
  },

  async getBySource(sourceType: SourceType, sourceId: string): Promise<OutcomeDetail> {
    return apiFetch(`/api/outcomes/by-source/${sourceType}/${sourceId}`);
  },

  async triggerBackfill(): Promise<BackfillSummary> {
    return apiFetch(`/api/outcomes/backfill`, { method: "POST" });
  },
};

// ── Trade journal ───────────────────────────────────────────────────────────

export type TradeDirection = "long" | "short";
export type ExitReason =
  | "thesis_played_out"
  | "kill_criterion"
  | "stop_loss"
  | "better_opportunity"
  | "rebalance"
  | "mistake"
  | "other";

export interface TradeReturnsRead {
  return_pct: string | null;
  spy_excess_pct: string | null;
  holding_days: number | null;
  unrealized: boolean;
}

export interface DecisionComparisonRead {
  offset: SnapshotOffset;
  trade_return_pct: string;
  trade_spy_excess_pct: string | null;
  paper_return_pct: string;
  paper_spy_excess_pct: string | null;
  execution_delta_pct: string | null;
}

export interface LinkedOutcomeSummary {
  id: string;
  verdict: string;
  source_type: SourceType;
  source_id: string;
  theme_id: string | null;
  verdict_emitted_at: string;
  entry_price_at: string;
  realized_spy_excess_pct: string | null;
}

export interface TradeDetail {
  id: string;
  ticker: string;
  direction: TradeDirection;
  status: "open" | "closed";
  entry_date: string;
  entry_price: string;
  entry_price_source: string;
  exit_date: string | null;
  exit_price: string | null;
  exit_price_source: string | null;
  quantity: string | null;
  spy_entry_price: string | null;
  spy_exit_price: string | null;
  outcome_id: string | null;
  entry_rationale: string | null;
  exit_reason: ExitReason | null;
  exit_note: string | null;
  returns: TradeReturnsRead | null;
  linked_outcome: LinkedOutcomeSummary | null;
  comparison: DecisionComparisonRead | null;
  created_at: string;
}

export interface TradeCreateBody {
  ticker: string;
  entry_date: string;
  entry_price?: string;
  quantity?: string;
  direction?: TradeDirection;
  outcome_id?: string;
  entry_rationale?: string;
}

export interface TradeUpdateBody {
  entry_date?: string;
  entry_price?: string;
  quantity?: string | null;
  direction?: TradeDirection;
  outcome_id?: string | null;
  entry_rationale?: string | null;
  exit_date?: string | null;
  exit_price?: string;
  exit_reason?: ExitReason;
  exit_note?: string;
}

export interface ExitReasonStat {
  exit_reason: string;
  count: number;
  avg_return_pct: string | null;
  avg_spy_excess_pct: string | null;
}

export interface JournalSummary {
  trade_count: number;
  open_count: number;
  closed_count: number;
  hit_rate: number | null;
  excess_basis_count: number;
  avg_return_pct: string | null;
  median_return_pct: string | null;
  avg_spy_excess_pct: string | null;
  avg_holding_days: number | null;
  execution_vs_paper: { n: number; avg_delta_pct: string | null };
  by_exit_reason: ExitReasonStat[];
  coverage: { outcomes_traded: number; outcomes_total: number };
}

export interface PricePreview {
  price: string;
  price_date: string;
  source: string;
}

export interface LinkCandidate {
  id: string;
  verdict: string;
  source_type: SourceType;
  theme_id: string | null;
  verdict_emitted_at: string;
  entry_price_at: string;
}

export const journalApi = {
  async list(q: { status?: "open" | "closed" | "all"; ticker?: string } = {}): Promise<TradeDetail[]> {
    const params = new URLSearchParams();
    if (q.status) params.set("status", q.status);
    if (q.ticker) params.set("ticker", q.ticker);
    return apiFetch(`/api/journal/trades?${params.toString()}`);
  },

  async create(body: TradeCreateBody): Promise<TradeDetail> {
    return apiFetch(`/api/journal/trades`, {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  async update(id: string, body: TradeUpdateBody): Promise<TradeDetail> {
    return apiFetch(`/api/journal/trades/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    });
  },

  async remove(id: string): Promise<void> {
    return apiFetch(`/api/journal/trades/${id}`, { method: "DELETE" });
  },

  async getSummary(): Promise<JournalSummary> {
    return apiFetch(`/api/journal/summary`);
  },

  async pricePreview(ticker: string, date: string): Promise<PricePreview> {
    return apiFetch(`/api/journal/price-preview?ticker=${encodeURIComponent(ticker)}&date=${date}`);
  },

  async linkCandidates(ticker: string): Promise<LinkCandidate[]> {
    return apiFetch(`/api/journal/link-candidates?ticker=${encodeURIComponent(ticker)}`);
  },
};

// ── Transcript delta ────────────────────────────────────────────────────────

export type TranscriptAxisDirection = "softening" | "strengthening" | "stable";
export type TranscriptAxisMagnitude = "minor" | "material" | "regime_change";

export interface TranscriptQuoteRef {
  year: number;
  quarter: number;
  role: string;
  text: string;
}

export interface TranscriptAxisDelta {
  direction: TranscriptAxisDirection;
  magnitude: TranscriptAxisMagnitude;
  summary: string;
  quotes: TranscriptQuoteRef[];
}

export interface TranscriptAxesDelta {
  business_quality: TranscriptAxisDelta | null;
  risk_assessment: TranscriptAxisDelta | null;
  growth_earnings: TranscriptAxisDelta | null;
  sentiment_narrative: TranscriptAxisDelta | null;
  management_governance: TranscriptAxisDelta | null;
  future_durability: TranscriptAxisDelta | null;
  macro_regime: TranscriptAxisDelta | null;
  financial_health: TranscriptAxisDelta | null;
  valuation_stage: TranscriptAxisDelta | null;
}

export interface TranscriptDeltaRead {
  id: string;
  ticker: string;
  transcripts_window: { year: number; quarter: number }[];
  axes: TranscriptAxesDelta;
  computed_at: string;
}

export const transcriptDeltaApi = {
  async getLatest(ticker: string): Promise<TranscriptDeltaRead | null> {
    const r = await fetch(`${BASE}/api/transcripts/delta/${encodeURIComponent(ticker)}/latest`);
    if (r.status === 204) return null;
    if (!r.ok) throw new Error(`getLatest ${ticker}: ${r.status}`);
    return r.json();
  },
  async getHistory(ticker: string): Promise<TranscriptDeltaRead[]> {
    return apiFetch(`/api/transcripts/delta/${encodeURIComponent(ticker)}/history`);
  },
  async compute(ticker: string, opts: { force?: boolean } = {}): Promise<TranscriptDeltaRead> {
    const qs = opts.force ? "?force=true" : "";
    const r = await fetch(
      `${BASE}/api/transcripts/delta/${encodeURIComponent(ticker)}${qs}`,
      { method: "POST" },
    );
    if (r.status === 404) throw new Error(`No transcripts available for ${ticker}`);
    if (!r.ok) throw new Error(`compute ${ticker}: ${r.status}`);
    return r.json();
  },
};

// ============================================================================
// Prospectus reports
// ============================================================================

export type IPOVerdict = "participate" | "watch_post_lockup" | "pass";
export type ProspectusStatus = "ingesting" | "analyzing" | "completed" | "failed";

export interface ExtractedSectionSummary {
  section_key: string;
  heading: string;
  char_count: number;
}

export interface AnnualFinancialRow {
  period_label: string;
  revenue: number | null;
  cost_of_revenue: number | null;
  operating_income: number | null;
  net_income: number | null;
  cash_and_equivalents: number | null;
  total_debt: number | null;
  source_snippet: string;
}

export interface InterimFinancialRow {
  period_label: string;
  revenue: number | null;
  operating_income: number | null;
  net_income: number | null;
  source_snippet: string;
}

export interface ProspectusFinancials {
  annual: AnnualFinancialRow[];
  interim: InterimFinancialRow[];
}

export interface IngestStepOutput {
  accession_number: string;
  primary_document_url: string;
  issuer_cik: string;
  issuer_name: string;
  proposed_ticker: string | null;
  form_type: string;
  sections: ExtractedSectionSummary[];
  financials: ProspectusFinancials;
}

export interface RelationshipSummary {
  counterparty_name: string;
  relationship_type: string;
  magnitude_pct: number | null;
  resolved_to_ticker: string | null;
  verbatim_quote: string;
}

export interface RelationshipsStepOutput {
  edges_extracted: number;
  edges_resolved: number;
  edges: RelationshipSummary[];
}

export interface ProspectusCategoryResult {
  category: string;
  content: string;
  score: number;
  key_findings: string[];
}

export interface CategoriesStepOutput {
  results: Record<string, ProspectusCategoryResult>;
  failures: Record<string, string>;
}

export interface KeyRisk {
  risk: string;
  severity: "low" | "medium" | "high";
  category_source: string;
}

export interface PostIPOPlanItem {
  question: string;
  why_it_matters: string;
  expected_data_source: string;
}

export interface ProspectusThesisOutput {
  thesis_statement: string;
  key_risks: KeyRisk[];
  ipo_verdict: IPOVerdict;
  price_range_commentary: string | null;
  post_ipo_research_plan: PostIPOPlanItem[];
}

export interface ProspectusReport {
  id: string;
  accession_number: string;
  issuer_cik: string;
  issuer_name: string;
  proposed_ticker: string | null;
  synthetic_ticker: string;
  theme_id: string | null;
  status: ProspectusStatus;
  step_outputs: {
    ingest?: IngestStepOutput;
    relationships?: RelationshipsStepOutput;
    categories?: CategoriesStepOutput;
    thesis?: ProspectusThesisOutput;
  };
  error_message: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export const prospectusApi = {
  create: async (
    body: { url_or_accession: string; theme_id?: string | null },
  ): Promise<{ report_id: string }> => {
    const r = await fetch(`${BASE}/api/prospectus`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error(`prospectus create failed: ${r.status} ${await r.text()}`);
    return r.json();
  },
  get: async (reportId: string): Promise<ProspectusReport> => {
    const r = await fetch(`${BASE}/api/prospectus/${reportId}`);
    if (!r.ok) throw new Error(`prospectus get failed: ${r.status}`);
    return r.json();
  },
  list: async (limit = 50): Promise<ProspectusReport[]> => {
    const r = await fetch(`${BASE}/api/prospectus?limit=${limit}`);
    if (!r.ok) throw new Error(`prospectus list failed: ${r.status}`);
    return r.json();
  },
  remove: async (reportId: string): Promise<void> => {
    const r = await fetch(`${BASE}/api/prospectus/${reportId}`, { method: "DELETE" });
    if (!r.ok && r.status !== 204) throw new Error(`prospectus delete failed: ${r.status}`);
  },
  streamUrl: (reportId: string) => `${BASE}/api/prospectus/${reportId}/stream`,
};

// ── Company workspace ─────────────────────────────────────────────────────────

export interface CompanyHeader {
  ticker: string;
  name: string | null;
  exchange: string | null;
  logo_url: string | null;
  currency: string | null;
  price: number | null;
  change: number | null;
  change_pct: number | null;
  delay_label: string;
}

export async function getCompanyHeader(ticker: string): Promise<CompanyHeader> {
  return apiFetch<CompanyHeader>(`/api/company/${encodeURIComponent(ticker)}/header`);
}

export interface StatItem {
  label: string;
  value: number | null;
  unit: "pct" | "x" | "money" | "num" | "int";
}

export interface OverviewStatGroup {
  title: string;
  items: StatItem[];
}

export interface PricePoint {
  date: string;
  close: number;
}

export interface CompanyOverview {
  ticker: string;
  sector: string | null;
  industry: string | null;
  stats: OverviewStatGroup[];
  prices: PricePoint[];
}

export async function getCompanyOverview(ticker: string): Promise<CompanyOverview> {
  return apiFetch<CompanyOverview>(`/api/company/${encodeURIComponent(ticker)}/overview`);
}

export interface CompanyFinancials {
  ticker: string;
  period: "annual" | "quarter";
  periods: string[];
  income: Record<string, (number | null)[]>;
  balance: Record<string, (number | null)[]>;
  cashflow: Record<string, (number | null)[]>;
}

export async function getCompanyFinancials(
  ticker: string,
  period: "annual" | "quarter",
): Promise<CompanyFinancials> {
  return apiFetch<CompanyFinancials>(
    `/api/company/${encodeURIComponent(ticker)}/financials?period=${period}`,
  );
}

export interface TranscriptEvent {
  quarter: number;
  fiscal_year: number;
  date: string;
}

export interface TranscriptList {
  ticker: string;
  events: TranscriptEvent[];
}

export interface TranscriptSegment {
  speaker: string;
  text: string;
}

export interface Transcript {
  ticker: string;
  year: number;
  quarter: number;
  date: string | null;
  segments: TranscriptSegment[];
}

export async function getTranscripts(ticker: string): Promise<TranscriptList> {
  return apiFetch<TranscriptList>(`/api/company/${encodeURIComponent(ticker)}/transcripts`);
}

export async function getTranscript(ticker: string, year: number, quarter: number): Promise<Transcript> {
  return apiFetch<Transcript>(
    `/api/company/${encodeURIComponent(ticker)}/transcripts/${year}/${quarter}`,
  );
}

export async function summarizeTranscript(ticker: string, year: number, quarter: number): Promise<{ summary_md: string }> {
  return apiFetch<{ summary_md: string }>(
    `/api/company/${encodeURIComponent(ticker)}/transcripts/${year}/${quarter}/summary`,
    { method: "POST" },
  );
}

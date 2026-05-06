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
  getGraph: (ticker: string, direction: "out" | "in" | "both" = "both") =>
    apiFetch<SupplyChainGraph>(
      `/api/relationships/graph/${encodeURIComponent(ticker)}?direction=${direction}`
    ),
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
  theme_id: string;
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

export interface ReportResponse {
  run_id: string;
  ticker: string;
  theme_id: string;
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
    theme_id: string;
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

  list: (opts?: { status?: string; theme_id?: string; search?: string; limit?: number }) => {
    const params = new URLSearchParams();
    if (opts?.status)   params.set("status",   opts.status);
    if (opts?.theme_id) params.set("theme_id", opts.theme_id);
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

export async function getCatalyst(id: string): Promise<CatalystRow> {
  return apiFetch<CatalystRow>(`/api/catalysts/${encodeURIComponent(id)}`);
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

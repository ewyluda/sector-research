import { apiFetch, BASE } from "./core";
import type { Citation } from "./core";
import type { Question } from "./status";

// ── Pipeline types ────────────────────────────────────────────────────────────

export type PhaseStatus =
  | "pending"
  | "in_progress"
  | "paused"
  | "awaiting_approval"
  | "completed"
  | "watchlist"
  | "pass"
  | "abandoned"
  | "error";
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

export interface KillCriterionStateOut {
  ordinal: number;
  status: "armed" | "triggered";
  flipped_at: string;
  note: string | null;
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

  abandon: (runId: string) =>
    apiFetch<{ run_id: string; status: "abandoned" }>(`/api/runs/${runId}/abandon`, {
      method: "POST",
    }),

  report: (runId: string) => apiFetch<ReportResponse>(`/api/runs/${runId}/report`),

  streamUrl: (runId: string) =>
    `${BASE}/api/runs/${runId}/stream`,
};


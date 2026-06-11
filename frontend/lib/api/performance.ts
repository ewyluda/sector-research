import { apiFetch } from "./core";

// ── Outcome tracking ──────────────────────────────────────────────────────────

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
  populated_offsets: SnapshotOffset[];
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

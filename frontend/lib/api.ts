/**
 * API client — thin typed wrapper over the FastAPI backend.
 * All fetches go through here. SSE streaming handled separately.
 */

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
  phase: string;
  status: PhaseStatus;
  loop_count: number;
  conviction_score: number | null;
  thesis_status: ThesisStatus | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface CategoryOutput {
  score: number;
  content: string;
  key_findings: string[];
  citations: Citation[];
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

export interface ReportResponse {
  run_id: string;
  ticker: string;
  theme_id: string;
  status: PhaseStatus;
  conviction_score: number;
  thesis_status: ThesisStatus;
  loop_count: number;
  phases: {
    quick_screen: CategoryOutput;
    deep_dive: Record<string, CategoryOutput>;
    thesis: { content: string; citations: Citation[] };
    risk: { content: string; citations: Citation[] };
    position: { content: string; citations: Citation[] };
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
}

// ── SSE event types ────────────────────────────────────────────────────────────

export type SSEEvent =
  | { type: "phase_start"; phase: string; label: string }
  | { type: "deep_dive_start"; categories: string[]; loop_count: number; loop_context: unknown }
  | { type: "category_complete"; category: string; score: number; key_findings: string[] }
  | { type: "category_error"; category: string; reason: string }
  | { type: "token"; text: string }
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

  list: (opts?: { status?: string; theme_id?: string; limit?: number }) => {
    const params = new URLSearchParams();
    if (opts?.status)   params.set("status",   opts.status);
    if (opts?.theme_id) params.set("theme_id", opts.theme_id);
    if (opts?.limit)    params.set("limit",    String(opts.limit));
    return apiFetch<RunSummary[]>(`/api/runs?${params}`);
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

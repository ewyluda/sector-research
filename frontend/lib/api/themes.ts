import { apiFetch } from "./core";
import type { Citation } from "./core";
import type { SignalHistoryResponse } from "./pipeline";

// ── Types ─────────────────────────────────────────────────────────────────────

export interface Theme {
  id: string;
  name: string;
  description: string | null;
  parent_theme_id: string | null;
  /**
   * Mirrors the `themes.seed_tickers` JSONB column, typed as the normalized
   * shape. Every write path runs through `_normalize_tickers` (api/themes.py:
   * uppercase, deduped list-of-strings, tolerating the legacy list-of-dicts
   * shape with a `"ticker"` key), but the read path serves the row as-is
   * (`ThemeResponse.seed_tickers: list | dict`) — so a legacy row that was
   * never rewritten can still surface dict entries here. Treat entries
   * defensively if you iterate; any PUT/ticker mutation re-normalizes the row.
   */
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

export interface CongressSnapshot {
  modifier: number;
  buy_count: number;
  sell_count: number;
  cluster_buy: boolean;
  net_value: number | null;
  is_stale: boolean;
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
  congress: CongressSnapshot;
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
  /**
   * Manually trigger an X-signal refresh for one theme. Synchronous on the
   * backend — blocks until every ticker finishes (2s sleep between X API
   * calls), so this can take a while. Per-ticker X failures degrade to the
   * `errors` count (HTTP 200), so callers must inspect the summary.
   */
  refreshSignals: (id: string) =>
    apiFetch<{ theme: string; processed: number; errors: number; surprises_fired: number }>(
      `/api/themes/${id}/signals/refresh`,
      { method: "POST" },
    ),
};

// ── Tickers ───────────────────────────────────────────────────────────────────

export interface TickerEntry {
  ticker: string;
}

/** Distinct known tickers (theme seeds ∪ researched) — feeds the ⌘K palette. */
export const getTickers = () => apiFetch<TickerEntry[]>("/api/tickers");

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

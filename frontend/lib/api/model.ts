import { apiFetch } from "./core";

// ── Model API — Tier 3.7 + 3.8 (editable financial model + reverse DCF) ──────

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

import { apiFetch, BASE } from "./core";
import type { Citation } from "./core";
import type { ReadThroughItem } from "./status";

// ── Workspace types ───────────────────────────────────────────────────────────

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
  model_skipped?: boolean;
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
  read_throughs: ReadThroughItem[];
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

export type WorkspaceStepOutput =
  | UpdateRefreshOutput
  | ResearchOutput
  | ValidationOutput
  | ChallengeOutput
  | DifferentiationOutput;

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
  citations: Citation[];
  error: string | null;
  created_at: string;
  updated_at: string;
}

export type WorkspaceSSE =
  | { type: "workspace_run_start"; run_id: string; ticker: string }
  | { type: "step_start"; step: WorkspaceStep }
  | { type: "step_complete"; step: WorkspaceStep; output: WorkspaceStepOutput }
  | { type: "step_failed"; step: WorkspaceStep; error: string }
  | { type: "workspace_run_complete"; verdict: WorkspaceVerdict | null; version_after: number | null; status: "completed" | "partial" }
  | { type: "workspace_run_failed"; error: string };

export interface WorkspacePreflight {
  ok: boolean;
  missing: (
    | "no_completed_research_run"
    | "research_run_not_completed"
    | "research_run_ticker_mismatch"
    | "unsaved_model_draft"
    | "workspace_run_in_flight"
  )[];
  warnings: ("no_ticker_model")[];
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

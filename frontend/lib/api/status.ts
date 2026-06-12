import { apiFetch } from "./core";
import type { KillCriterionStateOut } from "./pipeline";
import { buildQuestionListPath, type QuestionStatusFilter } from "../questions-ui";

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
  // Near-duplicate grouping: same (ticker, event_type) within 4 days collapse
  // into one list item; the primary's fields stay top-level.
  group_count: number;
  group_member_ids: string[];
  group_headlines: string[];
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

export type VerdictPhase = "pre" | "post" | "post_pending" | "none";
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
  snoozed_until: string | null;
}

export interface QuestionBulkFilter {
  ticker?: string;
  theme_id?: string;
  priority?: 1 | 2 | 3;
  category?: string;
  status?: QuestionStatus;
}

export interface QuestionBulkBody {
  ids?: string[];
  filter?: QuestionBulkFilter;
  action: "dismiss" | "resolve" | "snooze";
  note?: string;
  answer_text?: string;
  snooze_days?: number;
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

  bulk: async (body: QuestionBulkBody): Promise<{ affected: number }> =>
    apiFetch<{ affected: number }>(`/api/questions/bulk`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  unsnooze: async (id: string): Promise<Question> =>
    apiFetch<Question>(`/api/questions/${encodeURIComponent(id)}/unsnooze`, {
      method: "POST",
    }),
};

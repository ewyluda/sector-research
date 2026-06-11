import { apiFetch } from "./core";
import type { Citation } from "./core";
import type { CatalystType, SignalHistoryResponse } from "./pipeline";

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

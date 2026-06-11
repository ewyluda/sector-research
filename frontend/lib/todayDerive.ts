/**
 * Pure derivation for the Today dashboard: buckets status-board entries and
 * the open-question rollup into attention rows + banner summary counts.
 * Kept free of React/fetch so it's unit-testable via node --test.
 */

import type { Health, MaterialEvent, QuestionTickerRollup, StatusBoardEntry } from "./api";

export interface HealthAttentionRow {
  kind: "health";
  severity: "red" | "amber";
  ticker: string;
  themeName: string;
  runId: string;
  health: Health;
  reasons: string[];
  triggeredCriteria: number;
  totalCriteria: number;
  daysSinceUpdate: number;
}

export interface QuestionsAttentionRow {
  kind: "questions";
  severity: "blue";
  ticker: string;
  p1Count: number;
  openCount: number;
}

export interface EventAttentionRow {
  kind: "event";
  severity: "amber";
  materiality: MaterialEvent["materiality"];
  ticker: string;
  headline: string;
  eventType: string;
  filingDate: string;
  eventId: string;
}

export type AttentionRow = HealthAttentionRow | QuestionsAttentionRow | EventAttentionRow;

export interface TodaySummary {
  alerts: number;     // broken + triggered theses
  stale: number;      // stale theses
  p1Tickers: number;  // tickers with ≥1 open P1 question
}

const HEALTH_BUCKET: Partial<Record<Health, number>> = {
  broken: 0,
  triggered: 1,
  stale: 2,
};

export function deriveAttention(
  entries: StatusBoardEntry[],
  rollup: QuestionTickerRollup[],
  events: MaterialEvent[] = [],
): AttentionRow[] {
  const healthRows = entries
    .filter((e) => e.health in HEALTH_BUCKET)
    .sort((a, b) => {
      const aBucket = HEALTH_BUCKET[a.health] ?? 99;
      const bBucket = HEALTH_BUCKET[b.health] ?? 99;
      const byBucket = aBucket - bBucket;
      return byBucket !== 0 ? byBucket : b.days_since_update - a.days_since_update;
    })
    .map(
      (e): HealthAttentionRow => ({
        kind: "health",
        severity: e.health === "stale" ? "amber" : "red",
        ticker: e.ticker,
        themeName: e.theme_name,
        runId: e.run_id,
        health: e.health,
        reasons: e.health_reasons,
        triggeredCriteria: e.kill_criteria_summary.triggered,
        totalCriteria: e.kill_criteria_summary.total,
        daysSinceUpdate: e.days_since_update,
      }),
    );

  const questionRows = rollup
    .filter((r) => r.p1_count > 0)
    .sort((a, b) => b.p1_count - a.p1_count)
    .map(
      (r): QuestionsAttentionRow => ({
        kind: "questions",
        severity: "blue",
        ticker: r.ticker,
        p1Count: r.p1_count,
        openCount: r.open_count,
      }),
    );

  const eventRows = [...events]
    .sort((a, b) => b.filing_date.localeCompare(a.filing_date))
    .map(
      (ev): EventAttentionRow => ({
        kind: "event",
        severity: "amber",
        materiality: ev.materiality,
        ticker: ev.ticker,
        headline: ev.headline,
        eventType: ev.event_type,
        filingDate: ev.filing_date,
        eventId: ev.id,
      }),
    );

  // Severity tiers span item types: broken/triggered theses rank with
  // high-materiality events; stale theses with medium/low events; question
  // rollups last. The sort is stable, so within a tier the per-type ordering
  // above (health → events → questions, each internally sorted) is preserved.
  return [...healthRows, ...eventRows, ...questionRows].sort(
    (a, b) => attentionTier(a) - attentionTier(b),
  );
}

function attentionTier(row: AttentionRow): number {
  switch (row.kind) {
    case "health":
      return row.severity === "red" ? 0 : 1;
    case "event":
      return row.materiality === "high" ? 0 : 1;
    case "questions":
      return 2;
  }
}

export function deriveSummary(
  entries: StatusBoardEntry[],
  rollup: QuestionTickerRollup[],
): TodaySummary {
  return {
    alerts: entries.filter((e) => e.health === "broken" || e.health === "triggered").length,
    stale: entries.filter((e) => e.health === "stale").length,
    p1Tickers: rollup.filter((r) => r.p1_count > 0).length,
  };
}

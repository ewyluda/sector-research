export type QuestionsTab = "by_ticker" | "by_question";
export type QuestionStatusFilter =
  | "open"
  | "resolved_auto"
  | "resolved_inline"
  | "resolved_manual"
  | "dismissed"
  | "all";

export interface QuestionListPathParams {
  ticker?: string;
  theme_id?: string;
  status?: QuestionStatusFilter;
  priority?: 1 | 2 | 3;
  category?: string;
  limit?: number;
}

export function initialQuestionsTab(tickerFilter?: string | null): QuestionsTab {
  return tickerFilter ? "by_question" : "by_ticker";
}

export function syncQuestionsTabForTickerFilter(
  currentTab: QuestionsTab,
  tickerFilter?: string | null,
): QuestionsTab {
  return tickerFilter ? "by_question" : currentTab;
}

export function buildQuestionListPath(params: QuestionListPathParams = {}): string {
  const qs = new URLSearchParams();
  if (params.ticker) qs.set("ticker", params.ticker);
  if (params.theme_id) qs.set("theme_id", params.theme_id);
  if (params.status) qs.set("status", params.status);
  if (params.priority !== undefined) qs.set("priority", String(params.priority));
  if (params.category) qs.set("category", params.category);
  if (params.limit !== undefined) qs.set("limit", String(params.limit));
  return `/api/questions${qs.toString() ? `?${qs}` : ""}`;
}

export function dismissPromptToAction(
  promptResult: string | null,
): { cancelled: true } | { cancelled: false; note?: string } {
  if (promptResult === null) return { cancelled: true };
  const trimmed = promptResult.trim();
  return { cancelled: false, note: trimmed || undefined };
}

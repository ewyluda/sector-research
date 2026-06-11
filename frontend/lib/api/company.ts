import { apiFetch } from "./core";

// ── Company workspace ─────────────────────────────────────────────────────────

export interface CompanyHeader {
  ticker: string;
  name: string | null;
  exchange: string | null;
  logo_url: string | null;
  currency: string | null;
  price: number | null;
  change: number | null;
  change_pct: number | null;
  delay_label: string;
}

export async function getCompanyHeader(ticker: string): Promise<CompanyHeader> {
  return apiFetch<CompanyHeader>(`/api/company/${encodeURIComponent(ticker)}/header`);
}

export interface StatItem {
  label: string;
  value: number | null;
  // "pct_growth" = growth/CAGR rates: tiny-base artifacts render as "n/m".
  unit: "pct" | "pct_growth" | "x" | "money" | "num" | "int";
}

export interface OverviewStatGroup {
  title: string;
  items: StatItem[];
}

export interface PricePoint {
  date: string;
  close: number;
}

export interface CompanyOverview {
  ticker: string;
  sector: string | null;
  industry: string | null;
  stats: OverviewStatGroup[];
  prices: PricePoint[];
}

export async function getCompanyOverview(ticker: string): Promise<CompanyOverview> {
  return apiFetch<CompanyOverview>(`/api/company/${encodeURIComponent(ticker)}/overview`);
}

export interface CompanyFinancials {
  ticker: string;
  period: "annual" | "quarter";
  periods: string[];
  income: Record<string, (number | null)[]>;
  balance: Record<string, (number | null)[]>;
  cashflow: Record<string, (number | null)[]>;
}

export async function getCompanyFinancials(
  ticker: string,
  period: "annual" | "quarter",
): Promise<CompanyFinancials> {
  return apiFetch<CompanyFinancials>(
    `/api/company/${encodeURIComponent(ticker)}/financials?period=${period}`,
  );
}

export interface TranscriptEvent {
  quarter: number;
  fiscal_year: number;
  date: string;
}

export interface TranscriptList {
  ticker: string;
  events: TranscriptEvent[];
}

export interface TranscriptSegment {
  speaker: string;
  text: string;
}

export interface Transcript {
  ticker: string;
  year: number;
  quarter: number;
  date: string | null;
  segments: TranscriptSegment[];
}

export async function getTranscripts(ticker: string): Promise<TranscriptList> {
  return apiFetch<TranscriptList>(`/api/company/${encodeURIComponent(ticker)}/transcripts`);
}

export async function getTranscript(ticker: string, year: number, quarter: number): Promise<Transcript> {
  return apiFetch<Transcript>(
    `/api/company/${encodeURIComponent(ticker)}/transcripts/${year}/${quarter}`,
  );
}

export async function summarizeTranscript(ticker: string, year: number, quarter: number): Promise<{ summary_md: string }> {
  return apiFetch<{ summary_md: string }>(
    `/api/company/${encodeURIComponent(ticker)}/transcripts/${year}/${quarter}/summary`,
    { method: "POST" },
  );
}

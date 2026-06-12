import { apiFetch } from "./core";

// ── Filings (SEC EDGAR narrative section extracts) ────────────────────────────

export interface FilingSectionSummary {
  section_key: string;
  heading: string | null;
  char_count: number;
  extraction_method: string;
}

export interface FilingRecord {
  id: string;
  accession_number: string;
  ticker: string;
  form_type: string;
  filing_date: string;
  period_of_report: string | null;
  primary_document_url: string | null;
  sections: FilingSectionSummary[];
}

export interface FilingSectionText {
  section_key: string;
  heading: string | null;
  text: string;
  char_count: number;
  extraction_method: string;
  extracted_at: string;
}

export interface FilingIngestFormResult {
  accession_number: string | null;
  filing_date: string | null;
  sections_added: number;
  sections_skipped_existing: number;
  error: string | null;
}

export interface FilingIngestSummary {
  ticker: string;
  cik: string | null;
  filings_processed: number;
  sections_added: number;
  sections_skipped_existing: number;
  per_form: Record<string, FilingIngestFormResult>;
  errors: string[];
}

export const filings = {
  list: (ticker: string) =>
    apiFetch<FilingRecord[]>(`/api/filings/${encodeURIComponent(ticker)}`),
  getSection: (ticker: string, accession: string, sectionKey: string) =>
    apiFetch<FilingSectionText>(
      `/api/filings/${encodeURIComponent(ticker)}/${encodeURIComponent(accession)}/sections/${encodeURIComponent(sectionKey)}`
    ),
  ingestTicker: (ticker: string) =>
    apiFetch<FilingIngestSummary>(
      `/api/filings/ingest/${encodeURIComponent(ticker)}`,
      { method: "POST" }
    ),
  ingestBatch: (tickers: string[]) =>
    apiFetch<FilingIngestSummary[]>(`/api/filings/ingest/batch`, {
      method: "POST",
      body: JSON.stringify({ tickers }),
    }),
};

// ── Relationships + Counterparty Resolution (Phase B + C) ─────────────────────

export interface RelationshipRecord {
  id: string;
  accession_number: string;
  form_type: string;
  filing_date: string;
  section_key: string;
  counterparty_name: string;
  relationship_type: string;
  magnitude_pct: number | null;
  unnamed: boolean;
  verbatim_quote: string | null;
  confirmed_bilateral: boolean;
  resolved_to_cik: string | null;
  resolved_to_ticker: string | null;
  extracted_at: string;
}

export interface ResolutionCandidate {
  cik: string;
  ticker: string | null;
  canonical_name: string;
  score: number;
  source: string;
}

export interface UnresolvedCounterparty {
  counterparty_name: string;
  alias_normalized: string;
  occurrence_count: number;
  tickers: string[];
  candidates: ResolutionCandidate[];
}

export interface ManualAliasRequest {
  alias_name: string;
  canonical_cik: string;
  canonical_ticker: string | null;
  canonical_name: string;
  created_by?: string | null;
}

export interface DismissedAlias {
  alias_name: string;
  alias_normalized: string;
  created_at: string | null;
  created_by: string | null;
}

export interface ResolveSummary {
  ticker: string;
  rows_considered: number;
  already_resolved: number;
  resolved_via_alias: number;
  resolved_via_exact: number;
  resolved_via_fuzzy: number;
  unresolved_surfaced_to_queue: number;
  unnamed_skipped: number;
  relationships_updated: number;
  aliases_created: number;
}

export interface CompetitionResolveSummary {
  ticker: string;
  rows_considered: number;
  competitors_considered: number;
  already_resolved: number;
  resolved_via_alias: number;
  resolved_via_exact: number;
  resolved_via_fuzzy: number;
  unresolved: number;
  rows_updated: number;
  aliases_created: number;
  relationships_updated: number;
}

export interface CombinedResolveSummary {
  relationships: ResolveSummary;
  competition: CompetitionResolveSummary;
}

// ── Competition extraction (Phase A for competitive landscape) ─────────────────

export interface CompetitorChip {
  name: string;
  ticker: string | null;
  magnitude_pct: number | null;
  verbatim_quote: string | null;
  tracked: boolean;
}

export interface CompetitionArea {
  area_of_competition: string;
  competitors: CompetitorChip[];
}

export interface CompetitionSegment {
  segment_name: string;
  narrative: string;
  areas: CompetitionArea[];
}

export interface CompetitionFiling {
  accession_number: string;
  form_type: string;
  filing_date: string;
  sec_filing_url: string | null;
}

export interface CompetitionData {
  ticker: string;
  filing: CompetitionFiling | null;
  extracted_at: string | null;
  segments: CompetitionSegment[];
}

export interface CompetitionExtractionSummary {
  ticker: string;
  filing_id: string | null;
  segments_extracted: number;
  areas_extracted: number;
  competitors_extracted: number;
  skipped: boolean;
  errors: string[];
  resolver: CompetitionResolveSummary | null;
}

// ── Fan-out (bulk ingest + extract + resolve per theme or ticker) ─────────────

export type FanoutStatusLiteral = "running" | "completed" | "failed";
export type FanoutStage = "ingest" | "extract" | "extract_transcripts" | "resolve";

export type FanoutScope =
  | { kind: "theme"; theme_id: string }
  | { kind: "ticker"; ticker: string };

export interface FanoutError {
  ticker: string;
  stage: FanoutStage;
  message: string;
}

export interface FanoutStatus {
  fanout_id: string;
  status: FanoutStatusLiteral;
  scope: FanoutScope;
  total_tickers: number;
  completed_tickers: number;
  current_ticker: string | null;
  current_stage: FanoutStage | null;
  errors: FanoutError[];
  started_at: string;
  finished_at: string | null;
}

export type TranscriptExtractionSummary = {
  ticker: string;
  transcripts_considered: number;
  transcripts_extracted: number;
  transcripts_skipped_existing: number;
  relationships_added: number;
  relationships_dropped: number;
  per_transcript: Array<{
    year: number | null;
    quarter: number | null;
    date: string;
    relationships_added: number;
    relationships_dropped: number;
    skipped: string | null;
    error: string | null;
  }>;
  errors: string[];
};

export const relationships = {
  listForTicker: (ticker: string) =>
    apiFetch<RelationshipRecord[]>(
      `/api/filings/${encodeURIComponent(ticker)}/relationships`
    ),
  extractTicker: (ticker: string, force = false) =>
    apiFetch<unknown>(
      `/api/filings/extract-relationships/${encodeURIComponent(ticker)}${force ? "?force=true" : ""}`,
      { method: "POST" }
    ),
  resolveTicker: (ticker: string) =>
    apiFetch<CombinedResolveSummary>(
      `/api/relationships/resolve/${encodeURIComponent(ticker)}`,
      { method: "POST" }
    ),
  listUnresolved: (limit = 50) =>
    apiFetch<UnresolvedCounterparty[]>(
      `/api/relationships/unresolved?limit=${limit}`
    ),
  createAlias: (body: ManualAliasRequest) =>
    apiFetch<{ alias_id: string; relationships_updated: number }>(
      `/api/relationships/alias`,
      { method: "POST", body: JSON.stringify(body) }
    ),
  getGraph: (
    ticker: string,
    options: {
      direction?: "out" | "in" | "both";
      depth?: 1 | 2;
      themeId?: string;
    } = {}
  ) => {
    const direction = options.direction ?? "both";
    const params = new URLSearchParams({ direction });
    if (options.depth) params.set("depth", String(options.depth));
    if (options.themeId) params.set("theme_id", options.themeId);
    return apiFetch<SupplyChainGraph>(
      `/api/relationships/graph/${encodeURIComponent(ticker)}?${params.toString()}`
    );
  },
  getThemeGraph: (themeId: string) =>
    apiFetch<ThemeGraphResponse>(
      `/api/relationships/theme-graph/${encodeURIComponent(themeId)}`
    ),
  reconcile: () =>
    apiFetch<{ pairs_reconciled: number; rows_flipped: number }>(
      `/api/relationships/reconcile`,
      { method: "POST" }
    ),
  dismiss: (counterparty_name: string) =>
    apiFetch<{ alias_normalized: string; dismissed: boolean }>(
      `/api/relationships/dismiss`,
      { method: "POST", body: JSON.stringify({ counterparty_name, created_by: "ui-curator" }) }
    ),
  undismiss: (aliasNormalized: string) =>
    apiFetch<{ alias_normalized: string; restored: boolean }>(
      `/api/relationships/dismiss/${encodeURIComponent(aliasNormalized)}`,
      { method: "DELETE" }
    ),
  listDismissed: () =>
    apiFetch<DismissedAlias[]>(`/api/relationships/dismissed`),
};

export const competition = {
  get: (ticker: string) =>
    apiFetch<CompetitionData>(
      `/api/competition/${encodeURIComponent(ticker)}`
    ),
  extract: (ticker: string, force = false) =>
    apiFetch<CompetitionExtractionSummary>(
      `/api/filings/extract-competition/${encodeURIComponent(ticker)}${force ? "?force=true" : ""}`,
      { method: "POST" }
    ),
};

export const transcripts = {
  extract: (ticker: string, force = false) =>
    apiFetch<TranscriptExtractionSummary>(
      `/api/transcripts/extract-relationships/${encodeURIComponent(ticker)}${force ? "?force=true" : ""}`,
      { method: "POST" }
    ),
};

export const fanouts = {
  startTheme: (themeId: string, force: boolean = false) =>
    apiFetch<FanoutStatus>(
      `/api/themes/${encodeURIComponent(themeId)}/relationships/fanout${force ? "?force=true" : ""}`,
      { method: "POST" }
    ),
  startTicker: (ticker: string, force: boolean = false) =>
    apiFetch<FanoutStatus>(
      `/api/tickers/${encodeURIComponent(ticker)}/relationships/fanout${force ? "?force=true" : ""}`,
      { method: "POST" }
    ),
  get: (fanoutId: string) =>
    apiFetch<FanoutStatus>(`/api/fanouts/${encodeURIComponent(fanoutId)}`),
};

// ── Supply-chain graph (Phase D) ─────────────────────────────────────────────

export interface SupplyChainGraphNode {
  id: string;
  ticker: string | null;
  cik: string | null;
  name: string;
  is_root: boolean;
  tracked: boolean;
  unnamed: boolean;
  hop: number;
  in_selected_theme: boolean;
}

export interface SupplyChainGraphEdge {
  from_id: string;
  to_id: string;
  relationship_type: string;
  direction: "out" | "in";
  magnitude_pct: number | null;
  unnamed: boolean;
  confirmed_bilateral: boolean;
  verbatim_quote: string | null;
  source_ticker: string;
  accession_number: string;
  filing_date: string;
  section_key: string;
  hop: number;
}

export interface SupplyChainEntry {
  from_id: string;
  to_id: string;
  direction: "out" | "in";
  magnitude_pct: number | null;
  confirmed_bilateral: boolean;
  verbatim_quote: string | null;
  source_ticker: string;
  accession_number: string;
  filing_date: string;
  section_key: string;
  unnamed: boolean;
  counterparty_name?: string;
  counterparty_ticker?: string | null;
  counterparty_cik?: string | null;
  counterparty_tracked?: boolean;
}

export interface SupplyChainGraph {
  root_ticker: string;
  nodes: SupplyChainGraphNode[];
  edges: SupplyChainGraphEdge[];
  summary: Record<
    string,
    {
      out_named: SupplyChainEntry[];
      out_unnamed: SupplyChainEntry[];
      in_named: SupplyChainEntry[];
    }
  >;
}

export interface ThemeGraphResponse {
  theme_id: string;
  theme_name: string;
  nodes: SupplyChainGraphNode[];
  edges: SupplyChainGraphEdge[];
  too_dense: boolean;
  node_count: number;
  edge_count: number;
}

import { BASE } from "./core";

// ── Prospectus reports ────────────────────────────────────────────────────────

export type IPOVerdict = "participate" | "watch_post_lockup" | "pass";
export type ProspectusStatus = "ingesting" | "analyzing" | "completed" | "failed";

export interface ExtractedSectionSummary {
  section_key: string;
  heading: string;
  char_count: number;
}

export interface AnnualFinancialRow {
  period_label: string;
  revenue: number | null;
  cost_of_revenue: number | null;
  operating_income: number | null;
  net_income: number | null;
  cash_and_equivalents: number | null;
  total_debt: number | null;
  source_snippet: string;
}

export interface InterimFinancialRow {
  period_label: string;
  revenue: number | null;
  operating_income: number | null;
  net_income: number | null;
  source_snippet: string;
}

export interface ProspectusFinancials {
  annual: AnnualFinancialRow[];
  interim: InterimFinancialRow[];
}

export interface IngestStepOutput {
  accession_number: string;
  primary_document_url: string;
  issuer_cik: string;
  issuer_name: string;
  proposed_ticker: string | null;
  form_type: string;
  sections: ExtractedSectionSummary[];
  financials: ProspectusFinancials;
}

export interface RelationshipSummary {
  counterparty_name: string;
  relationship_type: string;
  magnitude_pct: number | null;
  resolved_to_ticker: string | null;
  verbatim_quote: string;
}

export interface RelationshipsStepOutput {
  edges_extracted: number;
  edges_resolved: number;
  edges: RelationshipSummary[];
}

export interface ProspectusCategoryResult {
  category: string;
  content: string;
  score: number;
  key_findings: string[];
}

export interface CategoriesStepOutput {
  results: Record<string, ProspectusCategoryResult>;
  failures: Record<string, string>;
}

export interface KeyRisk {
  risk: string;
  severity: "low" | "medium" | "high";
  category_source: string;
}

export interface PostIPOPlanItem {
  question: string;
  why_it_matters: string;
  expected_data_source: string;
}

export interface ProspectusThesisOutput {
  thesis_statement: string;
  key_risks: KeyRisk[];
  ipo_verdict: IPOVerdict;
  price_range_commentary: string | null;
  post_ipo_research_plan: PostIPOPlanItem[];
}

export interface ProspectusReport {
  id: string;
  accession_number: string;
  issuer_cik: string;
  issuer_name: string;
  proposed_ticker: string | null;
  synthetic_ticker: string;
  theme_id: string | null;
  status: ProspectusStatus;
  step_outputs: {
    ingest?: IngestStepOutput;
    relationships?: RelationshipsStepOutput;
    categories?: CategoriesStepOutput;
    thesis?: ProspectusThesisOutput;
  };
  error_message: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export const prospectusApi = {
  create: async (
    body: { url_or_accession: string; theme_id?: string | null },
  ): Promise<{ report_id: string }> => {
    const r = await fetch(`${BASE}/api/prospectus`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error(`prospectus create failed: ${r.status} ${await r.text()}`);
    return r.json();
  },
  get: async (reportId: string): Promise<ProspectusReport> => {
    const r = await fetch(`${BASE}/api/prospectus/${reportId}`);
    if (!r.ok) throw new Error(`prospectus get failed: ${r.status}`);
    return r.json();
  },
  list: async (limit = 50): Promise<ProspectusReport[]> => {
    const r = await fetch(`${BASE}/api/prospectus?limit=${limit}`);
    if (!r.ok) throw new Error(`prospectus list failed: ${r.status}`);
    return r.json();
  },
  remove: async (reportId: string): Promise<void> => {
    const r = await fetch(`${BASE}/api/prospectus/${reportId}`, { method: "DELETE" });
    if (!r.ok && r.status !== 204) throw new Error(`prospectus delete failed: ${r.status}`);
  },
  streamUrl: (reportId: string) => `${BASE}/api/prospectus/${reportId}/stream`,
};

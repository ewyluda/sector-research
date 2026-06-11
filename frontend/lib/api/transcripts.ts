import { apiFetch, BASE } from "./core";

// ── Transcript delta ────────────────────────────────────────────────────────

export type TranscriptAxisDirection = "softening" | "strengthening" | "stable";
export type TranscriptAxisMagnitude = "minor" | "material" | "regime_change";

export interface TranscriptQuoteRef {
  year: number;
  quarter: number;
  role: string;
  text: string;
}

export interface TranscriptAxisDelta {
  direction: TranscriptAxisDirection;
  magnitude: TranscriptAxisMagnitude;
  summary: string;
  quotes: TranscriptQuoteRef[];
}

export interface TranscriptAxesDelta {
  business_quality: TranscriptAxisDelta | null;
  risk_assessment: TranscriptAxisDelta | null;
  growth_earnings: TranscriptAxisDelta | null;
  sentiment_narrative: TranscriptAxisDelta | null;
  management_governance: TranscriptAxisDelta | null;
  future_durability: TranscriptAxisDelta | null;
  macro_regime: TranscriptAxisDelta | null;
  financial_health: TranscriptAxisDelta | null;
  valuation_stage: TranscriptAxisDelta | null;
}

export interface TranscriptDeltaRead {
  id: string;
  ticker: string;
  transcripts_window: { year: number; quarter: number }[];
  axes: TranscriptAxesDelta;
  computed_at: string;
}

export const transcriptDeltaApi = {
  async getLatest(ticker: string): Promise<TranscriptDeltaRead | null> {
    const r = await fetch(`${BASE}/api/transcripts/delta/${encodeURIComponent(ticker)}/latest`);
    if (r.status === 204) return null;
    if (!r.ok) throw new Error(`getLatest ${ticker}: ${r.status}`);
    return r.json();
  },
  async getHistory(ticker: string): Promise<TranscriptDeltaRead[]> {
    return apiFetch(`/api/transcripts/delta/${encodeURIComponent(ticker)}/history`);
  },
  async compute(ticker: string, opts: { force?: boolean } = {}): Promise<TranscriptDeltaRead> {
    const qs = opts.force ? "?force=true" : "";
    const r = await fetch(
      `${BASE}/api/transcripts/delta/${encodeURIComponent(ticker)}${qs}`,
      { method: "POST" },
    );
    if (r.status === 404) throw new Error(`No transcripts available for ${ticker}`);
    if (!r.ok) throw new Error(`compute ${ticker}: ${r.status}`);
    return r.json();
  },
};

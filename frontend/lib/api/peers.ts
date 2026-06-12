import { apiFetch } from "./core";

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

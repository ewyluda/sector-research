import type { CuratedFinancials, QuarterlyMetric } from "./api";

/** Growth beyond this is a tiny-base artifact, not a signal — same threshold as
 *  the backend (formatters.GROWTH_NM_THRESHOLD_PCT) and components/company/formatStat. */
export const GROWTH_NM_THRESHOLD_PCT = 1000;

/** Series whose yoy_growth is a year-over-year growth figure (margins and the
 *  current ratio carry none). */
const GROWTH_SERIES = [
  "quarterly_revenue",
  "quarterly_eps",
  "quarterly_cash",
  "quarterly_total_debt",
  "quarterly_shareholders_equity",
  "quarterly_operating_cf",
  "quarterly_free_cf",
  "quarterly_capex",
] as const;

/** Percent growth, or null ("n/m") on a zero/negative base or a tiny-base blowup. */
export function growthPct(current: number, prior: number | null | undefined): number | null {
  if (prior == null || prior <= 0) return null;
  const g = ((current - prior) / prior) * 100;
  return Math.abs(g) > GROWTH_NM_THRESHOLD_PCT ? null : g;
}

/** yoy_growth recomputed from the series itself: each quarter vs the same
 *  quarter a year earlier (index + 4; series are newest-first). */
export function withTrueYoy(series: QuarterlyMetric[]): QuarterlyMetric[] {
  return series.map((m, i) => ({ ...m, yoy_growth: growthPct(m.value, series[i + 4]?.value) }));
}

/**
 * Normalise curated financials at the boundary, for old and new runs alike:
 * - runs stored before 2026-09-27 carry quarter-over-quarter values in
 *   yoy_growth (the UI labelled them "YoY": SMCI read -19.2% for a +122.7% year);
 * - a non-positive DCF value makes the DCF gap meaningless (SMCI: "-303%").
 */
export function normalizeCuratedFinancials(cf: CuratedFinancials | null): CuratedFinancials | null {
  if (!cf) return cf;
  const out: CuratedFinancials = { ...cf };
  for (const key of GROWTH_SERIES) {
    const series = cf[key];
    if (Array.isArray(series)) out[key] = withTrueYoy(series);
  }
  if (cf.dcf_intrinsic_value != null && cf.dcf_intrinsic_value <= 0) out.dcf_gap_percent = null;
  return out;
}

/** TTM EPS growth vs the TTM one year earlier (quarters 0–3 vs 4–7). */
export function ttmEpsGrowth(eps: QuarterlyMetric[]): number | null {
  if (eps.length < 8) return null;
  const sum = (xs: QuarterlyMetric[]) => xs.reduce((s, m) => s + m.value, 0);
  return growthPct(sum(eps.slice(0, 4)), sum(eps.slice(4, 8)));
}

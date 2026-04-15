/**
 * Number formatters used across the dashboard.
 */

/**
 * Format a raw USD amount compactly.
 *  ≥ 1B → $X.XXB
 *  ≥ 1M → $X.XM
 *  ≥ 1K → $XK (no decimals — small values shouldn't drown in tick labels)
 *  otherwise → $X,XXX with thousands separator.
 */
export function formatUSD(v: number): string {
  if (v == null || !Number.isFinite(v)) return "—";
  const abs = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  if (abs >= 1e9) return `${sign}$${(abs / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `${sign}$${Math.round(abs / 1e3)}K`;
  return `${sign}$${Math.round(abs).toLocaleString("en-US")}`;
}

/**
 * Format a plain number with thousands separators. No currency prefix.
 */
export function formatNumber(v: number, fractionDigits = 0): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return v.toLocaleString("en-US", {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  });
}

/**
 * Format a percent value that is already scaled to 0–100 (not 0–1).
 */
export function formatPercent(v: number, fractionDigits = 1): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return `${v.toFixed(fractionDigits)}%`;
}

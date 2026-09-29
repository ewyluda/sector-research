/**
 * Display formatting for financial-model cells. The model stores raw units —
 * fractions for rates, whole dollars for amounts, whole shares — so the grid
 * formats by row key: rates as percentages, amounts and share counts in
 * millions, EPS in dollars, working-capital days as whole days.
 */

const RATE_SUFFIXES = ["_pct", "_pct_revenue", "_rate", "_yield", "_ratio"];

export function isRateKey(key: string): boolean {
  return RATE_SUFFIXES.some((s) => key.endsWith(s));
}

export function formatModelValue(key: string, value: number | null): string {
  if (value === null || !Number.isFinite(value)) return "—";
  if (isRateKey(key)) return `${(value * 100).toFixed(1)}%`;
  if (key.endsWith("_days")) return value.toFixed(0);
  if (key === "eps_diluted") return value.toFixed(2);
  const millions = value / 1e6;
  return millions.toLocaleString("en-US", { maximumFractionDigits: Math.abs(millions) < 100 ? 1 : 0 });
}

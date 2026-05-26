export type Unit = "K" | "M" | "B";

/** Format an absolute money value scaled to the chosen unit. Null → em-dash. */
export function fmtMoney(value: number | null, unit: Unit): string {
  if (value == null || Number.isNaN(value)) return "—";
  const div = unit === "B" ? 1e9 : unit === "M" ? 1e6 : 1e3;
  const scaled = value / div;
  return scaled.toLocaleString("en-US", { maximumFractionDigits: scaled >= 100 || scaled <= -100 ? 0 : 1 });
}

/** Format a percentage (value is already a ratio, e.g. 0.46 → "46.0%"). Null → em-dash. */
export function fmtPct(value: number | null): string {
  if (value == null || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(1)}%`;
}

/** Per-share / raw numeric value (EPS etc.). Null → em-dash. */
export function fmtNum(value: number | null): string {
  if (value == null || Number.isNaN(value)) return "—";
  return value.toFixed(2);
}

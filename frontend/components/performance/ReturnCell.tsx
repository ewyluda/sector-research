"use client";

/** Sign-colored return cell. Accepts either a fractional string ("0.123") or null. */
export function ReturnCell({ value, asPercent = true }: { value: string | number | null; asPercent?: boolean }) {
  if (value == null) return <span className="text-[var(--text-muted)]">—</span>;
  const num = typeof value === "string" ? parseFloat(value) : value;
  if (Number.isNaN(num)) return <span className="text-[var(--text-muted)]">—</span>;
  const display = asPercent ? `${(num * 100).toFixed(2)}%` : num.toFixed(2);
  const color =
    num > 0.0001 ? "text-emerald-400"
    : num < -0.0001 ? "text-rose-400"
    : "text-[var(--text-muted)]";
  const sign = num > 0.0001 ? "+" : "";
  return <span className={color}>{sign}{display}</span>;
}

import type { StatItem } from "@/lib/api";

/** Format a stat value by unit. Null → em-dash. */
export function formatStat(value: number | null, unit: StatItem["unit"]): string {
  if (value == null || Number.isNaN(value)) return "—";
  switch (unit) {
    case "pct":
      return `${(value * 100).toFixed(1)}%`;
    case "pct_growth":
      // Tiny-base growth rates beyond ±1000% (e.g. ORCL FCF growth -59.1 →
      // "-5911.7%") are arithmetic noise, not signal — render "not meaningful".
      // Margins are guarded backend-side (metric_guards.py); this rule is
      // growth/CAGR-only.
      if (Math.abs(value) > 10) return "n/m";
      return `${(value * 100).toFixed(1)}%`;
    case "x":
      return `${value.toFixed(1)}x`;
    case "int":
      return Math.round(value).toLocaleString();
    case "num":
      return value.toFixed(2);
    case "money": {
      const a = Math.abs(value);
      if (a >= 1e12) return `$${(value / 1e12).toFixed(2)}T`;
      if (a >= 1e9) return `$${(value / 1e9).toFixed(1)}B`;
      if (a >= 1e6) return `$${(value / 1e6).toFixed(0)}M`;
      return `$${value.toFixed(2)}`;
    }
    default:
      return String(value);
  }
}

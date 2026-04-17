/**
 * Shared 4-tier score palette. Returns Tailwind classes for the two common
 * presentations:
 *   - `badge`     — colored pill (header chips, score bar segments)
 *   - `solid`     — slightly higher-contrast variant used by ScoreBar segments
 *
 * Thresholds chosen so scores in the 40-60 range read as distinct (the old
 * 3-tier 50/70 setup clumped most values into one "amber" bucket).
 */
export type ScoreTier = "strong" | "solid" | "caution" | "weak" | "pending";

export function scoreTier(score: number | null): ScoreTier {
  if (score == null) return "pending";
  if (score >= 70) return "strong";
  if (score >= 55) return "solid";
  if (score >= 40) return "caution";
  return "weak";
}

const BADGE: Record<ScoreTier, string> = {
  pending: "bg-[var(--color-surface-alt)] text-[var(--color-text-faint)]",
  strong: "bg-emerald-500/15 text-emerald-400",
  solid: "bg-amber-500/15 text-amber-400",
  caution: "bg-orange-500/15 text-orange-400",
  weak: "bg-red-500/15 text-red-400",
};

const SOLID: Record<ScoreTier, string> = {
  pending: "bg-[var(--color-surface-alt)] text-[var(--color-text-faint)] animate-pulse",
  strong: "bg-emerald-500/20 text-emerald-400",
  solid: "bg-amber-500/20 text-amber-400",
  caution: "bg-orange-500/20 text-orange-400",
  weak: "bg-red-500/20 text-red-400",
};

export function scoreBadge(score: number | null): string {
  return BADGE[scoreTier(score)];
}

export function scoreSegment(score: number | null): string {
  return SOLID[scoreTier(score)];
}

/**
 * Extracted from app/report/[runId]/page.tsx so other phase cards
 * (QuickScreenCard, future ThesisCard, etc.) can reuse it.
 *
 * NOTE: the class strings reference var(--color-accent), var(--color-surface),
 * etc. which are NOT defined in globals.css — they're a latent issue in the
 * report and library pages. Preserving the exact strings here keeps the
 * report page rendering byte-for-byte identical after the extraction.
 * Fixing those undefined vars is out of scope for this plan.
 */

import type { Citation } from "@/lib/api";

export function CitationList({ citations }: { citations: Citation[] }) {
  if (!citations?.length) return null;
  return (
    <div className="mt-3 flex flex-wrap gap-2">
      {citations.map((c, i) => (
        <a
          key={i}
          href={c.source_url}
          target="_blank"
          rel="noopener noreferrer"
          className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs border transition-colors hover:opacity-80 ${
            c.tier === 1
              ? "bg-[var(--color-accent)]/10 text-[var(--color-accent)] border-[var(--color-accent)]/20"
              : "bg-[var(--color-surface)] text-[var(--color-text-secondary)] border-[var(--color-border)]"
          }`}
        >
          <span className="font-medium">[{i + 1}]</span>
          {c.source_name} · {c.metric}
        </a>
      ))}
    </div>
  );
}

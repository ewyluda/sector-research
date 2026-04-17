import type { Citation } from "@/lib/api";

/**
 * Pulls a short "family" tag from a citation's source name so the list can
 * be clustered by provider (FMP, FRED, SEC EDGAR, X signal, etc.) instead of
 * rendering one flat strip of 20+ chips.
 */
function sourceFamily(sourceName: string): string {
  const trimmed = sourceName.trim();
  if (!trimmed) return "Other";
  // "FMP /income-statement", "FRED /FEDFUNDS", "SEC EDGAR /company-facts" →
  // take the segment before the first " /" or " ·".
  const splitIdx = trimmed.search(/\s[/·]/);
  const head = splitIdx >= 0 ? trimmed.slice(0, splitIdx) : trimmed;
  return head.trim() || "Other";
}

function groupByFamily(citations: Citation[]): Array<{ family: string; items: { citation: Citation; originalIndex: number }[] }> {
  const groups = new Map<string, { citation: Citation; originalIndex: number }[]>();
  citations.forEach((citation, originalIndex) => {
    const key = sourceFamily(citation.source_name);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key)!.push({ citation, originalIndex });
  });
  return [...groups.entries()].map(([family, items]) => ({ family, items }));
}

export function CitationList({ citations }: { citations: Citation[] }) {
  if (!citations?.length) return null;
  const groups = groupByFamily(citations);

  return (
    <div className="mt-3 space-y-2">
      {groups.map(({ family, items }) => (
        <div key={family} className="flex flex-wrap gap-2 items-center">
          <span className="text-[10px] font-medium uppercase tracking-wider text-[var(--color-text-muted)] shrink-0 mr-1">
            {family}
          </span>
          {items.map(({ citation, originalIndex }) => (
            <a
              key={originalIndex}
              href={citation.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs border transition-colors hover:opacity-80 ${
                citation.tier === 1
                  ? "bg-[var(--color-accent)]/10 text-[var(--color-accent)] border-[var(--color-accent)]/20"
                  : "bg-[var(--color-surface)] text-[var(--color-text-secondary)] border-[var(--color-border)]"
              }`}
            >
              <span className="font-medium">[{originalIndex + 1}]</span>
              {citation.source_name} · {citation.metric}
            </a>
          ))}
        </div>
      ))}
    </div>
  );
}

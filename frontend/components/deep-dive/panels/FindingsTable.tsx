import type { DeepDiveFinding } from "@/lib/api";
import { CitationBlock } from "./CitationBlock";

/**
 * Stacked vertical list of findings. Each finding is its own block with
 * the statement above and the evidence/citation immediately below.
 * Reads well in narrow columns unlike the previous 2-column table.
 */
export function FindingsTable({ findings }: { findings: DeepDiveFinding[] }) {
  if (!findings || findings.length === 0) return null;
  return (
    <ol className="space-y-3 list-none m-0 p-0">
      {findings.map((f, i) => (
        <li key={i} className="space-y-1.5">
          <div className="flex gap-2">
            <span className="flex-shrink-0 text-[10px] font-mono font-semibold text-[var(--color-text-muted)] mt-0.5">
              {String(i + 1).padStart(2, "0")}
            </span>
            <p className="text-[12px] leading-snug text-[var(--color-text-primary)]">
              {f.finding}
            </p>
          </div>
          {f.evidence && (
            <div className="pl-6">
              <CitationBlock>{f.evidence}</CitationBlock>
            </div>
          )}
        </li>
      ))}
    </ol>
  );
}

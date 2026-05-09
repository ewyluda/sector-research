"use client";

import type { ResearchOutput } from "@/lib/api";

const CLASS_COLOR: Record<string, string> = {
  confirms_thesis: "text-[var(--success)]",
  threatens_thesis: "text-[var(--error)]",
  new_unknown: "text-[var(--warning)]",
};

export function ResearchCard({ output }: { output: ResearchOutput }) {
  return (
    <div className="space-y-3 mt-2">
      <p className="text-sm text-[var(--text)] whitespace-pre-line">{output.summary}</p>

      {output.highlights.length > 0 && (
        <ul className="space-y-1">
          {output.highlights.map((h, i) => (
            <li key={i} className="text-sm flex gap-2">
              <span className={`text-xs uppercase font-semibold ${CLASS_COLOR[h.classification]}`}>
                {h.classification.replace(/_/g, " ")}
              </span>
              <span className="text-[var(--text)]">{h.text}</span>
            </li>
          ))}
        </ul>
      )}

      {output.new_open_questions.length > 0 && (
        <details className="rounded border border-[var(--border)] bg-[var(--surface)] p-2">
          <summary className="text-sm font-medium text-[var(--text)] hover:text-[var(--primary)] cursor-pointer">
            New open questions ({output.new_open_questions.length})
          </summary>
          <ul className="mt-2 space-y-1">
            {output.new_open_questions.map((q, i) => (
              <li key={i} className="text-sm text-[var(--text)]">
                <span className="text-xs px-1 rounded mr-2 bg-[var(--surface-alt)] text-[var(--text-muted)]">
                  {q.classification}
                </span>
                {q.question}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

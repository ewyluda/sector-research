import type { RelationshipsStepOutput } from "@/lib/api";

export function RelationshipsCard({ rel }: { rel: RelationshipsStepOutput }) {
  return (
    <section className="border border-[var(--border)] rounded-lg p-5 bg-[var(--surface)]">
      <h2 className="text-xl font-semibold mb-1">Counterparty relationships</h2>
      <p className="text-sm text-[var(--text-muted)] mb-3">
        {rel.edges_extracted} extracted · {rel.edges_resolved} resolved to known tickers
      </p>
      {rel.edges.length === 0 ? (
        <p className="text-sm text-[var(--text-muted)]">No counterparty edges extracted.</p>
      ) : (
        <ul className="space-y-2">
          {rel.edges.map((e, i) => (
            <li key={i} className="text-sm border-b border-[var(--border)] pb-2">
              <div>
                <span className="font-medium">{e.counterparty_name || "(unnamed)"}</span>
                <span className="text-[var(--text-muted)]"> — {e.relationship_type}</span>
                {e.resolved_to_ticker && (
                  <span className="text-blue-400 ml-2">${e.resolved_to_ticker}</span>
                )}
                {e.magnitude_pct !== null && (
                  <span className="text-[var(--text-muted)] ml-2">{e.magnitude_pct}%</span>
                )}
              </div>
              {e.verbatim_quote && (
                <blockquote className="italic text-[var(--text-muted)] mt-1 text-xs">
                  &ldquo;{e.verbatim_quote}&rdquo;
                </blockquote>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

import type { ProspectusThesisOutput } from "@/lib/api";
import { VerdictPill } from "../VerdictPill";

const SEVERITY_COLOR: Record<string, string> = {
  high: "text-red-400",
  medium: "text-amber-400",
  low: "text-blue-400",
};

export function ThesisCard({ thesis }: { thesis: ProspectusThesisOutput }) {
  return (
    <section className="border border-[var(--border)] rounded-lg p-5 bg-[var(--surface)]">
      <header className="flex items-center justify-between mb-3">
        <h2 className="text-xl font-semibold">Thesis</h2>
        <VerdictPill verdict={thesis.ipo_verdict} />
      </header>
      <p className="text-[var(--text)] mb-4">{thesis.thesis_statement}</p>

      {thesis.price_range_commentary && (
        <div className="mb-4">
          <h3 className="text-sm font-semibold mb-1">Price range commentary</h3>
          <p className="text-sm text-[var(--text-muted)]">{thesis.price_range_commentary}</p>
        </div>
      )}

      {thesis.key_risks.length > 0 && (
        <div className="mb-4">
          <h3 className="text-sm font-semibold mb-1">Key risks</h3>
          <ul className="text-sm space-y-0.5">
            {thesis.key_risks.map((r, i) => (
              <li key={i}>
                <span className={`uppercase text-xs mr-2 ${SEVERITY_COLOR[r.severity] ?? ""}`}>
                  {r.severity}
                </span>
                <span>{r.risk}</span>
                <span className="text-[var(--text-muted)] text-xs ml-1">({r.category_source})</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {thesis.post_ipo_research_plan.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold mb-1">Post-IPO research plan</h3>
          <ul className="text-sm space-y-2">
            {thesis.post_ipo_research_plan.map((p, i) => (
              <li key={i} className="border-l-2 border-[var(--border)] pl-3">
                <div className="font-medium">{p.question}</div>
                <div className="text-[var(--text-muted)] text-xs">
                  {p.why_it_matters} · expects: {p.expected_data_source}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

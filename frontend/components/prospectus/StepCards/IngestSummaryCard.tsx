import type { IngestStepOutput } from "@/lib/api";

function fmtMoney(n: number | null): string {
  if (n === null || n === undefined) return "—";
  if (Math.abs(n) >= 1e9) return `$${(n / 1e9).toFixed(2)}B`;
  if (Math.abs(n) >= 1e6) return `$${(n / 1e6).toFixed(2)}M`;
  return `$${n.toLocaleString()}`;
}

export function IngestSummaryCard({ ingest }: { ingest: IngestStepOutput }) {
  return (
    <section className="border border-[var(--border)] rounded-lg p-5 bg-[var(--surface)]">
      <h2 className="text-xl font-semibold mb-3">S-1 ingest</h2>
      <p className="text-sm text-[var(--text-muted)] mb-3">
        Form {ingest.form_type} · CIK {ingest.issuer_cik}
        {ingest.proposed_ticker && <> · proposed ticker {ingest.proposed_ticker}</>}
      </p>
      <a href={ingest.primary_document_url} target="_blank" rel="noopener noreferrer"
         className="text-blue-400 hover:underline text-sm">
        Open primary document ↗
      </a>

      <h3 className="text-sm font-semibold mt-4 mb-1">Extracted sections</h3>
      <ul className="text-sm space-y-0.5">
        {ingest.sections.map((s) => (
          <li key={s.section_key} className="flex justify-between border-b border-[var(--border)] py-1">
            <span className="text-[var(--text)]">{s.heading}</span>
            <span className="text-[var(--text-muted)]">{s.char_count.toLocaleString()} chars</span>
          </li>
        ))}
      </ul>

      {ingest.financials.annual.length > 0 && (
        <>
          <h3 className="text-sm font-semibold mt-4 mb-1">Annual financials</h3>
          <table className="w-full text-sm">
            <thead className="text-xs uppercase text-[var(--text-muted)]">
              <tr>
                <th className="text-left py-1">Period</th>
                <th className="text-right py-1">Revenue</th>
                <th className="text-right py-1">Op Income</th>
                <th className="text-right py-1">Net Income</th>
              </tr>
            </thead>
            <tbody>
              {ingest.financials.annual.map((r) => (
                <tr key={r.period_label} className="border-t border-[var(--border)]">
                  <td className="py-1">{r.period_label}</td>
                  <td className="py-1 text-right">{fmtMoney(r.revenue)}</td>
                  <td className="py-1 text-right">{fmtMoney(r.operating_income)}</td>
                  <td className="py-1 text-right">{fmtMoney(r.net_income)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </section>
  );
}

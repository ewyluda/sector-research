"use client";

import { useEffect, useState } from "react";
import { prospectusApi, type ProspectusReport } from "@/lib/api";
import { IngestSummaryCard } from "./StepCards/IngestSummaryCard";
import { RelationshipsCard } from "./StepCards/RelationshipsCard";
import { CategoryCard } from "./StepCards/CategoryCard";
import { ThesisCard } from "./StepCards/ThesisCard";

export function ProspectusReportView({ reportId }: { reportId: string }) {
  const [report, setReport] = useState<ProspectusReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    prospectusApi
      .get(reportId)
      .then((r) => { if (alive) setReport(r); })
      .catch((e) => { if (alive) setError(e instanceof Error ? e.message : String(e)); });

    const es = new EventSource(prospectusApi.streamUrl(reportId));
    es.onmessage = async (evt) => {
      try {
        const parsed = JSON.parse(evt.data);
        if (parsed.type === "step_complete" || parsed.type === "prospectus_complete") {
          const fresh = await prospectusApi.get(reportId);
          if (alive) setReport(fresh);
        }
        if (parsed.type === "prospectus_complete" || parsed.type === "prospectus_failed") {
          es.close();
        }
      } catch {
        // ignore malformed events
      }
    };
    es.onerror = () => es.close();
    return () => { alive = false; es.close(); };
  }, [reportId]);

  if (error) {
    return (
      <div className="mx-auto max-w-4xl p-6">
        <div className="p-4 bg-red-950 border border-red-800 rounded-md text-red-300 text-sm">
          {error}
        </div>
      </div>
    );
  }
  if (!report) {
    return <div className="mx-auto max-w-4xl p-6 text-[var(--text-muted)]">Loading…</div>;
  }

  const { step_outputs: s, issuer_name, accession_number, status } = report;
  const categoryNames = s.categories ? Object.keys(s.categories.results) : [];

  const promoteHref = report.proposed_ticker
    ? `/pipeline/new?ticker=${encodeURIComponent(report.proposed_ticker)}${report.theme_id ? `&theme_id=${encodeURIComponent(report.theme_id)}` : ""}`
    : null;

  return (
    <div className="min-h-screen bg-[var(--bg)]">
      <div className="mx-auto max-w-5xl p-6 space-y-6">
        <header className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl font-semibold text-[var(--text)]">{issuer_name}</h1>
            <p className="text-[var(--text-muted)] text-sm mt-1">
              {accession_number} · status: {status}
            </p>
          </div>
          {promoteHref && status === "completed" && (
            <a
              href={promoteHref}
              className="text-sm px-3 py-1.5 rounded-md border border-[var(--border)] hover:bg-[var(--surface)] whitespace-nowrap"
            >
              Promote to research run →
            </a>
          )}
        </header>

        {s.thesis && <ThesisCard thesis={s.thesis} />}
        {s.ingest && <IngestSummaryCard ingest={s.ingest} />}
        {s.relationships && <RelationshipsCard rel={s.relationships} />}

        {categoryNames.length > 0 && (
          <section className="space-y-4">
            <h2 className="text-xl font-semibold">Category analyses</h2>
            {categoryNames.map((name) => (
              <CategoryCard key={name} result={s.categories!.results[name]} />
            ))}
            {s.categories && Object.keys(s.categories.failures).length > 0 && (
              <div className="p-3 bg-red-950 border border-red-800 rounded-md text-red-300 text-sm">
                <div className="font-medium mb-1">Category failures</div>
                <ul className="list-disc pl-5 space-y-0.5">
                  {Object.entries(s.categories.failures).map(([cat, err]) => (
                    <li key={cat}><span className="font-medium">{cat}:</span> {err}</li>
                  ))}
                </ul>
              </div>
            )}
          </section>
        )}
      </div>
    </div>
  );
}

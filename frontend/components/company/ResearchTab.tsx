"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { pipeline } from "@/lib/api";
import type { RunSummary, ReportResponse } from "@/lib/api";
import { DeepDiveDashboard } from "@/components/deep-dive/DeepDiveDashboard";
import { ReportHeader } from "@/components/deep-dive/ReportHeader";
import { reportToDashboardProps } from "@/lib/reportProps";
import { EmptyState } from "./EmptyState";

export function ResearchTab({ ticker }: { ticker: string }) {
  const lens = useSearchParams().get("lens");
  const [runs, setRuns] = useState<RunSummary[] | null>(null);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [report, setReport] = useState<ReportResponse | null>(null);

  useEffect(() => {
    pipeline
      .list({ status: "completed", limit: 50 })
      .then((all) => {
        const mine = all.filter((r) => r.ticker?.toUpperCase() === ticker.toUpperCase());
        setRuns(mine);
        const preferred =
          (lens && mine.find((r) => r.theme_id === lens)) || mine[0];
        setActiveRunId(preferred?.id ?? null);
        setReport(null);
      })
      .catch(() => setRuns([]));
  }, [ticker, lens]);

  useEffect(() => {
    if (!activeRunId) return;
    pipeline
      .report(activeRunId)
      .then(setReport)
      .catch(() => setReport(null));
  }, [activeRunId]);

  if (runs === null) {
    return <div className="p-6 text-[var(--text-muted)]">Loading research…</div>;
  }
  if (runs.length === 0) {
    return (
      <EmptyState
        title="No research yet"
        message="Run the due-diligence pipeline to generate a deep-dive report for this company."
        cta={{ href: `/pipeline/new?ticker=${ticker}`, label: "Run pipeline →" }}
      />
    );
  }

  const props = report ? reportToDashboardProps(report) : null;

  return (
    <div className="space-y-4">
      {runs.length > 1 && (
        <div className="flex items-center gap-2">
          <label className="text-sm text-[var(--text-muted)]">Run:</label>
          <select
            value={activeRunId ?? ""}
            onChange={(e) => setActiveRunId(e.target.value)}
            className="rounded-md border border-[var(--border)] bg-[var(--surface-alt)] px-2 py-1 text-sm text-[var(--text)]"
          >
            {runs.map((r) => (
              <option key={r.id} value={r.id}>
                {r.created_at ? new Date(r.created_at).toLocaleDateString() : "—"}
                {r.theme_name ? ` · ${r.theme_name}` : ""}
                {r.thesis_status ? ` · ${r.thesis_status}` : ""}
              </option>
            ))}
          </select>
        </div>
      )}
      {props && activeRunId && (
        <>
          <ReportHeader
            financials={props.financials}
            quickScreen={props.quickScreen}
            convictionScore={props.convictionScore}
            ticker={ticker}
            runId={activeRunId}
            isLive={false}
            runStatus="completed"
          />
          <DeepDiveDashboard
            ticker={ticker}
            themeId={props.themeId}
            financials={props.financials}
            categories={props.categories}
            scores={props.scores}
            isLive={false}
            transcriptAnalysis={props.transcriptAnalysis}
            xSignalVelocity={props.xSignalVelocity ?? undefined}
            edgarFacts={props.edgarFacts}
          />
        </>
      )}
    </div>
  );
}

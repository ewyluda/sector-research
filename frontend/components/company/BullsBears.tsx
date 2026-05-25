"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { pipeline } from "@/lib/api";
import type { RunSummary, ReportResponse, ThesisStructured, ThesisPoint } from "@/lib/api";
import { EmptyState } from "./EmptyState";

export function BullsBears({ ticker }: { ticker: string }) {
  const lens = useSearchParams().get("lens");
  const [hasRun, setHasRun] = useState<boolean | null>(null);
  const [thesis, setThesis] = useState<ThesisStructured | null>(null);

  useEffect(() => {
    let alive = true;
    pipeline
      .list({ status: "completed", ticker, limit: 50 })
      .then((runs: RunSummary[]) => {
        if (!alive) return;
        const preferred = (lens && runs.find((r) => r.theme_id === lens)) || runs[0];
        if (!preferred) {
          setHasRun(false);
          setThesis(null);
          return;
        }
        setHasRun(true);
        return pipeline.report(preferred.id).then((rep: ReportResponse) => {
          if (alive)
            setThesis(
              (rep.phases.thesis?.structured as unknown as ThesisStructured) ?? null,
            );
        });
      })
      .catch(() => {
        if (alive) {
          setHasRun(false);
          setThesis(null);
        }
      });
    return () => {
      alive = false;
    };
  }, [ticker, lens]);

  if (hasRun === null) {
    return <div className="p-4 text-sm text-[var(--text-muted)]">Loading thesis…</div>;
  }
  if (!hasRun) {
    return (
      <EmptyState
        title="No thesis yet"
        message="Run the due-diligence pipeline to generate the bull and bear case."
        cta={{ href: `/pipeline/new?ticker=${ticker}`, label: "Run pipeline →" }}
      />
    );
  }

  const bulls: ThesisPoint[] = thesis?.bull_case ?? [];
  const bears: ThesisPoint[] = thesis?.bear_case ?? [];

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
      <Column title="Bulls say" tone="var(--success,#16a34a)" points={bulls} />
      <Column title="Bears say" tone="var(--error,#dc2626)" points={bears} />
    </div>
  );
}

function Column({
  title,
  tone,
  points,
}: {
  title: string;
  tone: string;
  points: ThesisPoint[];
}) {
  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-3">
      <h3 className="mb-2 text-sm font-semibold" style={{ color: tone }}>
        {title}
      </h3>
      {points.length === 0 ? (
        <p className="text-xs text-[var(--text-muted)]">—</p>
      ) : (
        <ul className="space-y-2">
          {points.map((p, i) => (
            <li key={i} className="text-sm">
              <span className="font-medium text-[var(--text)]">{p.title}</span>
              {p.evidence && (
                <span className="text-[var(--text-muted)]"> — {p.evidence}</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

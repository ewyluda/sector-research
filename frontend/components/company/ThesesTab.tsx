"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { status, pipeline, questions } from "@/lib/api";
import type { StatusBoardEntry, RunSummary, Question } from "@/lib/api";

export function ThesesTab({ ticker }: { ticker: string }) {
  const lens = useSearchParams().get("lens");
  const [rows, setRows] = useState<StatusBoardEntry[]>([]);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [qs, setQs] = useState<Question[]>([]);

  useEffect(() => {
    let alive = true;
    const up = ticker.toUpperCase();
    status
      .board()
      .then((b) => {
        if (alive) setRows(b.entries.filter((e) => e.ticker.toUpperCase() === up));
      })
      .catch(() => {
        if (alive) setRows([]);
      });
    pipeline
      .list({ ticker, limit: 50 })
      .then((all) => {
        if (alive) setRuns(all);
      })
      .catch(() => {
        if (alive) setRuns([]);
      });
    questions
      .list({ ticker: up })
      .then((r) => {
        if (alive) setQs(r.questions);
      })
      .catch(() => {
        if (alive) setQs([]);
      });
    return () => {
      alive = false;
    };
  }, [ticker]);

  return (
    <div className="space-y-6">
      <section>
        <h3 className="mb-2 text-sm font-semibold text-[var(--text)]">Theses tracking {ticker}</h3>
        {rows.length === 0 ? (
          <p className="text-sm text-[var(--text-muted)]">Not tracked in any theme yet.</p>
        ) : (
          <div className="space-y-2">
            {rows.map((e) => (
              <div
                key={e.run_id}
                className={`flex items-center justify-between rounded-md border px-3 py-2 ${
                  lens && e.theme_id === lens
                    ? "border-[var(--primary)] bg-[var(--accent-bg)]"
                    : "border-[var(--border)] bg-[var(--surface)]"
                }`}
              >
                <div className="text-sm">
                  <span className="font-medium text-[var(--text)]">{e.theme_name}</span>
                  <span className="ml-2 text-xs text-[var(--text-muted)]">{e.thesis_status}</span>
                </div>
                <div className="flex items-center gap-3 text-xs text-[var(--text-muted)]">
                  <span className="uppercase">{e.health}</span>
                  <span>
                    kill: {e.kill_criteria_summary.triggered}/{e.kill_criteria_summary.total} triggered
                  </span>
                  <Link
                    href={`/pipeline/${e.run_id}`}
                    className="text-[var(--primary)] hover:underline"
                  >
                    run →
                  </Link>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <section>
        <h3 className="mb-2 text-sm font-semibold text-[var(--text)]">Run history</h3>
        {runs.length === 0 ? (
          <p className="text-sm text-[var(--text-muted)]">No runs yet.</p>
        ) : (
          <ul className="space-y-1 text-sm">
            {runs.map((r) => (
              <li key={r.id} className="flex items-center gap-3">
                <span className="text-[var(--text-muted)]">
                  {r.created_at ? new Date(r.created_at).toLocaleDateString() : "—"}
                </span>
                <span className="text-[var(--text)]">{r.theme_name ?? "—"}</span>
                <span className="text-xs text-[var(--text-muted)]">{r.thesis_status ?? r.status}</span>
                <Link href={`/pipeline/${r.id}`} className="text-[var(--primary)] hover:underline">
                  open →
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <h3 className="mb-2 text-sm font-semibold text-[var(--text)]">Open questions</h3>
        {qs.length === 0 ? (
          <p className="text-sm text-[var(--text-muted)]">No open questions.</p>
        ) : (
          <ul className="list-disc space-y-1 pl-5 text-sm text-[var(--text)]">
            {qs.map((q) => (
              <li key={q.id}>{q.question_text}</li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

/**
 * Page — /workspace
 *
 * Fleet-wide recent workspace runs index.
 * Server component fetches workspace.recent() and displays a table of runs.
 */

import Link from "next/link";
import { workspaceApi, type WorkspaceRun } from "@/lib/api";
import { VerdictBadge } from "@/components/workspace/VerdictBadge";
import { RetryRunButton } from "@/components/workspace/RetryRunButton";

export const dynamic = "force-dynamic";

function VersionBadge({ before, after }: { before: number; after: number | null }) {
  if (after === null) {
    return <span className="text-[var(--text-muted)]">v{before} (no save)</span>;
  }
  return (
    <span className="text-sm">
      <span className="text-[var(--text-muted)]">v{before}</span>
      <span className="text-[var(--text-muted)] mx-1">→</span>
      <span className="font-medium">v{after}</span>
    </span>
  );
}

export default async function WorkspaceIndex() {
  let runs: WorkspaceRun[] = [];
  let error: string | null = null;

  try {
    runs = await workspaceApi.recent();
  } catch (e) {
    error = e instanceof Error ? e.message : "Failed to fetch workspace runs";
  }

  return (
    <div className="min-h-screen bg-[var(--bg)]">
      <div className="mx-auto max-w-5xl p-6 space-y-6">
        <div>
          <h1 className="text-3xl font-semibold text-[var(--text)]">Workspace Runs</h1>
          <p className="text-[var(--text-muted)] text-sm mt-2">
            Recent model reconciliations and iteration history
          </p>
        </div>

        {error && (
          <div className="p-4 bg-red-950 border border-red-800 rounded-md text-red-300 text-sm">
            {error}
          </div>
        )}

        {runs.length === 0 && !error && (
          <div className="flex flex-col items-center justify-center p-12 border border-[var(--border)] rounded-lg bg-[var(--surface-alt)]">
            <p className="text-[var(--text-muted)] text-sm">No workspace runs yet.</p>
            <p className="text-[var(--text-muted)] text-xs mt-2">
              Trigger a workspace run from a completed research pipeline or status board.
            </p>
          </div>
        )}

        {runs.length > 0 && (
          <div className="overflow-x-auto border border-[var(--border)] rounded-lg bg-[var(--surface)]">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[var(--border)] bg-[var(--surface-alt)]">
                  <th className="px-6 py-3 text-left text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wide">
                    Ticker
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wide">
                    Verdict
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wide">
                    Model Version
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wide">
                    Status
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wide">
                    When
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--border)]">
                {runs.map((run) => {
                  const createdDate = new Date(run.created_at);
                  const timeStr = createdDate.toLocaleString("en-US", {
                    month: "short",
                    day: "numeric",
                    hour: "2-digit",
                    minute: "2-digit",
                  });

                  const statusColor: Record<string, string> = {
                    running: "text-blue-400",
                    completed: "text-emerald-400",
                    partial: "text-amber-400",
                    failed: "text-red-400",
                  };
                  const statusClass = statusColor[run.status] || "text-[var(--text-muted)]";

                  return (
                    <tr key={run.id} className="hover:bg-[var(--surface-alt)] transition-colors">
                      <td className="px-6 py-4">
                        <Link
                          href={`/workspace/${run.id}`}
                          className="font-semibold text-[var(--primary)] hover:text-[var(--primary-lt)] transition-colors"
                        >
                          {run.ticker}
                        </Link>
                      </td>
                      <td className="px-6 py-4">
                        <VerdictBadge verdict={run.verdict} />
                      </td>
                      <td className="px-6 py-4">
                        <VersionBadge before={run.ticker_model_version_before} after={run.ticker_model_version_after} />
                      </td>
                      <td className={`px-6 py-4 font-medium capitalize ${statusClass}`}>
                        <span className="inline-flex items-center gap-2">
                          {run.status}
                          {run.status === "failed" && <RetryRunButton ticker={run.ticker} />}
                        </span>
                      </td>
                      <td className="px-6 py-4 text-[var(--text-muted)] text-xs">{timeStr}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

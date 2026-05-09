"use client";

import type { ChallengeOutput } from "@/lib/api";
import { MarkdownProse } from "@/components/deep-dive/renderMarkdown";
import { VerdictBadge } from "../VerdictBadge";

const STATUS_COLOR: Record<string, string> = {
  armed: "text-[var(--text-muted)]",
  triggered: "text-[var(--error)]",
  resolved: "text-[var(--success)]",
  still_pending: "text-[var(--text-muted)]",
  missed: "text-[var(--error)]",
};

export function ChallengeCard({ output }: { output: ChallengeOutput }) {
  return (
    <div className="space-y-4 mt-2">
      <MarkdownProse text={output.stress_test_summary} className="text-sm text-[var(--text)] space-y-2" />

      {output.kill_criterion_writes.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-semibold text-[var(--text)]">Kill Criteria</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-[var(--text)]">
              <thead>
                <tr className="border-b border-[var(--border)]">
                  <th className="text-left py-1 px-2 font-semibold text-[var(--text-muted)]">#</th>
                  <th className="text-left py-1 px-2 font-semibold text-[var(--text-muted)]">Status</th>
                  <th className="text-left py-1 px-2 font-semibold text-[var(--text-muted)]">Note</th>
                </tr>
              </thead>
              <tbody>
                {output.kill_criterion_writes.map((kc, i) => (
                  <tr key={i} className="border-b border-[var(--border)]">
                    <td className="py-1 px-2">{kc.ordinal}</td>
                    <td className={`py-1 px-2 font-medium ${STATUS_COLOR[kc.status]}`}>
                      {kc.status.replace(/_/g, " ")}
                    </td>
                    <td className="py-1 px-2 text-[var(--text-muted)]">{kc.note || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {output.catalyst_updates.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-semibold text-[var(--text)]">Catalyst Updates</h3>
          <ul className="space-y-1">
            {output.catalyst_updates.map((cu, i) => (
              <li key={i} className="text-sm flex gap-2 items-start">
                <span className={`text-xs uppercase font-semibold ${STATUS_COLOR[cu.new_status]}`}>
                  {cu.new_status.replace(/_/g, " ")}
                </span>
                <span className="text-[var(--text)] flex-1">
                  <span className="text-[var(--text-muted)]">{cu.catalyst_id}</span>
                  {cu.note && <span className="block text-xs text-[var(--text-muted)] mt-0.5">{cu.note}</span>}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {output.proposed_verdict && (
        <div className="flex items-center gap-3 pt-2 border-t border-[var(--border)]">
          <span className="text-sm text-[var(--text-muted)]">Proposed verdict:</span>
          <VerdictBadge verdict={output.proposed_verdict} />
        </div>
      )}
    </div>
  );
}

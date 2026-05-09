"use client";

import type { ChallengeOutput } from "@/lib/api";
import { MarkdownProse } from "@/components/deep-dive/renderMarkdown";
import { VerdictBadge } from "../VerdictBadge";

const STATUS_COLOR: Record<string, string> = {
  armed: "text-slate-400",
  triggered: "text-red-400",
  resolved: "text-emerald-400",
  still_pending: "text-slate-400",
  missed: "text-red-400",
};

export function ChallengeCard({ output }: { output: ChallengeOutput }) {
  return (
    <div className="space-y-4 mt-2">
      <MarkdownProse text={output.stress_test_summary} className="text-sm text-slate-300 space-y-2" />

      {output.kill_criterion_writes.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-semibold text-slate-200">Kill Criteria</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-slate-300">
              <thead>
                <tr className="border-b border-slate-700">
                  <th className="text-left py-1 px-2 font-semibold text-slate-400">#</th>
                  <th className="text-left py-1 px-2 font-semibold text-slate-400">Status</th>
                  <th className="text-left py-1 px-2 font-semibold text-slate-400">Note</th>
                </tr>
              </thead>
              <tbody>
                {output.kill_criterion_writes.map((kc, i) => (
                  <tr key={i} className="border-b border-slate-800">
                    <td className="py-1 px-2">{kc.ordinal}</td>
                    <td className={`py-1 px-2 font-medium ${STATUS_COLOR[kc.status]}`}>
                      {kc.status.replace(/_/g, " ")}
                    </td>
                    <td className="py-1 px-2 text-slate-400">{kc.note || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {output.catalyst_updates.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-semibold text-slate-200">Catalyst Updates</h3>
          <ul className="space-y-1">
            {output.catalyst_updates.map((cu, i) => (
              <li key={i} className="text-sm flex gap-2 items-start">
                <span className={`text-xs uppercase font-semibold ${STATUS_COLOR[cu.new_status]}`}>
                  {cu.new_status.replace(/_/g, " ")}
                </span>
                <span className="text-slate-300 flex-1">
                  <span className="text-slate-400">{cu.catalyst_id}</span>
                  {cu.note && <span className="block text-xs text-slate-400 mt-0.5">{cu.note}</span>}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {output.proposed_verdict && (
        <div className="flex items-center gap-3 pt-2 border-t border-slate-700">
          <span className="text-sm text-slate-400">Proposed verdict:</span>
          <VerdictBadge verdict={output.proposed_verdict} />
        </div>
      )}
    </div>
  );
}

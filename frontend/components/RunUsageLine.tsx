"use client";

import { useEffect, useState } from "react";
import { pipeline, type RunUsage } from "@/lib/api";

/** "LLM $3.41 · 38 calls · 8.1 min · 22% cached" for a finished run. Renders
 *  nothing for runs recorded before llm_calls existed. */
export function RunUsageLine({ runId }: { runId: string }) {
  const [usage, setUsage] = useState<RunUsage | null>(null);

  useEffect(() => {
    let alive = true;
    pipeline.usage(runId).then((u) => { if (alive) setUsage(u); }).catch(() => {});
    return () => { alive = false; };
  }, [runId]);

  if (!usage || usage.calls === 0) return null;
  const parts = [
    `LLM $${usage.cost_usd.toFixed(2)}${usage.unpriced_calls ? "+" : ""}`,
    `${usage.calls} calls`,
    usage.wall_clock_s != null ? `${(usage.wall_clock_s / 60).toFixed(1)} min` : null,
    usage.cache_hit_rate != null ? `${Math.round(usage.cache_hit_rate * 100)}% cached` : null,
  ].filter(Boolean);
  const title = usage.by_phase
    .map((p) => `${p.phase}: $${p.cost_usd.toFixed(2)} over ${p.calls} calls`)
    .join("\n");
  return (
    <span className="text-xs text-[var(--color-text-faint)] tabular-nums px-2" title={title}>
      {parts.join(" · ")}
    </span>
  );
}

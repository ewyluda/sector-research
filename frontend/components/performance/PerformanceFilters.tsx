"use client";

import { useRouter, useSearchParams } from "next/navigation";
import type { Benchmark, SnapshotOffset, SourceType, Window } from "@/lib/api";

const WINDOWS: Window[] = ["30d", "90d", "1y", "all"];
const OFFSETS: SnapshotOffset[] = ["1d", "1w", "1m", "3m", "6m"];
const BENCHMARKS: Benchmark[] = ["spy", "sector", "theme_basket"];
const SOURCES: ("all" | SourceType)[] = ["all", "research_run", "workspace_run"];

export function PerformanceFilters({
  showSuperseded,
  activeOffset,
}: {
  showSuperseded: boolean;
  // The offset the page actually resolved (URL param or largest populated
  // default) — deriving from the URL alone would wrongly highlight 3m on first load.
  activeOffset: SnapshotOffset;
}) {
  const router = useRouter();
  const sp = useSearchParams();

  const current = {
    window: (sp.get("window") as Window) ?? "90d",
    snapshot_offset: activeOffset,
    benchmark: (sp.get("benchmark") as Benchmark) ?? "spy",
    source_type: (sp.get("source_type") as "all" | SourceType) ?? "all",
  };

  function set(key: string, value: string) {
    const params = new URLSearchParams(sp.toString());
    params.set(key, value);
    router.push(`/performance?${params.toString()}`);
  }

  function toggleSuperseded() {
    const params = new URLSearchParams(sp.toString());
    if (showSuperseded) {
      params.delete("superseded");
    } else {
      params.set("superseded", "1");
    }
    router.push(`/performance?${params.toString()}`);
  }

  return (
    <div className="flex flex-wrap gap-3 p-3 border-b border-[var(--border)]" data-print-hide="true">
      <FilterGroup label="Window" options={WINDOWS} value={current.window} onChange={(v) => set("window", v)} />
      <FilterGroup label="Offset" options={OFFSETS} value={current.snapshot_offset} onChange={(v) => set("snapshot_offset", v)} />
      <FilterGroup label="Benchmark" options={BENCHMARKS} value={current.benchmark} onChange={(v) => set("benchmark", v)} format={fmtBenchmark} />
      <FilterGroup label="Source" options={SOURCES} value={current.source_type} onChange={(v) => set("source_type", v)} format={fmtSource} />
      <label className="flex items-center gap-1 text-sm cursor-pointer select-none">
        <input
          type="checkbox"
          checked={showSuperseded}
          onChange={toggleSuperseded}
          className="accent-[var(--primary)]"
        />
        <span className="text-[var(--text-muted)]">Show superseded</span>
      </label>
    </div>
  );
}

function fmtBenchmark(v: string) {
  return v === "spy" ? "SPY" : v === "sector" ? "Sector ETF" : "Theme basket";
}
function fmtSource(v: string) {
  return v === "all" ? "All" : v === "research_run" ? "Research" : "Workspace";
}

function FilterGroup<T extends string>({
  label, options, value, onChange, format,
}: {
  label: string;
  options: readonly T[];
  value: T;
  onChange: (v: T) => void;
  format?: (v: T) => string;
}) {
  return (
    <div className="flex items-center gap-1 text-sm">
      <span className="text-[var(--text-muted)] mr-1">{label}:</span>
      {options.map((opt) => (
        <button
          key={opt}
          type="button"
          onClick={() => onChange(opt)}
          className={
            "px-2 py-1 rounded " +
            (opt === value
              ? "bg-[var(--primary)] text-white"
              : "bg-[var(--surface)] text-[var(--text)] hover:bg-[var(--surface-2)]")
          }
        >
          {format ? format(opt) : opt}
        </button>
      ))}
    </div>
  );
}

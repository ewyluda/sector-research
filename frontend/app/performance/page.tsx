import { outcomesApi } from "@/lib/api";
import { PerformanceFilters } from "@/components/performance/PerformanceFilters";
import { HeroBand } from "@/components/performance/HeroBand";
import { ByVerdictTable } from "@/components/performance/ByVerdictTable";
import { ByThemeTable } from "@/components/performance/ByThemeTable";
import { BySignalBucketPanel } from "@/components/performance/BySignalBucketPanel";
import { OutcomeList } from "@/components/performance/OutcomeList";
import type { Benchmark, SnapshotOffset, SourceType, Window } from "@/lib/api";

interface PageProps {
  searchParams: Promise<{
    window?: Window;
    snapshot_offset?: SnapshotOffset;
    benchmark?: Benchmark;
    source_type?: SourceType | "all";
    theme_filter?: string;
  }>;
}

export default async function PerformancePage({ searchParams }: PageProps) {
  const sp = await searchParams;
  const window = sp.window ?? "90d";
  const snapshotOffset = sp.snapshot_offset ?? "3m";
  const benchmark = sp.benchmark ?? "spy";
  const sourceType = sp.source_type ?? "all";

  const [summary, outcomes] = await Promise.all([
    outcomesApi.getSummary({
      themeId: sp.theme_filter,
      window,
      snapshotOffset,
      benchmark,
      sourceType: sourceType === "all" ? undefined : (sourceType as SourceType),
    }),
    outcomesApi.list({
      themeId: sp.theme_filter,
      sourceType: sourceType === "all" ? undefined : (sourceType as SourceType),
      limit: 200,
    }),
  ]);

  return (
    <main id="main-content" className="min-h-screen bg-[var(--bg)] text-[var(--text)]">
      <header className="px-4 py-3 border-b border-[var(--border)]">
        <h1 className="text-lg font-semibold">Performance</h1>
      </header>
      <PerformanceFilters />
      <HeroBand summary={summary} />
      <ByVerdictTable summary={summary} />
      <ByThemeTable summary={summary} />
      <BySignalBucketPanel summary={summary} />
      <OutcomeList outcomes={outcomes} />
    </main>
  );
}

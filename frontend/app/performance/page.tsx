import { outcomesApi } from "@/lib/api";
import { PerformanceFilters } from "@/components/performance/PerformanceFilters";
import { HeroBand } from "@/components/performance/HeroBand";
import { ByVerdictTable } from "@/components/performance/ByVerdictTable";
import { ByThemeTable } from "@/components/performance/ByThemeTable";
import { BySignalBucketPanel } from "@/components/performance/BySignalBucketPanel";
import { OutcomeList } from "@/components/performance/OutcomeList";
import { TradeJournalSection } from "@/components/journal/TradeJournalSection";
import type { Benchmark, SnapshotOffset, SourceType, Window } from "@/lib/api";

interface PageProps {
  searchParams: Promise<{
    window?: Window;
    snapshot_offset?: SnapshotOffset;
    benchmark?: Benchmark;
    source_type?: SourceType | "all";
    theme_filter?: string;
    superseded?: string;
  }>;
}

const OFFSET_PRIORITY: SnapshotOffset[] = ["6m", "3m", "1m", "1w", "1d"];

export default async function PerformancePage({ searchParams }: PageProps) {
  const sp = await searchParams;
  const window = sp.window ?? "90d";
  const benchmark = sp.benchmark ?? "spy";
  const sourceType = sp.source_type ?? "all";
  const showSuperseded = sp.superseded === "1";

  // Kick off outcomes fetch immediately — it depends on nothing below.
  const outcomesPromise = outcomesApi.list({
    themeId: sp.theme_filter,
    sourceType: sourceType === "all" ? undefined : (sourceType as SourceType),
    superseded: showSuperseded ? "all" : "false",
    limit: 200,
  });

  // Resolve snapshot_offset: URL param wins; otherwise discover from a summary call.
  let snapshotOffset: SnapshotOffset;
  let summary;

  if (sp.snapshot_offset) {
    snapshotOffset = sp.snapshot_offset;
    summary = await outcomesApi.getSummary({
      themeId: sp.theme_filter,
      window,
      snapshotOffset,
      benchmark,
      sourceType: sourceType === "all" ? undefined : (sourceType as SourceType),
    });
  } else {
    // No URL offset: fetch summary with "1m" placeholder to learn populated offsets,
    // then re-fetch only if a better offset exists. One extra round-trip on first paint;
    // URL params avoid it on subsequent filter changes.
    const discoverySummary = await outcomesApi.getSummary({
      themeId: sp.theme_filter,
      window,
      snapshotOffset: "1m",
      benchmark,
      sourceType: sourceType === "all" ? undefined : (sourceType as SourceType),
    });
    snapshotOffset =
      OFFSET_PRIORITY.find((o) => discoverySummary.populated_offsets.includes(o)) ?? "1m";

    if (snapshotOffset === "1m") {
      summary = discoverySummary;
    } else {
      summary = await outcomesApi.getSummary({
        themeId: sp.theme_filter,
        window,
        snapshotOffset,
        benchmark,
        sourceType: sourceType === "all" ? undefined : (sourceType as SourceType),
      });
    }
  }

  const outcomes = await outcomesPromise;

  return (
    <main id="main-content" className="min-h-screen bg-[var(--bg)] text-[var(--text)]">
      <header className="px-4 py-3 border-b border-[var(--border)]">
        <h1 className="text-lg font-semibold">Performance</h1>
      </header>
      <PerformanceFilters showSuperseded={showSuperseded} activeOffset={snapshotOffset} />
      <HeroBand summary={summary} />
      <ByVerdictTable summary={summary} />
      <ByThemeTable summary={summary} />
      <BySignalBucketPanel summary={summary} />
      <OutcomeList outcomes={outcomes} />
      <TradeJournalSection />
    </main>
  );
}

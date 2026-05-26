import type {
  ReportResponse,
  CategoryOutput,
  CuratedFinancials,
  DeepDiveCategoryStructured,
  TranscriptAnalysis,
  XSignalVelocity,
  EdgarFacts,
  QuickScreenStructured,
} from "./api";

export interface DashboardProps {
  financials: CuratedFinancials | null;
  categories: Record<string, CategoryOutput | null>;
  scores: Record<string, number>;
  transcriptAnalysis: TranscriptAnalysis | null;
  xSignalVelocity: XSignalVelocity | null;
  edgarFacts: EdgarFacts;
  convictionScore: number | null;
  quickScreen: QuickScreenStructured | null;
  themeId?: string;
}

export function reportToDashboardProps(report: ReportResponse): DashboardProps {
  const deep = report.phases.deep_dive;
  const rawCats = deep?.categories ?? {};
  const categories: Record<string, CategoryOutput | null> = {};
  for (const [key, val] of Object.entries(rawCats)) {
    const v = val as CategoryOutput & { __type__?: string; structured?: unknown };
    if (v.__type__ === "CategoryError") {
      categories[key] = null;
    } else {
      categories[key] = {
        score: v.score ?? 0,
        content: "",
        key_findings: v.key_findings ?? [],
        citations: [],
        structured: (v.structured as DeepDiveCategoryStructured) ?? undefined,
      };
    }
  }

  return {
    financials: deep?.curated_financials ?? null,
    categories,
    scores: report.scores ?? {},
    transcriptAnalysis: deep?.transcript_analysis ?? null,
    xSignalVelocity: report.x_signal_velocity ?? null,
    edgarFacts: deep?.edgar_facts ?? {},
    convictionScore: report.conviction_score ?? null,
    quickScreen: (report.phases.quick_screen?.structured as QuickScreenStructured) ?? null,
    themeId: report.theme_id ?? undefined,
  };
}

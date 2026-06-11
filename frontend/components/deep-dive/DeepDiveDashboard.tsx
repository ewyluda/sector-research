import { useMemo } from "react";
import type { CuratedFinancials, CategoryOutput, DeepDiveCategoryStructured, TranscriptAnalysis, XSignalVelocity, EdgarFacts } from "@/lib/api";
import { OverviewBanner } from "./OverviewBanner";
import { FinancialHealth } from "./sections/FinancialHealth";
import { SupplyChainEcosystem } from "./sections/SupplyChainEcosystem";
import { Competition } from "./sections/Competition";
import { GrowthEarnings } from "./sections/GrowthEarnings";
import { TechnicalMarket } from "./sections/TechnicalMarket";
import { BusinessQuality } from "./sections/BusinessQuality";
import { MacroRegime } from "./sections/MacroRegime";
import { RiskAssessment } from "./sections/RiskAssessment";
import { WhatChangedPanel } from "./sections/WhatChangedPanel";
import { ManagementGovernance } from "./sections/ManagementGovernance";
import { SentimentNarrative } from "./sections/SentimentNarrative";
import { FutureDurability } from "./sections/FutureDurability";
import { CrossCategoryCorrelation } from "./sections/CrossCategoryCorrelation";
import { QuantFingerprint } from "./sections/QuantFingerprint";
import { SectionNav } from "./SectionNav";
import { normalizeScoreKeys } from "./scoreKeys";

export interface DeepDiveDashboardProps {
  ticker: string;
  themeId?: string;
  financials: CuratedFinancials | null;
  categories: Record<string, CategoryOutput | null>;
  scores: Record<string, number>;
  isLive?: boolean;
  transcriptAnalysis?: TranscriptAnalysis | null;
  xSignalVelocity?: XSignalVelocity | null;
  edgarFacts?: EdgarFacts;
}

function getStructured(cat: CategoryOutput | null): DeepDiveCategoryStructured | null {
  if (!cat || !cat.structured) return null;
  return cat.structured as DeepDiveCategoryStructured;
}

function getScore(cat: CategoryOutput | null, scores: Record<string, number>, key: string): number | null {
  return scores[key] ?? cat?.score ?? null;
}

export function DeepDiveDashboard({ ticker, themeId, financials, categories: rawCategories, scores: rawScores, isLive, transcriptAnalysis, xSignalVelocity, edgarFacts }: DeepDiveDashboardProps) {
  const scores = useMemo(() => normalizeScoreKeys(rawScores), [rawScores]);
  const categories = useMemo(() => normalizeScoreKeys(rawCategories), [rawCategories]);

  // Hoist structured/score/fallback derivations so memoized section components
  // receive referentially-stable props and can skip re-renders on SSE events
  // that don't change their category.
  const fhCat = categories["financial_health"] ?? null;
  const fhStructured = useMemo(() => getStructured(fhCat), [fhCat]);
  const fhScore = useMemo(() => getScore(fhCat, scores, "financial_health"), [fhCat, scores]);

  const geCat = categories["growth_earnings"] ?? null;
  const geStructured = useMemo(() => getStructured(geCat), [geCat]);
  const geScore = useMemo(() => getScore(geCat, scores, "growth_earnings"), [geCat, scores]);

  const tmCat = categories["technical_market_structure"] ?? null;
  const tmStructured = useMemo(() => getStructured(tmCat), [tmCat]);
  const tmScore = useMemo(() => getScore(tmCat, scores, "technical_market_structure"), [tmCat, scores]);

  const bqCat = categories["business_quality"] ?? null;
  const bqStructured = useMemo(() => getStructured(bqCat), [bqCat]);
  const bqScore = useMemo(() => getScore(bqCat, scores, "business_quality"), [bqCat, scores]);

  const mrCat = categories["macro_regime"] ?? null;
  const mrStructured = useMemo(() => getStructured(mrCat), [mrCat]);
  const mrScore = useMemo(() => getScore(mrCat, scores, "macro_regime"), [mrCat, scores]);

  const raCat = categories["risk_assessment"] ?? null;
  const raStructured = useMemo(() => getStructured(raCat), [raCat]);
  const raScore = useMemo(() => getScore(raCat, scores, "risk_assessment"), [raCat, scores]);

  const mgCat = categories["management_governance"] ?? null;
  const mgStructured = useMemo(() => getStructured(mgCat), [mgCat]);
  const mgScore = useMemo(() => getScore(mgCat, scores, "management_governance"), [mgCat, scores]);

  const snCat = categories["sentiment_narrative"] ?? null;
  const snStructured = useMemo(() => getStructured(snCat), [snCat]);
  const snScore = useMemo(() => getScore(snCat, scores, "sentiment_narrative"), [snCat, scores]);

  const fdCat = categories["future_durability"] ?? null;
  const fdStructured = useMemo(() => getStructured(fdCat), [fdCat]);
  const fdScore = useMemo(() => getScore(fdCat, scores, "future_durability"), [fdCat, scores]);

  const transcriptAnalysisStable = transcriptAnalysis ?? null;

  return (
  <>
    <SectionNav ticker={ticker} />
    <div className="space-y-6">
        <OverviewBanner financials={financials} scores={scores} />

        {/* Data-Rich */}
        <FinancialHealth
          financials={financials}
          structured={fhStructured}
          score={fhScore}
          fallback={fhCat}
          isLive={isLive}
          edgarFacts={edgarFacts}
        />
        <GrowthEarnings
          financials={financials}
          structured={geStructured}
          score={geScore}
          fallback={geCat}
          isLive={isLive}
          transcriptAnalysis={transcriptAnalysisStable}
          edgarFacts={edgarFacts}
        />
        <TechnicalMarket
          financials={financials}
          structured={tmStructured}
          score={tmScore}
          fallback={tmCat}
          isLive={isLive}
        />

        {/* Cross-Category Correlations */}
        <CrossCategoryCorrelation financials={financials} isLive={isLive} />

        {/* Quant Fingerprint — deterministic scores computed backend-side */}
        <QuantFingerprint financials={financials} />

        {/* Mixed */}
        <BusinessQuality
          financials={financials}
          structured={bqStructured}
          score={bqScore}
          fallback={bqCat}
          isLive={isLive}
          transcriptAnalysis={transcriptAnalysisStable}
        />

        {/* Competition — Item 1 segment / area / competitor table */}
        <Competition ticker={ticker} />

        {/* Supply Chain & Ecosystem — 1-hop relationship graph */}
        <SupplyChainEcosystem ticker={ticker} />
        <MacroRegime
          financials={financials}
          structured={mrStructured}
          score={mrScore}
          fallback={mrCat}
          isLive={isLive}
        />
        <RiskAssessment
          structured={raStructured}
          score={raScore}
          fallback={raCat}
          isLive={isLive}
        />

        <WhatChangedPanel ticker={ticker} />

        {/* Qualitative — 2-column grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <ManagementGovernance
            structured={mgStructured}
            score={mgScore}
            fallback={mgCat}
            isLive={isLive}
            transcriptAnalysis={transcriptAnalysisStable}
          />
          <SentimentNarrative
            structured={snStructured}
            score={snScore}
            fallback={snCat}
            isLive={isLive}
            xSignalVelocity={xSignalVelocity}
            themeId={themeId}
            ticker={ticker}
          />
        </div>
        <FutureDurability
          structured={fdStructured}
          score={fdScore}
          fallback={fdCat}
          isLive={isLive}
        />
    </div>
  </>
  );
}

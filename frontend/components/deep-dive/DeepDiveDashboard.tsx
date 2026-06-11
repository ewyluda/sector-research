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

  // Per-category locals — plain consts are sufficient:
  //   getStructured() is a property lookup (returns an existing reference, no allocation);
  //   getScore() returns a primitive (compared by value in shallow prop compare).
  // The two normalizeScoreKeys useMemos above already guard the only allocating paths.
  const fhCat = categories["financial_health"] ?? null;
  const fhStructured = getStructured(fhCat);
  const fhScore = getScore(fhCat, scores, "financial_health");

  const geCat = categories["growth_earnings"] ?? null;
  const geStructured = getStructured(geCat);
  const geScore = getScore(geCat, scores, "growth_earnings");

  const tmCat = categories["technical_market_structure"] ?? null;
  const tmStructured = getStructured(tmCat);
  const tmScore = getScore(tmCat, scores, "technical_market_structure");

  const bqCat = categories["business_quality"] ?? null;
  const bqStructured = getStructured(bqCat);
  const bqScore = getScore(bqCat, scores, "business_quality");

  const mrCat = categories["macro_regime"] ?? null;
  const mrStructured = getStructured(mrCat);
  const mrScore = getScore(mrCat, scores, "macro_regime");

  const raCat = categories["risk_assessment"] ?? null;
  const raStructured = getStructured(raCat);
  const raScore = getScore(raCat, scores, "risk_assessment");

  const mgCat = categories["management_governance"] ?? null;
  const mgStructured = getStructured(mgCat);
  const mgScore = getScore(mgCat, scores, "management_governance");

  const snCat = categories["sentiment_narrative"] ?? null;
  const snStructured = getStructured(snCat);
  const snScore = getScore(snCat, scores, "sentiment_narrative");

  const fdCat = categories["future_durability"] ?? null;
  const fdStructured = getStructured(fdCat);
  const fdScore = getScore(fdCat, scores, "future_durability");

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

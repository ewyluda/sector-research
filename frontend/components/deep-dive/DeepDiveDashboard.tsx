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
import { ManagementGovernance } from "./sections/ManagementGovernance";
import { SentimentNarrative } from "./sections/SentimentNarrative";
import { FutureDurability } from "./sections/FutureDurability";
import { CrossCategoryCorrelation } from "./sections/CrossCategoryCorrelation";
import { SectionNav } from "./SectionNav";
import { normalizeScoreKeys } from "./scoreKeys";

export interface DeepDiveDashboardProps {
  ticker: string;
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

export function DeepDiveDashboard({ ticker, financials, categories: rawCategories, scores: rawScores, isLive, transcriptAnalysis, xSignalVelocity, edgarFacts }: DeepDiveDashboardProps) {
  const scores = normalizeScoreKeys(rawScores);
  const categories = normalizeScoreKeys(rawCategories);
  return (
  <>
    <SectionNav ticker={ticker} />
    <div className="space-y-6">
        <OverviewBanner financials={financials} scores={scores} />

        {/* Data-Rich */}
        <FinancialHealth
          financials={financials}
          structured={getStructured(categories["financial_health"] ?? null)}
          score={getScore(categories["financial_health"] ?? null, scores, "financial_health")}
          fallback={categories["financial_health"] ?? null}
          isLive={isLive}
          edgarFacts={edgarFacts}
        />
        <GrowthEarnings
          financials={financials}
          structured={getStructured(categories["growth_earnings"] ?? null)}
          score={getScore(categories["growth_earnings"] ?? null, scores, "growth_earnings")}
          fallback={categories["growth_earnings"] ?? null}
          isLive={isLive}
          transcriptAnalysis={transcriptAnalysis ?? null}
          edgarFacts={edgarFacts}
        />
        <TechnicalMarket
          financials={financials}
          structured={getStructured(categories["technical_market_structure"] ?? null)}
          score={getScore(categories["technical_market_structure"] ?? null, scores, "technical_market_structure")}
          fallback={categories["technical_market_structure"] ?? null}
          isLive={isLive}
        />

        {/* Cross-Category Correlations */}
        <CrossCategoryCorrelation financials={financials} isLive={isLive} />

        {/* Mixed */}
        <BusinessQuality
          financials={financials}
          structured={getStructured(categories["business_quality"] ?? null)}
          score={getScore(categories["business_quality"] ?? null, scores, "business_quality")}
          fallback={categories["business_quality"] ?? null}
          isLive={isLive}
          transcriptAnalysis={transcriptAnalysis ?? null}
        />

        {/* Competition — Item 1 segment / area / competitor table */}
        <Competition ticker={ticker} />

        {/* Supply Chain & Ecosystem — 1-hop relationship graph */}
        <SupplyChainEcosystem ticker={ticker} />
        <MacroRegime
          financials={financials}
          structured={getStructured(categories["macro_regime"] ?? null)}
          score={getScore(categories["macro_regime"] ?? null, scores, "macro_regime")}
          fallback={categories["macro_regime"] ?? null}
          isLive={isLive}
        />
        <RiskAssessment
          structured={getStructured(categories["risk_assessment"] ?? null)}
          score={getScore(categories["risk_assessment"] ?? null, scores, "risk_assessment")}
          fallback={categories["risk_assessment"] ?? null}
          isLive={isLive}
        />

        {/* Qualitative — 2-column grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <ManagementGovernance
            structured={getStructured(categories["management_governance"] ?? null)}
            score={getScore(categories["management_governance"] ?? null, scores, "management_governance")}
            fallback={categories["management_governance"] ?? null}
            isLive={isLive}
            transcriptAnalysis={transcriptAnalysis ?? null}
          />
          <SentimentNarrative
            structured={getStructured(categories["sentiment_narrative"] ?? null)}
            score={getScore(categories["sentiment_narrative"] ?? null, scores, "sentiment_narrative")}
            fallback={categories["sentiment_narrative"] ?? null}
            isLive={isLive}
            xSignalVelocity={xSignalVelocity}
          />
        </div>
        <FutureDurability
          structured={getStructured(categories["future_durability"] ?? null)}
          score={getScore(categories["future_durability"] ?? null, scores, "future_durability")}
          fallback={categories["future_durability"] ?? null}
          isLive={isLive}
        />
    </div>
  </>
  );
}

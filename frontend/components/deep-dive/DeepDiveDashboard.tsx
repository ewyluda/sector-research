import type { CuratedFinancials, CategoryOutput, DeepDiveCategoryStructured } from "@/lib/api";
import { DashboardSidebar } from "./DashboardSidebar";
import { OverviewBanner } from "./OverviewBanner";
import { FinancialHealth } from "./sections/FinancialHealth";
import { GrowthEarnings } from "./sections/GrowthEarnings";
import { TechnicalMarket } from "./sections/TechnicalMarket";
import { BusinessQuality } from "./sections/BusinessQuality";
import { MacroRegime } from "./sections/MacroRegime";
import { RiskAssessment } from "./sections/RiskAssessment";
import { ManagementGovernance } from "./sections/ManagementGovernance";
import { SentimentNarrative } from "./sections/SentimentNarrative";
import { FutureDurability } from "./sections/FutureDurability";

export interface DeepDiveDashboardProps {
  financials: CuratedFinancials | null;
  categories: Record<string, CategoryOutput | null>;
  scores: Record<string, number>;
  isLive?: boolean;
}

/** Map display-name keys → snake_case keys used by sidebar, radar, score bar */
const DISPLAY_TO_KEY: Record<string, string> = {
  "Business Quality": "business_quality",
  "Financial Health": "financial_health",
  "Growth & Earnings": "growth_earnings",
  "Management & Governance": "management_governance",
  "Technical & Market Structure": "technical_market_structure",
  "Macro & Regime": "macro_regime",
  "Sentiment & Narrative": "sentiment_narrative",
  "Risk Assessment": "risk_assessment",
  "Future Durability": "future_durability",
};

function normalizeKeys<T>(record: Record<string, T>): Record<string, T> {
  const out: Record<string, T> = {};
  for (const [k, v] of Object.entries(record)) {
    out[DISPLAY_TO_KEY[k] ?? k] = v;
  }
  return out;
}

function getStructured(cat: CategoryOutput | null): DeepDiveCategoryStructured | null {
  if (!cat || !cat.structured) return null;
  return cat.structured as DeepDiveCategoryStructured;
}

function getScore(cat: CategoryOutput | null, scores: Record<string, number>, key: string): number | null {
  return scores[key] ?? cat?.score ?? null;
}

export function DeepDiveDashboard({ financials, categories: rawCategories, scores: rawScores, isLive }: DeepDiveDashboardProps) {
  const scores = normalizeKeys(rawScores);
  const categories = normalizeKeys(rawCategories);
  return (
    <div className="flex gap-6">
      <DashboardSidebar scores={scores} />
      <div className="flex-1 space-y-6 min-w-0">
        <OverviewBanner financials={financials} scores={scores} />

        {/* Data-Rich */}
        <FinancialHealth
          financials={financials}
          structured={getStructured(categories["financial_health"] ?? null)}
          score={getScore(categories["financial_health"] ?? null, scores, "financial_health")}
          fallback={categories["financial_health"] ?? null}
          isLive={isLive}
        />
        <GrowthEarnings
          financials={financials}
          structured={getStructured(categories["growth_earnings"] ?? null)}
          score={getScore(categories["growth_earnings"] ?? null, scores, "growth_earnings")}
          fallback={categories["growth_earnings"] ?? null}
          isLive={isLive}
        />
        <TechnicalMarket
          financials={financials}
          structured={getStructured(categories["technical_market_structure"] ?? null)}
          score={getScore(categories["technical_market_structure"] ?? null, scores, "technical_market_structure")}
          fallback={categories["technical_market_structure"] ?? null}
          isLive={isLive}
        />

        {/* Mixed */}
        <BusinessQuality
          financials={financials}
          structured={getStructured(categories["business_quality"] ?? null)}
          score={getScore(categories["business_quality"] ?? null, scores, "business_quality")}
          fallback={categories["business_quality"] ?? null}
          isLive={isLive}
        />
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
          />
          <SentimentNarrative
            structured={getStructured(categories["sentiment_narrative"] ?? null)}
            score={getScore(categories["sentiment_narrative"] ?? null, scores, "sentiment_narrative")}
            fallback={categories["sentiment_narrative"] ?? null}
            isLive={isLive}
          />
        </div>
        <FutureDurability
          structured={getStructured(categories["future_durability"] ?? null)}
          score={getScore(categories["future_durability"] ?? null, scores, "future_durability")}
          fallback={categories["future_durability"] ?? null}
          isLive={isLive}
        />
      </div>
    </div>
  );
}

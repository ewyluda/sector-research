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

function getStructured(cat: CategoryOutput | null): DeepDiveCategoryStructured | null {
  if (!cat || !cat.structured) return null;
  return cat.structured as DeepDiveCategoryStructured;
}

function getScore(cat: CategoryOutput | null, scores: Record<string, number>, key: string): number | null {
  return scores[key] ?? cat?.score ?? null;
}

export function DeepDiveDashboard({ financials, categories, scores, isLive }: DeepDiveDashboardProps) {
  return (
    <div className="flex gap-6">
      <DashboardSidebar scores={scores} />
      <div className="flex-1 space-y-6 min-w-0">
        <OverviewBanner financials={financials} scores={scores} />

        {/* Data-Rich */}
        <FinancialHealth
          financials={financials}
          structured={getStructured(categories["financial_health"] ?? categories["Financial Health"] ?? null)}
          score={getScore(categories["financial_health"] ?? categories["Financial Health"] ?? null, scores, "financial_health")}
          isLive={isLive}
        />
        <GrowthEarnings
          financials={financials}
          structured={getStructured(categories["growth_earnings"] ?? categories["Growth & Earnings"] ?? null)}
          score={getScore(categories["growth_earnings"] ?? categories["Growth & Earnings"] ?? null, scores, "growth_earnings")}
          isLive={isLive}
        />
        <TechnicalMarket
          financials={financials}
          structured={getStructured(categories["technical_market_structure"] ?? categories["Technical & Market Structure"] ?? null)}
          score={getScore(categories["technical_market_structure"] ?? categories["Technical & Market Structure"] ?? null, scores, "technical_market_structure")}
          isLive={isLive}
        />

        {/* Mixed */}
        <BusinessQuality
          financials={financials}
          structured={getStructured(categories["business_quality"] ?? categories["Business Quality"] ?? null)}
          score={getScore(categories["business_quality"] ?? categories["Business Quality"] ?? null, scores, "business_quality")}
          isLive={isLive}
        />
        <MacroRegime
          financials={financials}
          structured={getStructured(categories["macro_regime"] ?? categories["Macro & Regime"] ?? null)}
          score={getScore(categories["macro_regime"] ?? categories["Macro & Regime"] ?? null, scores, "macro_regime")}
          isLive={isLive}
        />
        <RiskAssessment
          structured={getStructured(categories["risk_assessment"] ?? categories["Risk Assessment"] ?? null)}
          score={getScore(categories["risk_assessment"] ?? categories["Risk Assessment"] ?? null, scores, "risk_assessment")}
          isLive={isLive}
        />

        {/* Qualitative — 2-column grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <ManagementGovernance
            structured={getStructured(categories["management_governance"] ?? categories["Management & Governance"] ?? null)}
            score={getScore(categories["management_governance"] ?? categories["Management & Governance"] ?? null, scores, "management_governance")}
            isLive={isLive}
          />
          <SentimentNarrative
            structured={getStructured(categories["sentiment_narrative"] ?? categories["Sentiment & Narrative"] ?? null)}
            score={getScore(categories["sentiment_narrative"] ?? categories["Sentiment & Narrative"] ?? null, scores, "sentiment_narrative")}
            isLive={isLive}
          />
        </div>
        <FutureDurability
          structured={getStructured(categories["future_durability"] ?? categories["Future Durability"] ?? null)}
          score={getScore(categories["future_durability"] ?? categories["Future Durability"] ?? null, scores, "future_durability")}
          isLive={isLive}
        />
      </div>
    </div>
  );
}

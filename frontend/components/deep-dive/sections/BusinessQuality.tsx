import { memo } from "react";
import type { CuratedFinancials, DeepDiveCategoryStructured, CategoryOutput, TranscriptAnalysis } from "@/lib/api";
import { MixedSection } from "./MixedSection";
import { TrendLineChart } from "../charts/TrendLineChart";
import { TranscriptInsights } from "../panels/TranscriptInsights";

interface BusinessQualityProps {
  financials: CuratedFinancials | null;
  structured: DeepDiveCategoryStructured | null;
  score: number | null;
  fallback?: CategoryOutput | null;
  isLive?: boolean;
  transcriptAnalysis: TranscriptAnalysis | null;
}

const BQ_PASSES = ["pass3_qa_tensions", "pass5_consistency"];

function BusinessQualityImpl({ financials, structured, score, fallback, isLive, transcriptAnalysis }: BusinessQualityProps) {
  return (
    <MixedSection id="business_quality" label="Business Quality" score={score} structured={structured} fallback={fallback} isLive={isLive}>
      {financials ? (
        <>
          <div className="grid grid-cols-2 gap-2">
            {[
              { label: "Market Cap", value: `$${(financials.market_cap / 1e9).toFixed(1)}B` },
              { label: "Sector", value: financials.sector || "—" },
              { label: "Industry", value: financials.industry || "—" },
              { label: "Beta", value: financials.beta?.toFixed(2) ?? "—" },
            ].map((m) => (
              <div key={m.label} className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)]/40 p-2">
                <p className="text-[9px] text-[var(--color-text-muted)] uppercase">{m.label}</p>
                <p className="text-xs font-mono font-semibold text-[var(--color-text-primary)]">{m.value}</p>
              </div>
            ))}
          </div>
          <div>
            <h4 className="text-[10px] font-medium text-[var(--color-text-muted)] uppercase tracking-wider mb-2">Margin Trends</h4>
            <TrendLineChart
              lines={[
                { data: financials.quarterly_gross_margin, name: "Gross", color: "#34d399" },
                { data: financials.quarterly_operating_margin, name: "Operating", color: "#60a5fa" },
              ]}
            />
          </div>
        </>
      ) : null}
      {transcriptAnalysis ? (
        <TranscriptInsights analysis={transcriptAnalysis} passes={BQ_PASSES} />
      ) : null}
    </MixedSection>
  );
}

export const BusinessQuality = memo(BusinessQualityImpl);

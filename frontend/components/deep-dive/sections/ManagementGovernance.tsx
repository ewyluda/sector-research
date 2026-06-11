import { memo } from "react";
import type { DeepDiveCategoryStructured, CategoryOutput, TranscriptAnalysis } from "@/lib/api";
import { MixedSection } from "./MixedSection";
import { TranscriptInsights } from "../panels/TranscriptInsights";

interface ManagementGovernanceProps {
  structured: DeepDiveCategoryStructured | null;
  score: number | null;
  fallback?: CategoryOutput | null;
  transcriptAnalysis: TranscriptAnalysis | null;
  isLive?: boolean;
}

const MGMT_PASSES = ["pass1_claims", "pass2_tiers", "pass3_qa_tensions", "pass4_validation", "pass5_consistency"];

function ManagementGovernanceImpl({ structured, score, fallback, transcriptAnalysis, isLive }: ManagementGovernanceProps) {
  return (
    <MixedSection id="management_governance" label="Management & Governance" score={score} structured={structured} fallback={fallback} isLive={isLive}>
      {transcriptAnalysis ? (
        <TranscriptInsights analysis={transcriptAnalysis} passes={MGMT_PASSES} />
      ) : null}
    </MixedSection>
  );
}

export const ManagementGovernance = memo(ManagementGovernanceImpl);

import { memo } from "react";
import type { DeepDiveCategoryStructured, CategoryOutput } from "@/lib/api";
import { MixedSection } from "./MixedSection";
import { RAGStrip } from "../charts/RAGStrip";

interface RiskAssessmentProps {
  structured: DeepDiveCategoryStructured | null;
  score: number | null;
  fallback?: CategoryOutput | null;
  isLive?: boolean;
}

function RiskAssessmentImpl({ structured, score, fallback, isLive }: RiskAssessmentProps) {
  return (
    <MixedSection id="risk_assessment" label="Risk Assessment" score={score} structured={structured} fallback={fallback} isLive={isLive}>
      {structured ? (
        <div>
          <h4 className="text-[10px] font-medium text-[var(--color-text-muted)] uppercase tracking-wider mb-2">Risk Heat Map</h4>
          <RAGStrip findings={structured.key_findings} score={structured.score} />
        </div>
      ) : null}
    </MixedSection>
  );
}

export const RiskAssessment = memo(RiskAssessmentImpl);

import type { DeepDiveCategoryStructured } from "@/lib/api";
import { MixedSection } from "./MixedSection";
import { RAGStrip } from "../charts/RAGStrip";
import { FindingsTable } from "../panels/FindingsTable";

interface RiskAssessmentProps {
  structured: DeepDiveCategoryStructured | null;
  score: number | null;
  isLive?: boolean;
}

export function RiskAssessment({ structured, score, isLive }: RiskAssessmentProps) {
  return (
    <MixedSection id="risk_assessment" label="Risk Assessment" score={score} structured={structured} isLive={isLive}>
      {structured ? (
        <>
          <div>
            <h4 className="text-[10px] font-medium text-[var(--color-text-muted)] uppercase tracking-wider mb-2">Risk Heat Map</h4>
            <RAGStrip findings={structured.key_findings} score={structured.score} />
          </div>
          <div>
            <h4 className="text-[10px] font-medium text-[var(--color-text-muted)] uppercase tracking-wider mb-2">Risk Register</h4>
            <FindingsTable findings={structured.key_findings} />
          </div>
        </>
      ) : null}
    </MixedSection>
  );
}

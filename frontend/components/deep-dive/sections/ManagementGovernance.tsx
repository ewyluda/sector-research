import type { DeepDiveCategoryStructured } from "@/lib/api";
import { QualitativeCard } from "./QualitativeCard";

interface ManagementGovernanceProps {
  structured: DeepDiveCategoryStructured | null;
  score: number | null;
  isLive?: boolean;
}

export function ManagementGovernance({ structured, score, isLive }: ManagementGovernanceProps) {
  return (
    <QualitativeCard id="management_governance" label="Management & Governance" score={score} structured={structured} isLive={isLive} />
  );
}

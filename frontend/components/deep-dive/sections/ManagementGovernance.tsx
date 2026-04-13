import type { DeepDiveCategoryStructured, CategoryOutput } from "@/lib/api";
import { QualitativeCard } from "./QualitativeCard";

interface ManagementGovernanceProps {
  structured: DeepDiveCategoryStructured | null;
  score: number | null;
  fallback?: CategoryOutput | null;
  isLive?: boolean;
}

export function ManagementGovernance({ structured, score, fallback, isLive }: ManagementGovernanceProps) {
  return (
    <QualitativeCard id="management_governance" label="Management & Governance" score={score} structured={structured} fallback={fallback} isLive={isLive} />
  );
}

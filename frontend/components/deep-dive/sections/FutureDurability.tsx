import type { DeepDiveCategoryStructured, CategoryOutput } from "@/lib/api";
import { QualitativeCard } from "./QualitativeCard";

interface FutureDurabilityProps {
  structured: DeepDiveCategoryStructured | null;
  score: number | null;
  fallback?: CategoryOutput | null;
  isLive?: boolean;
}

export function FutureDurability({ structured, score, fallback, isLive }: FutureDurabilityProps) {
  return (
    <QualitativeCard id="future_durability" label="Future Durability" score={score} structured={structured} fallback={fallback} isLive={isLive} />
  );
}

import type { DeepDiveCategoryStructured } from "@/lib/api";
import { QualitativeCard } from "./QualitativeCard";

interface FutureDurabilityProps {
  structured: DeepDiveCategoryStructured | null;
  score: number | null;
  isLive?: boolean;
}

export function FutureDurability({ structured, score, isLive }: FutureDurabilityProps) {
  return (
    <QualitativeCard id="future_durability" label="Future Durability" score={score} structured={structured} isLive={isLive} />
  );
}

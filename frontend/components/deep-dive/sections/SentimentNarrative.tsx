import type { DeepDiveCategoryStructured, CategoryOutput } from "@/lib/api";
import { QualitativeCard } from "./QualitativeCard";

interface SentimentNarrativeProps {
  structured: DeepDiveCategoryStructured | null;
  score: number | null;
  fallback?: CategoryOutput | null;
  isLive?: boolean;
}

export function SentimentNarrative({ structured, score, fallback, isLive }: SentimentNarrativeProps) {
  return (
    <QualitativeCard id="sentiment_narrative" label="Sentiment & Narrative" score={score} structured={structured} fallback={fallback} isLive={isLive} />
  );
}

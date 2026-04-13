import type { DeepDiveCategoryStructured } from "@/lib/api";
import { QualitativeCard } from "./QualitativeCard";

interface SentimentNarrativeProps {
  structured: DeepDiveCategoryStructured | null;
  score: number | null;
  isLive?: boolean;
}

export function SentimentNarrative({ structured, score, isLive }: SentimentNarrativeProps) {
  return (
    <QualitativeCard id="sentiment_narrative" label="Sentiment & Narrative" score={score} structured={structured} isLive={isLive} />
  );
}

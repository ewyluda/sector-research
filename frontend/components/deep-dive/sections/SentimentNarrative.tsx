import type { DeepDiveCategoryStructured, CategoryOutput, XSignalVelocity } from "@/lib/api";
import { QualitativeCard } from "./QualitativeCard";
import { VelocitySparkline } from "../VelocitySparkline";

interface SentimentNarrativeProps {
  structured: DeepDiveCategoryStructured | null;
  score: number | null;
  fallback?: CategoryOutput | null;
  isLive?: boolean;
  xSignalVelocity?: XSignalVelocity | null;
  themeId?: string;
  ticker?: string;
}

export function SentimentNarrative({ structured, score, fallback, isLive, xSignalVelocity, themeId, ticker }: SentimentNarrativeProps) {
  return (
    <QualitativeCard
      id="sentiment_narrative"
      label="Sentiment & Narrative"
      score={score}
      structured={structured}
      fallback={fallback}
      isLive={isLive}
      headerAddon={
        xSignalVelocity ? (
          <VelocitySparkline velocity={xSignalVelocity} themeId={themeId} ticker={ticker} />
        ) : undefined
      }
    />
  );
}

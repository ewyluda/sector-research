"use client";

import { Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer } from "recharts";

const CATEGORY_SHORT: Record<string, string> = {
  business_quality: "BizQ",
  financial_health: "Fin",
  growth_earnings: "Grw",
  management_governance: "Mgt",
  technical_market_structure: "Tech",
  macro_regime: "Mac",
  sentiment_narrative: "Sen",
  risk_assessment: "Rsk",
  future_durability: "Fut",
};

interface ScoreRadarProps {
  scores: Record<string, number>;
}

export function ScoreRadar({ scores }: ScoreRadarProps) {
  const data = Object.entries(CATEGORY_SHORT).map(([key, short]) => ({
    category: short,
    score: scores[key] ?? 0,
    fullMark: 100,
  }));

  return (
    <ResponsiveContainer width="100%" height={260}>
      <RadarChart data={data}>
        <PolarGrid stroke="var(--color-border)" />
        <PolarAngleAxis dataKey="category" tick={{ fontSize: 10, fill: "var(--color-text-muted)" }} />
        <PolarRadiusAxis angle={90} domain={[0, 100]} tick={{ fontSize: 8, fill: "var(--color-text-faint)" }} />
        <Radar name="Score" dataKey="score" stroke="var(--color-primary)" fill="var(--color-primary)" fillOpacity={0.2} strokeWidth={2} />
      </RadarChart>
    </ResponsiveContainer>
  );
}

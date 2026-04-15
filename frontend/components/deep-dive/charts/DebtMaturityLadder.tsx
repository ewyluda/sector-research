"use client";

import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";
import type { EdgarFacts } from "@/lib/api";
import { formatUSD } from "@/lib/format";

const BUCKETS: { label: string; concept: string }[] = [
  { label: "Next 12mo", concept: "us-gaap:LongTermDebtMaturitiesRepaymentsOfPrincipalInNextTwelveMonths" },
  { label: "Year 2", concept: "us-gaap:LongTermDebtMaturitiesRepaymentsOfPrincipalInYearTwo" },
  { label: "Year 3", concept: "us-gaap:LongTermDebtMaturitiesRepaymentsOfPrincipalInYearThree" },
  { label: "Year 4", concept: "us-gaap:LongTermDebtMaturitiesRepaymentsOfPrincipalInYearFour" },
  { label: "Year 5", concept: "us-gaap:LongTermDebtMaturitiesRepaymentsOfPrincipalInYearFive" },
  { label: "After Y5", concept: "us-gaap:LongTermDebtMaturitiesRepaymentsOfPrincipalAfterYearFive" },
];

interface DebtMaturityLadderProps {
  edgarFacts: EdgarFacts;
}

export function DebtMaturityLadder({ edgarFacts }: DebtMaturityLadderProps) {
  const data = BUCKETS.map((b) => {
    const latest = edgarFacts[b.concept]?.[0];
    return {
      bucket: b.label,
      value: latest ? latest.value : 0,
      periodEnd: latest?.period_end ?? null,
      hasData: !!latest,
    };
  });

  const hasAnyData = data.some((d) => d.hasData);
  if (!hasAnyData) {
    return (
      <div className="text-[11px] text-[var(--color-text-muted)] px-2 py-6 text-center">
        Debt maturity schedule not disclosed in SEC XBRL filings.
      </div>
    );
  }

  const latestPeriod = data.find((d) => d.periodEnd)?.periodEnd;
  // Sum in raw dollars (was previously summed in $B before simplification).
  const total = data.reduce((sum, d) => sum + d.value, 0);

  return (
    <div>
      <div className="flex items-center justify-between mb-1 px-1">
        <span className="text-[10px] text-[var(--color-text-muted)]">
          {latestPeriod ? `As of ${latestPeriod}` : ""}
        </span>
        <span className="text-[10px] text-[var(--color-text-muted)] font-mono">
          Total: {formatUSD(total)}
        </span>
      </div>
      <ResponsiveContainer width="100%" height={200}>
        <BarChart data={data} margin={{ top: 5, right: 5, bottom: 5, left: 5 }}>
          <XAxis dataKey="bucket" tick={{ fontSize: 10, fill: "var(--color-text-muted)" }} />
          <YAxis
            tick={{ fontSize: 10, fill: "var(--color-text-muted)" }}
            tickFormatter={(v) => formatUSD(v)}
            width={60}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "var(--color-surface)",
              border: "1px solid var(--color-border)",
              borderRadius: 8,
              fontSize: 11,
            }}
            formatter={(value) => [formatUSD(value as number), "Principal due"]}
          />
          <Bar dataKey="value" radius={[4, 4, 0, 0]}>
            {data.map((d, i) => (
              <Cell key={i} fill={d.hasData ? "#f87171" : "#4b5563"} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

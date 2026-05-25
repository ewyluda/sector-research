"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { getCompanyOverview } from "@/lib/api";
import type { CompanyOverview } from "@/lib/api";
import { StatisticsGrid } from "@/components/company/StatisticsGrid";
import { PriceChart } from "@/components/company/PriceChart";
import { BullsBears } from "@/components/company/BullsBears";

export default function OverviewPage() {
  const params = useParams<{ ticker: string }>();
  const ticker = (Array.isArray(params.ticker) ? params.ticker[0] : params.ticker ?? "").toUpperCase();
  // null = not yet fetched, undefined = fetched but failed
  const [overview, setOverview] = useState<CompanyOverview | null | undefined>(null);

  useEffect(() => {
    if (!ticker) return;
    let alive = true;
    getCompanyOverview(ticker)
      .then((o) => { if (alive) setOverview(o); })
      .catch(() => { if (alive) setOverview(undefined); });
    return () => {
      alive = false;
    };
  }, [ticker]);

  const loading = overview === null;

  return (
    <div className="space-y-4">
      {(overview && overview !== undefined) && (
        <p className="text-xs text-[var(--text-muted)]">
          {overview.sector}
          {overview.industry ? ` · ${overview.industry}` : ""}
        </p>
      )}
      {loading ? (
        <div className="p-6 text-sm text-[var(--text-muted)]">Loading overview…</div>
      ) : (
        <>
          {overview && <PriceChart prices={overview.prices} />}
          {overview && <StatisticsGrid groups={overview.stats} />}
        </>
      )}
      <BullsBears ticker={ticker} />
    </div>
  );
}

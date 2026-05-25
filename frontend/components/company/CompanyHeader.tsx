"use client";

import { useEffect, useState } from "react";
import { getCompanyHeader } from "@/lib/api";
import type { CompanyHeader as CompanyHeaderData } from "@/lib/api";
import { PricePill } from "./PricePill";
import { LensSelector } from "./LensSelector";

export function CompanyHeader({ ticker }: { ticker: string }) {
  const [data, setData] = useState<CompanyHeaderData | null>(null);

  useEffect(() => {
    let alive = true;
    getCompanyHeader(ticker)
      .then((d) => alive && setData(d))
      .catch(() => alive && setData(null));
    return () => {
      alive = false;
    };
  }, [ticker]);

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
      <div className="flex items-center gap-3">
        {data?.logo_url && (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={data.logo_url} alt="" className="h-7 w-7 rounded" />
        )}
        <div>
          <div className="flex items-center gap-2">
            <span className="text-base font-semibold text-[var(--text)]">{ticker}</span>
            {data?.exchange && (
              <span className="text-xs text-[var(--text-muted)]">{data.exchange}</span>
            )}
          </div>
          {data?.name && (
            <div className="text-xs text-[var(--text-muted)]">{data.name}</div>
          )}
        </div>
        <div className="ml-2">
          <PricePill
            price={data?.price ?? null}
            change={data?.change ?? null}
            changePct={data?.change_pct ?? null}
            currency={data?.currency ?? null}
            delayLabel={data?.delay_label ?? "15 min delay"}
          />
        </div>
      </div>
      <LensSelector />
    </div>
  );
}

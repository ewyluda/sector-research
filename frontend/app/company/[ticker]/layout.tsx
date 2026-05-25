"use client";

import { useParams } from "next/navigation";
import { CompanyHeader } from "@/components/company/CompanyHeader";
import { TabStrip } from "@/components/company/TabStrip";

export default function CompanyLayout({ children }: { children: React.ReactNode }) {
  const params = useParams<{ ticker: string }>();
  const ticker = (Array.isArray(params.ticker) ? params.ticker[0] : params.ticker ?? "").toUpperCase();

  return (
    <div className="mx-auto max-w-[1400px]">
      <div className="sticky top-14 z-30 bg-[var(--surface)]" data-print-hide="true">
        <CompanyHeader ticker={ticker} />
        <TabStrip ticker={ticker} />
      </div>
      <div className="p-4">{children}</div>
    </div>
  );
}

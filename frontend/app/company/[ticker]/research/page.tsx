"use client";

import { Suspense } from "react";
import { useParams } from "next/navigation";
import { ResearchTab } from "@/components/company/ResearchTab";

export default function CompanyResearchPage() {
  const params = useParams<{ ticker: string }>();
  const ticker = (Array.isArray(params.ticker) ? params.ticker[0] : params.ticker ?? "").toUpperCase();
  // ResearchTab reads useSearchParams; keep it under a Suspense boundary.
  return (
    <Suspense fallback={null}>
      <ResearchTab ticker={ticker} />
    </Suspense>
  );
}

"use client";

import { Suspense } from "react";
import { useParams } from "next/navigation";
import { ThesesTab } from "@/components/company/ThesesTab";

export default function CompanyThesesPage() {
  const params = useParams<{ ticker: string }>();
  const ticker = (Array.isArray(params.ticker) ? params.ticker[0] : params.ticker ?? "").toUpperCase();
  // ThesesTab reads useSearchParams; keep it under a Suspense boundary.
  return (
    <Suspense fallback={null}>
      <ThesesTab ticker={ticker} />
    </Suspense>
  );
}

"use client";

import { useParams } from "next/navigation";
import { ResearchTab } from "@/components/company/ResearchTab";

export default function CompanyResearchPage() {
  const params = useParams<{ ticker: string }>();
  const ticker = (Array.isArray(params.ticker) ? params.ticker[0] : params.ticker ?? "").toUpperCase();
  return <ResearchTab ticker={ticker} />;
}

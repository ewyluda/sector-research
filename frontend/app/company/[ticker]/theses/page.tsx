"use client";

import { useParams } from "next/navigation";
import { ThesesTab } from "@/components/company/ThesesTab";

export default function CompanyThesesPage() {
  const params = useParams<{ ticker: string }>();
  const ticker = (Array.isArray(params.ticker) ? params.ticker[0] : params.ticker ?? "").toUpperCase();
  return <ThesesTab ticker={ticker} />;
}

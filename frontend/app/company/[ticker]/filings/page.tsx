"use client";

import { useParams } from "next/navigation";
import TickerFilingsCard from "@/components/filings/TickerFilingsCard";

export default function CompanyFilingsPage() {
  const params = useParams<{ ticker: string }>();
  const ticker = (Array.isArray(params.ticker) ? params.ticker[0] : params.ticker ?? "").toUpperCase();
  return <TickerFilingsCard ticker={ticker} />;
}

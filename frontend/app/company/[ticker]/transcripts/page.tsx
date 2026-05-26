"use client";

import { useParams } from "next/navigation";
import { TranscriptReader } from "@/components/company/TranscriptReader";

export default function TranscriptsPage() {
  const params = useParams<{ ticker: string }>();
  const ticker = (Array.isArray(params.ticker) ? params.ticker[0] : params.ticker ?? "").toUpperCase();
  return <TranscriptReader ticker={ticker} />;
}

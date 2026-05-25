"use client";

import { useParams } from "next/navigation";
import { ModelWorkspace } from "@/components/model/ModelWorkspace";

export default function CompanyModelPage() {
  const params = useParams<{ ticker: string }>();
  const ticker = (Array.isArray(params.ticker) ? params.ticker[0] : params.ticker ?? "").toUpperCase();
  return <ModelWorkspace ticker={ticker} />;
}

"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import clsx from "clsx";

const TABS: { seg: string; label: string }[] = [
  { seg: "", label: "Overview" },
  { seg: "financials", label: "Financials" },
  { seg: "transcripts", label: "Transcripts" },
  { seg: "research", label: "Research" },
  { seg: "model", label: "Model" },
  { seg: "filings", label: "Filings" },
  { seg: "theses", label: "Theses" },
];

export function TabStrip({ ticker }: { ticker: string }) {
  const pathname = usePathname();
  const params = useSearchParams();
  const lens = params.get("lens");
  const base = `/company/${ticker}`;
  const qs = lens ? `?lens=${encodeURIComponent(lens)}` : "";

  return (
    <nav className="flex items-center gap-1 overflow-x-auto border-b border-[var(--border)] px-2">
      {TABS.map(({ seg, label }) => {
        const href = seg ? `${base}/${seg}` : base;
        const active = seg ? pathname === href : pathname === base;
        return (
          <Link
            key={seg || "overview"}
            href={`${href}${qs}`}
            className={clsx(
              "whitespace-nowrap px-3 py-2 text-sm transition-colors",
              active
                ? "border-b-2 border-[var(--primary)] font-medium text-[var(--text)]"
                : "text-[var(--text-muted)] hover:text-[var(--text)]"
            )}
          >
            {label}
          </Link>
        );
      })}
    </nav>
  );
}

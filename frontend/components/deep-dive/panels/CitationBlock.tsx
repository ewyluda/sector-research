interface CitationBlockProps {
  children: React.ReactNode;
  source?: string;
}

type Provider = "edgar" | "fmp" | "fred" | "x" | "txn" | "default";

function detectProvider(source?: string): Provider {
  if (!source) return "default";
  const s = source.toLowerCase();
  if (s.includes("edgar") || s.includes("10-k") || s.includes("10-q") || s.includes("def 14a") || s.includes("sec filing")) return "edgar";
  if (s.includes("fmp")) return "fmp";
  if (s.includes("fred")) return "fred";
  if (s.includes("twitter") || s.includes(" x ") || /^x[\s/]/.test(s)) return "x";
  if (s.includes("transcript") || s.includes("earnings") || s.includes("prompted") || s.includes("q&a")) return "txn";
  return "default";
}

const DOT_COLORS: Record<Provider, string> = {
  edgar: "bg-amber-700",
  fmp: "bg-sky-700",
  fred: "bg-purple-600",
  x: "bg-pink-700",
  txn: "bg-emerald-700",
  default: "bg-[var(--color-text-faint)]",
};

/**
 * Provenance pill citation — matches the "01 Provenance pills" theme in
 * design/citation-styles.html. Evidence text reads as clean prose; source
 * attribution renders as a small rounded pill with a provider-colored dot.
 */
export function CitationBlock({ children, source }: CitationBlockProps) {
  const provider = detectProvider(source);
  return (
    <div className="my-1 flex flex-wrap items-baseline gap-x-2 gap-y-1">
      <div className="flex-1 min-w-0 text-[12px] leading-snug text-[var(--color-text-muted)]">
        {children}
      </div>
      {source && (
        <span className="inline-flex shrink-0 items-center gap-1.5 h-[22px] px-2.5 rounded-full border border-[var(--color-border)] bg-[var(--color-surface-alt)] text-[10.5px] font-medium text-[var(--color-text-muted)] whitespace-nowrap">
          <span className={`w-1.5 h-1.5 rounded-full ${DOT_COLORS[provider]}`} />
          {source}
        </span>
      )}
    </div>
  );
}

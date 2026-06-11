interface CitationBlockProps {
  children: React.ReactNode;
  source?: string;
}

type Provider = "edgar" | "fmp" | "fred" | "x" | "txn" | "default";

function detectProvider(source?: string): Provider {
  if (!source) return "default";
  const s = source.toLowerCase();
  if (s.includes("edgar") || s.includes("10-k") || s.includes("10-q") || s.includes("def 14a") || s.includes("sec filing") || s.includes("xbrl")) return "edgar";
  if (s.includes("fmp")) return "fmp";
  if (s.includes("fred")) return "fred";
  if (s.includes("twitter") || /^x[\s/]/.test(s) || /\bx api\b/.test(s)) return "x";
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
 * Parse a "[Source: <provider> [: <values>]]" wrapper that the AI deep-dive
 * output emits as the evidence string. When detected, the inner identifier
 * becomes the pill content and any post-colon values become the body prose.
 */
function parseEmbeddedSource(text: string): { body: string; source?: string } {
  const m = text.match(/^\s*\[Source:\s*([\s\S]+?)\]\s*$/i);
  if (!m) return { body: text };
  const inner = m[1].trim();
  const colonIdx = inner.indexOf(":");
  if (colonIdx > 0 && colonIdx < inner.length - 1) {
    const after = inner.slice(colonIdx + 1).trim();
    if (/[\d$%=]/.test(after.slice(0, 50))) {
      return { source: inner.slice(0, colonIdx).trim(), body: after };
    }
  }
  return { source: inner, body: "" };
}

/**
 * Provenance pill citation — "01 Provenance pills" style.
 * Evidence text reads as clean prose; source attribution renders as a small
 * rounded pill with a provider-colored dot.
 */
export function CitationBlock({ children, source: explicitSource }: CitationBlockProps) {
  let body: React.ReactNode = children;
  let source = explicitSource;

  if (!source && typeof children === "string") {
    const parsed = parseEmbeddedSource(children);
    if (parsed.source) {
      source = parsed.source;
      body = parsed.body;
    }
  }

  const provider = detectProvider(source);
  const hasBody = typeof body === "string" ? body.length > 0 : body != null;

  return (
    <div className="my-1 flex flex-wrap items-baseline gap-x-2 gap-y-1">
      {hasBody && (
        <div className="flex-1 min-w-0 text-[12px] leading-snug text-[var(--color-text-muted)]">
          {body}
        </div>
      )}
      {source && (
        <span className="inline-flex shrink-0 items-center gap-1.5 max-w-full h-[22px] px-2.5 rounded-full border border-[var(--color-border)] bg-[var(--color-surface-alt)] text-[10.5px] font-medium text-[var(--color-text-muted)]">
          <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${DOT_COLORS[provider]}`} />
          <span className="truncate">{source}</span>
        </span>
      )}
    </div>
  );
}

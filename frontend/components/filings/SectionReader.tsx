"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { filings } from "@/lib/api";
import type { FilingSectionText } from "@/lib/api";

interface Props {
  ticker: string;
  accession: string;
  sectionKey: string;
  heading: string | null;
  onClose: () => void;
}

type Block =
  | { kind: "heading"; level: 2 | 3; id: string; text: string }
  | { kind: "paragraph"; text: string }
  | { kind: "list"; items: string[] }
  | { kind: "boilerplate"; title: string; paragraphs: string[] };

export default function SectionReader({
  ticker,
  accession,
  sectionKey,
  heading,
  onClose,
}: Props) {
  const [data, setData] = useState<FilingSectionText | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);
  const contentRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    filings
      .getSection(ticker, accession, sectionKey)
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "fetch failed");
      });
    return () => {
      cancelled = true;
    };
  }, [ticker, accession, sectionKey]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const blocks = useMemo(() => parseSectionText(data?.text ?? ""), [data?.text]);
  const tocItems = useMemo(
    () => blocks.filter((b): b is Extract<Block, { kind: "heading" }> => b.kind === "heading"),
    [blocks],
  );

  const wordCount = data ? data.text.trim().split(/\s+/).length : 0;
  const readMinutes = Math.max(1, Math.round(wordCount / 220));

  const edgarUrl = useMemo(() => {
    if (!accession) return null;
    return `https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=${ticker}&type=&dateb=&owner=include&count=40&search_text=${accession}`;
  }, [accession, ticker]);

  // Spy on heading visibility for ToC active-state highlighting.
  useEffect(() => {
    const root = contentRef.current;
    if (!root || tocItems.length === 0) return;
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible[0]) setActiveId(visible[0].target.id);
      },
      { root, rootMargin: "0px 0px -70% 0px", threshold: 0 },
    );
    tocItems.forEach((h) => {
      const el = root.querySelector(`#${CSS.escape(h.id)}`);
      if (el) observer.observe(el);
    });
    return () => observer.disconnect();
  }, [tocItems, blocks]);

  function jumpTo(id: string) {
    const el = contentRef.current?.querySelector(`#${CSS.escape(id)}`);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={heading ?? sectionKey}
      className="fixed inset-0 z-50 bg-black/40 flex items-start justify-center p-4 sm:p-6"
      onClick={onClose}
    >
      <div
        className="bg-[var(--surface)] rounded-xl border border-[var(--border)] max-w-6xl w-full my-4 shadow-xl flex flex-col max-h-[calc(100vh-2rem)]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="border-b border-[var(--border)] px-5 py-3 flex items-start justify-between rounded-t-xl gap-4">
          <div className="min-w-0">
            <div className="text-[11px] text-[var(--text-faint)] font-mono">
              {ticker.toUpperCase()} · {accession}
            </div>
            <h3 className="text-base font-semibold text-[var(--text)] truncate">
              {heading ?? sectionKey}
            </h3>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {edgarUrl && (
              <a
                href={edgarUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="text-[11px] px-2 py-1 rounded border border-[var(--border)] text-[var(--text-muted)] hover:text-[var(--primary)] hover:border-[var(--primary)] transition-colors"
                title="Open on SEC.gov"
              >
                EDGAR ↗
              </a>
            )}
            <button
              type="button"
              onClick={onClose}
              className="text-[var(--text-muted)] hover:text-[var(--text)] text-2xl leading-none px-2"
              aria-label="Close"
            >
              ×
            </button>
          </div>
        </div>

        {/* Metadata strip */}
        {data && (
          <div className="border-b border-[var(--border)] px-5 py-2 flex items-center gap-4 text-[11px] text-[var(--text-muted)]">
            <span className="inline-flex items-center gap-1">
              <span className="font-mono tabular-nums text-[var(--text)]">
                {wordCount.toLocaleString()}
              </span>{" "}
              words
            </span>
            <span className="text-[var(--text-faint)]">·</span>
            <span className="inline-flex items-center gap-1">
              <span className="font-mono tabular-nums text-[var(--text)]">~{readMinutes}</span> min read
            </span>
            <span className="text-[var(--text-faint)]">·</span>
            <span className="inline-flex items-center gap-1">
              <span className="font-mono tabular-nums text-[var(--text)]">{tocItems.length}</span>{" "}
              sections
            </span>
            <span className="text-[var(--text-faint)]">·</span>
            <span className="font-mono">{data.extraction_method}</span>
          </div>
        )}

        {/* Body: ToC + content */}
        <div
          className={`flex-1 min-h-0 grid grid-cols-1 ${
            tocItems.length > 0 ? "lg:grid-cols-[220px_minmax(0,1fr)]" : ""
          }`}
        >
          {/* ToC sidebar */}
          {tocItems.length > 0 && (
            <nav
              className="hidden lg:block border-r border-[var(--border)] overflow-y-auto px-3 py-4 text-xs"
              aria-label="Section contents"
            >
              <div className="text-[10px] uppercase tracking-wider text-[var(--text-faint)] mb-2 px-2">
                On this page
              </div>
              <ul className="space-y-1">
                {tocItems.map((h) => (
                  <li key={h.id}>
                    <button
                      onClick={() => jumpTo(h.id)}
                      className={`w-full text-left px-2 py-1 rounded hover:bg-[var(--surface-alt)] transition-colors ${
                        h.level === 3 ? "pl-4 text-[var(--text-muted)]" : "text-[var(--text)]"
                      } ${
                        activeId === h.id
                          ? "bg-[var(--accent-bg)] text-[var(--primary)] font-medium"
                          : ""
                      }`}
                    >
                      {h.text}
                    </button>
                  </li>
                ))}
              </ul>
            </nav>
          )}

          {/* Content */}
          <div ref={contentRef} className="overflow-y-auto px-6 sm:px-10 py-6">
            {error && <div className="text-sm text-[var(--error-text)]">{error}</div>}
            {!error && !data && (
              <div className="text-sm text-[var(--text-faint)]">Loading…</div>
            )}
            {data && (
              <article className="max-w-2xl mx-auto text-[var(--text)]">
                {blocks.map((b, i) => (
                  <BlockView key={i} block={b} />
                ))}
              </article>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function BlockView({ block }: { block: Block }) {
  switch (block.kind) {
    case "heading":
      return block.level === 2 ? (
        <h4
          id={block.id}
          className="text-lg font-semibold text-[var(--text)] mt-8 mb-3 scroll-mt-4"
        >
          {block.text}
        </h4>
      ) : (
        <h5
          id={block.id}
          className="text-sm font-semibold text-[var(--text-muted)] uppercase tracking-wide mt-6 mb-2 scroll-mt-4"
        >
          {block.text}
        </h5>
      );
    case "paragraph":
      return (
        <p className="text-[15px] leading-7 text-[var(--text)] my-3">{block.text}</p>
      );
    case "list":
      return (
        <ul className="list-disc pl-6 my-3 space-y-1.5 text-[15px] leading-7 text-[var(--text)] marker:text-[var(--text-faint)]">
          {block.items.map((it, i) => (
            <li key={i}>{it}</li>
          ))}
        </ul>
      );
    case "boilerplate":
      return <BoilerplateCallout title={block.title} paragraphs={block.paragraphs} />;
  }
}

function BoilerplateCallout({ title, paragraphs }: { title: string; paragraphs: string[] }) {
  const [open, setOpen] = useState(false);
  return (
    <details
      open={open}
      onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}
      className="my-4 rounded-lg border border-[var(--border)] bg-[var(--surface-alt)]"
    >
      <summary className="cursor-pointer px-4 py-2 text-xs font-medium text-[var(--text-muted)] hover:text-[var(--text)] flex items-center gap-2 select-none">
        <span aria-hidden>{open ? "▾" : "▸"}</span>
        <span>{title}</span>
        <span className="ml-auto text-[10px] uppercase tracking-wider text-[var(--text-faint)]">
          legal · {paragraphs.length} paragraphs
        </span>
      </summary>
      <div className="px-4 pb-4 pt-1">
        {paragraphs.map((p, i) => (
          <p
            key={i}
            className="text-xs leading-6 text-[var(--text-muted)] my-2 first:mt-0 last:mb-0"
          >
            {p}
          </p>
        ))}
      </div>
    </details>
  );
}


// ────────────────────────────────────────────────────────────────────
// Text parser
//
// SEC filing text from our extractor is line-broken without consistent
// paragraph separators (single \n between most things). Strategy:
//   1. Walk lines.
//   2. A line that matches the heading whitelist OR Item/Part pattern OR
//      is ALL CAPS + 3+ chars → emit heading. Cuts off any open paragraph.
//   3. A line starting with a bullet marker → accumulate into the current
//      list (groups of bullets become one <ul>).
//   4. Otherwise → accumulate as paragraph fragments. Flush on sentence
//      terminator (.!?), heading, or list boundary.
//   5. The "Forward-Looking Statements" / safe-harbor block becomes a
//      collapsible boilerplate callout instead of dominating the reader.

const BOILERPLATE_HEADINGS = /^(forward-?looking statements?|safe harbor|cautionary (note|statement))\b/i;
const HEADING_LINE_RE = /^(?:item\s+\d+[a-z]?\.?|part\s+[ivx]+\.?)\b.*/i;
const ALL_CAPS_RE = /^[A-Z0-9][A-Z0-9 \-,&/():']{2,}[A-Z0-9)]\s*$/;
const BULLET_RE = /^\s*(?:[•‣◦⁃∙\-*·▪]|\(\s*[a-z0-9]+\s*\))\s+/;
const SENTENCE_END_RE = /[.!?][")\]]?\s*$/;

const HEADING_WHITELIST = new Set([
  // 10-Q / 10-K MD&A
  "overview",
  "recent developments",
  "results of operations",
  "components of our results of operations",
  "components of results of operations",
  "liquidity and capital resources",
  "critical accounting policies",
  "critical accounting estimates",
  "recent accounting pronouncements",
  "off-balance sheet arrangements",
  "cash flows",
  "operating activities",
  "investing activities",
  "financing activities",
  "quantitative and qualitative disclosures about market risk",
  "contractual obligations",
  "material cash requirements",
  "significant accounting policies",
  "use of estimates",
  "key business metrics",
  "non-gaap financial measures",
  "non-gaap measures",
  "key factors affecting our performance",
  "comparison of results of operations",
  // (Skipping single line-items like "revenue", "cost of revenue",
  // "operating expenses", "net income" — they appear in tables and prose
  // many times and produce duplicate-heading false positives.)
  // Item 1 Business
  "our company",
  "our mission",
  "our strategy",
  "our industry",
  "our customers",
  "our competition",
  "competition",
  "our products",
  "our products and services",
  "our services",
  "our solutions",
  "our market",
  "our market opportunity",
  "sales and marketing",
  "research and development",
  "government regulation",
  "intellectual property",
  "human capital",
  "human capital management",
  "human capital resources",
  "employees",
  "available information",
  // Item 1A Risk Factors
  "risk factors summary",
  "summary of risk factors",
  // DEF 14A
  "compensation discussion and analysis",
  "executive compensation",
  "director compensation",
  "beneficial ownership",
  "audit matters",
]);

export function parseSectionText(text: string): Block[] {
  if (!text) return [];

  const lines = text
    .replace(/\r\n/g, "\n")
    .replace(/ /g, " ")
    .split("\n")
    .map((l) => l.trim());

  const blocks: Block[] = [];
  const usedIds = new Map<string, number>();
  let paraBuf: string[] = [];
  let listBuf: string[] | null = null;
  let inBoilerplate = false;
  let boilerplateTitle = "Forward-Looking Statements";
  let boilerplateBuf: string[] = [];

  const uniqueId = (base: string): string => {
    const n = (usedIds.get(base) ?? 0) + 1;
    usedIds.set(base, n);
    return n === 1 ? base : `${base}-${n}`;
  };

  const flushParagraph = () => {
    if (paraBuf.length === 0) return;
    const t = paraBuf.join(" ").replace(/\s{2,}/g, " ").trim();
    paraBuf = [];
    if (!t) return;
    if (inBoilerplate) {
      boilerplateBuf.push(t);
    } else {
      blocks.push({ kind: "paragraph", text: t });
    }
  };
  const flushList = () => {
    if (listBuf && listBuf.length > 0) {
      blocks.push({ kind: "list", items: listBuf });
    }
    listBuf = null;
  };
  const flushBoilerplate = () => {
    if (boilerplateBuf.length > 0) {
      blocks.push({ kind: "boilerplate", title: boilerplateTitle, paragraphs: boilerplateBuf });
    }
    boilerplateBuf = [];
    inBoilerplate = false;
  };

  for (const raw of lines) {
    if (!raw) continue;
    const line = raw;

    const headingClass = classifyHeading(line);
    if (headingClass) {
      flushParagraph();
      flushList();

      if (BOILERPLATE_HEADINGS.test(line)) {
        flushBoilerplate();
        inBoilerplate = true;
        boilerplateTitle = line.replace(/[:.]\s*$/, "");
        continue;
      }
      if (inBoilerplate) flushBoilerplate();

      blocks.push({
        kind: "heading",
        level: headingClass === "primary" ? 2 : 3,
        id: uniqueId(slugify(line)),
        text: titleCaseIfShouty(line),
      });
      continue;
    }

    if (BULLET_RE.test(line)) {
      flushParagraph();
      if (listBuf === null) listBuf = [];
      listBuf.push(line.replace(BULLET_RE, "").trim());
      continue;
    }
    flushList();

    paraBuf.push(line);
    if (SENTENCE_END_RE.test(line)) {
      flushParagraph();
    }
  }
  flushParagraph();
  flushList();
  flushBoilerplate();

  return blocks;
}

function classifyHeading(line: string): "primary" | "secondary" | null {
  if (line.length < 3 || line.length > 110) return null;
  if (HEADING_LINE_RE.test(line)) return "primary";
  // ALL CAPS — require at least 3 alphabetic uppercase chars so a bare
  // "2026" or "(1)" doesn't get promoted to a heading.
  if (ALL_CAPS_RE.test(line) && (line.match(/[A-Z]/g) ?? []).length >= 3) {
    return "primary";
  }
  const normalized = line.toLowerCase().replace(/[.:]\s*$/, "").trim();
  if (HEADING_WHITELIST.has(normalized)) return "secondary";
  return null;
}

function titleCaseIfShouty(line: string): string {
  if (!ALL_CAPS_RE.test(line)) return line;
  const small = new Set(["and", "of", "the", "in", "for", "to", "a", "an", "or", "on", "at", "by"]);
  return line
    .toLowerCase()
    .split(/\s+/)
    .map((w, i) => (i > 0 && small.has(w) ? w : w.charAt(0).toUpperCase() + w.slice(1)))
    .join(" ");
}

function slugify(s: string): string {
  return (
    "h-" +
    s
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 60)
  );
}

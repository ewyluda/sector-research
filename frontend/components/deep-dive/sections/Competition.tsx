"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { competition } from "@/lib/api";
import type { CompetitionData, CompetitorChip } from "@/lib/api";
import { usePersistedCollapse } from "../usePersistedCollapse";

interface Props {
  ticker: string;
}

export function Competition({ ticker }: Props) {
  const [data, setData] = useState<CompetitionData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [collapsed, setCollapsed] = usePersistedCollapse("competition");

  useEffect(() => {
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true);
    setError(null);
    competition
      .get(ticker)
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "load failed");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [ticker]);

  const toggle = () => setCollapsed((c) => !c);

  const segCount = data?.segments.length ?? 0;
  const compCount = (data?.segments ?? []).reduce(
    (n, s) => n + s.areas.reduce((m, a) => m + a.competitors.length, 0),
    0,
  );
  const filingPill = data?.filing
    ? `${data.filing.form_type} · ${data.filing.filing_date}`
    : null;
  const stat = data && data.extracted_at
    ? `${segCount} segment${segCount !== 1 ? "s" : ""} · ${compCount} competitor${compCount !== 1 ? "s" : ""}${filingPill ? " · " + filingPill : ""}`
    : null;

  return (
    <Shell collapsed={collapsed} onToggle={toggle} stat={stat}>
      {loading && (
        <p className="text-[11px] text-[var(--color-text-muted)]">Loading…</p>
      )}
      {error && (
        <p className="text-[11px] text-[var(--error-text)]">{error}</p>
      )}
      {!loading && !error && data && data.extracted_at === null && (
        <EmptyNeverExtracted />
      )}
      {!loading && !error && data && data.extracted_at !== null && data.segments.length === 0 && (
        <EmptyNoSegments />
      )}
      {!loading && !error && data && data.segments.length > 0 && (
        <SegmentsList data={data} />
      )}
    </Shell>
  );
}

function Shell({
  children,
  collapsed,
  onToggle,
  stat,
}: {
  children: React.ReactNode;
  collapsed: boolean;
  onToggle: () => void;
  stat: string | null;
}) {
  return (
    <section
      id="competition"
      className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] overflow-hidden"
    >
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={!collapsed}
        aria-controls="competition-body"
        data-print-hide="true"
        className="w-full px-5 py-3 border-b border-[var(--color-border)] bg-[var(--color-bg)]/40 flex items-center justify-between cursor-pointer select-none text-left"
      >
        <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">
          Competition
        </h3>
        <div className="flex items-center gap-2">
          {stat && (
            <span className="text-[11px] font-mono text-[var(--color-text-muted)]">
              {stat}
            </span>
          )}
          <svg
            className={`w-4 h-4 text-[var(--color-text-muted)] transition-transform ${collapsed ? "" : "rotate-180"}`}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
          </svg>
        </div>
      </button>
      {!collapsed && (
        <div id="competition-body" className="p-5 space-y-3">
          {children}
        </div>
      )}
    </section>
  );
}

function EmptyNeverExtracted() {
  return (
    <p className="text-[11px] text-[var(--color-text-muted)] leading-relaxed">
      No competition extracted yet.{" "}
      <Link
        href="/filings"
        className="text-[var(--color-primary)] hover:underline font-medium"
      >
        Open the Filings page
      </Link>
      {" "}and run &ldquo;Extract competition&rdquo; on the latest 10-K.
    </p>
  );
}

function EmptyNoSegments() {
  return (
    <p className="text-[11px] text-[var(--color-text-muted)] leading-relaxed">
      Latest 10-K disclosed no structured competition information.
    </p>
  );
}

function SegmentsList({ data }: { data: CompetitionData }) {
  return (
    <div className="space-y-3">
      {data.segments.map((seg, i) => (
        <SegmentBlock key={seg.segment_name + i} segment={seg} defaultOpen={i === 0} />
      ))}
    </div>
  );
}

function SegmentBlock({
  segment,
  defaultOpen,
}: {
  segment: CompetitionData["segments"][number];
  defaultOpen: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const competitorCount = segment.areas.reduce(
    (n, a) => n + a.competitors.length, 0,
  );
  return (
    <div className="rounded border border-[var(--color-border)] bg-[var(--color-bg)]/40 overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="w-full px-3 py-2 flex items-center justify-between text-left"
      >
        <div className="flex flex-col gap-0.5">
          <span className="text-[12px] font-semibold text-[var(--color-text-primary)]">
            {segment.segment_name}
          </span>
          <span className="text-[10px] text-[var(--color-text-muted)]">
            {segment.areas.length} area{segment.areas.length !== 1 ? "s" : ""} · {competitorCount} competitor{competitorCount !== 1 ? "s" : ""}
          </span>
        </div>
        <svg
          className={`w-3.5 h-3.5 text-[var(--color-text-muted)] transition-transform ${open ? "rotate-180" : ""}`}
          fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      {open && (
        <div className="px-3 pb-3 space-y-2.5">
          <p className="text-[11px] text-[var(--color-text-muted)] leading-relaxed italic">
            {segment.narrative}
          </p>
          {segment.areas.map((area, j) => (
            <AreaBlock key={area.area_of_competition + j} area={area} />
          ))}
        </div>
      )}
    </div>
  );
}

function AreaBlock({ area }: { area: CompetitionData["segments"][number]["areas"][number] }) {
  return (
    <div className="space-y-1.5">
      <div className="text-[10px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
        {area.area_of_competition}
      </div>
      <div className="flex flex-wrap gap-1.5">
        {area.competitors.length === 0 ? (
          <span className="text-[10px] text-[var(--color-text-muted)] italic">
            no competitors named
          </span>
        ) : (
          area.competitors.map((c, k) => (
            <Chip key={c.name + k} chip={c} />
          ))
        )}
      </div>
    </div>
  );
}

function Chip({ chip }: { chip: CompetitorChip }) {
  const tickerLabel = chip.ticker ? ` $${chip.ticker}` : "";
  const tooltip = chip.verbatim_quote ?? undefined;

  if (chip.tracked && chip.ticker) {
    return (
      <Link
        href={`/pipeline/new?ticker=${encodeURIComponent(chip.ticker)}`}
        title={tooltip}
        className="inline-flex items-center gap-1 rounded border border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-0.5 text-[11px] hover:border-[var(--color-accent)] hover:text-[var(--color-accent)] transition"
      >
        <span>{chip.name}</span>
        <span className="font-mono text-[10px] text-[var(--color-text-muted)]">
          {tickerLabel}
        </span>
        <span className="text-[10px]">↗</span>
      </Link>
    );
  }
  return (
    <span
      title={tooltip}
      className="inline-flex items-center gap-1 rounded border border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-0.5 text-[11px] text-[var(--color-text-primary)]"
    >
      <span>{chip.name}</span>
      {chip.ticker && (
        <span className="font-mono text-[10px] text-[var(--color-text-muted)]">
          {tickerLabel}
        </span>
      )}
    </span>
  );
}

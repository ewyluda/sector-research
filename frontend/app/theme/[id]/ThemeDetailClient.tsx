"use client";

import { useState, useMemo, useEffect, useTransition } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import clsx from "clsx";
import type { Theme, DiscoverResponse, CompanySignalCard } from "@/lib/api";
import { fmtMarketCap, fmtPct, fmtScore, themes as themesApi } from "@/lib/api";
import VelocityBadge from "@/components/VelocityBadge";
import SourceBadge from "@/components/SourceBadge";
import ScoreRing from "@/components/ScoreRing";
import { VelocitySparkline } from "@/components/deep-dive/VelocitySparkline";

interface Props {
  theme: Theme;
  initialData: DiscoverResponse | null;
}

type SortKey = "combined_score" | "fundamental_quality_score" | "market_cap" | "x_velocity";
type FilterKey = "all" | "surprise" | "researched" | "accelerating";

// ── Company row in the left panel ─────────────────────────────────────────────
function CompanyRow({
  card,
  selected,
  onClick,
}: {
  card: CompanySignalCard;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={clsx(
        "w-full text-left px-4 py-3 border-b border-[var(--border)] transition-colors cursor-pointer",
        selected
          ? "bg-[var(--accent-bg)] border-l-2 border-l-[var(--primary)]"
          : "hover:bg-[var(--surface-alt)]"
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="font-mono font-semibold text-sm text-[var(--primary-dk)]">
              ${card.ticker}
            </span>
            {card.is_surprise && (
              <span className="text-[10px] font-bold text-amber-400 bg-amber-500/15 border border-amber-500/30 rounded-full px-1.5 py-0.5">
                ⚡ Surprise
              </span>
            )}
            {card.is_seed && (
              <span className="text-[10px] text-[var(--text-faint)] border border-[var(--border)] rounded-full px-1.5 py-0.5">
                seed
              </span>
            )}
          </div>
          <p className="text-xs text-[var(--text-muted)] truncate mt-0.5">{card.company_name}</p>
        </div>
        <ScoreRing score={card.combined_score} size={36} />
      </div>

      <div className="flex items-center gap-2 mt-2">
        <VelocityBadge signal={card.x_signal} compact />
        <span className="text-[10px] text-[var(--text-faint)]">{fmtMarketCap(card.market_cap)}</span>
      </div>
    </button>
  );
}

// ── Metric row in the right panel ─────────────────────────────────────────────
function MetricRow({
  label,
  value,
  tier,
}: {
  label: string;
  value: string;
  tier?: 1 | 2;
}) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-[var(--border)]">
      <span className="text-xs text-[var(--text-muted)]">{label}</span>
      <div className="flex items-center gap-2">
        <span className="text-xs font-medium text-[var(--text)]">{value}</span>
        {tier === 2 && (
          <span className="text-[9px] text-[var(--warning)] border border-[var(--warning)]/30 rounded px-1">
            T2
          </span>
        )}
      </div>
    </div>
  );
}

// ── Right panel — expanded company view ───────────────────────────────────────
function CompanyDetail({ card, themeId }: { card: CompanySignalCard; themeId: string }) {
  return (
    <div className="h-full overflow-y-auto p-5 space-y-5">
      {/* Header */}
      <div>
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-[var(--text)]">{card.company_name}</h2>
            <p className="text-sm text-[var(--text-muted)] font-mono">${card.ticker}</p>
          </div>
          <ScoreRing score={card.combined_score} size={52} label="signal" />
        </div>
        <div className="flex flex-wrap gap-2 mt-3">
          <SourceBadge badge={card.signal_source_badge} />
          <VelocityBadge signal={card.x_signal} />
          {card.is_surprise && (
            <span className="text-xs font-semibold text-amber-400 bg-amber-500/15 border border-amber-500/30 rounded-full px-2.5 py-1">
              ⚡ Surprise Signal
            </span>
          )}
          {card.insider && card.insider.modifier !== 0 && (
            <span
              className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${
                card.insider.modifier > 0
                  ? "bg-emerald-900/40 text-emerald-300"
                  : "bg-amber-900/40 text-amber-300"
              }`}
              title={`Combined score ${card.insider.modifier > 0 ? "+" : ""}${card.insider.modifier} from 90-day insider activity (${card.insider.buy_count} buys / ${card.insider.sell_count} sells)`}
            >
              {card.insider.modifier > 0 ? "Insider buying" : "Insider selling"}
            </span>
          )}
        </div>
      </div>

      {/* FMP metrics */}
      <div>
        <h3 className="text-xs font-semibold text-[var(--text-faint)] uppercase tracking-wide mb-2">
          Fundamentals
        </h3>
        <div className="rounded-lg border border-[var(--border)] overflow-hidden">
          <MetricRow label="Market Cap" value={fmtMarketCap(card.market_cap)} tier={1} />
          <MetricRow label="Revenue Growth YoY" value={fmtPct(card.fmp.revenue_growth_yoy)} tier={1} />
          <MetricRow label="Gross Margin" value={fmtPct(card.fmp.gross_margin)} tier={1} />
          <MetricRow label="ROIC" value={fmtPct(card.fmp.roic)} tier={1} />
          <MetricRow label="P/E Ratio" value={card.fmp.pe_ratio ? card.fmp.pe_ratio.toFixed(1) : "—"} tier={1} />
          <MetricRow label="Fundamental Score" value={fmtScore(card.fundamental_quality_score) + " / 100"} />
        </div>
      </div>

      {/* X Signal */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-xs font-semibold text-[var(--text-faint)] uppercase tracking-wide">
            X Signal
            <span className="ml-1.5 text-[9px] font-normal text-[var(--warning)] border border-[var(--warning)]/30 rounded px-1">
              T2
            </span>
          </h3>
          <VelocitySparkline
            velocity={card.x_signal}
            themeId={themeId}
            ticker={card.ticker}
            days={30}
            width={120}
            height={26}
          />
        </div>
        <div className="rounded-lg border border-[var(--border)] overflow-hidden">
          <MetricRow label="Velocity direction" value={card.x_signal.direction} />
          <MetricRow label="7d/30d ratio" value={card.x_signal.ratio?.toFixed(2) ?? "—"} />
          <MetricRow label="Discovery score" value={card.x_signal.discovery_score.toFixed(3)} />
        </div>
        {card.x_signal.narrative_summary && (
          <p className="mt-2 text-xs text-[var(--text-muted)] bg-[var(--surface-alt)] rounded-lg p-3 leading-relaxed">
            {card.x_signal.narrative_summary}
          </p>
        )}
      </div>

      {/* Prior research */}
      {card.last_run_id && (
        <div>
          <h3 className="text-xs font-semibold text-[var(--text-faint)] uppercase tracking-wide mb-2">
            Last Research Run
          </h3>
          <div className="rounded-lg border border-[var(--border)] p-3 flex items-center justify-between">
            <div>
              <span
                className={clsx(
                  "text-xs font-semibold",
                  card.last_thesis_status === "ON TRACK" && "text-[var(--success)]",
                  card.last_thesis_status === "DRIFTING" && "text-amber-600",
                  card.last_thesis_status === "BROKEN" && "text-red-400"
                )}
              >
                {card.last_thesis_status}
              </span>
              <p className="text-[11px] text-[var(--text-faint)] mt-0.5">
                Conviction: {card.last_conviction_score ?? "—"} / 100
              </p>
            </div>
            <Link
              href={`/pipeline/${card.last_run_id}`}
              className="text-xs text-[var(--primary)] hover:underline"
            >
              View report →
            </Link>
          </div>
        </div>
      )}

      {/* Citations */}
      {card.citations.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold text-[var(--text-faint)] uppercase tracking-wide mb-2">
            Sources
          </h3>
          <ul className="space-y-1">
            {card.citations.map((c, i) => (
              <li key={i} className="flex items-start gap-2 text-[11px]">
                <span
                  className={clsx(
                    "shrink-0 mt-0.5 text-[9px] font-bold rounded px-1 py-0.5",
                    c.tier === 1
                      ? "bg-[var(--accent-bg)] text-[var(--primary-dk)]"
                      : "bg-amber-500/15 text-amber-400 border border-amber-500/30"
                  )}
                >
                  T{c.tier}
                </span>
                <span className="text-[var(--text-muted)]">
                  {c.metric} —{" "}
                  <a
                    href={c.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[var(--primary)] hover:underline"
                  >
                    {c.source_name}
                  </a>
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Run Quick Screen CTA */}
      <div className="pt-2">
        <Link
          href={`/pipeline/new?ticker=${card.ticker}&theme=${themeId}`}
          className="block w-full text-center py-2.5 rounded-lg bg-[var(--primary)] text-white text-sm font-medium hover:bg-[var(--primary-dk)] transition-colors"
        >
          Run Quick Screen →
        </Link>
      </div>
    </div>
  );
}

// ── Tracked-ticker editor ─────────────────────────────────────────────────────
// Optimistic chips + input. Mutations call the atomic add/remove sub-routes;
// on success we router.refresh() so the server component re-fetches the theme
// + discovery data and re-flows everything (is_seed flags, scheduler scope).
function TickerEditor({
  themeId,
  tickers,
  onClose,
}: {
  themeId: string;
  tickers: string[];
  onClose: () => void;
}) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [local, setLocal] = useState<string[]>(tickers);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);

  // Re-sync local state if props change (after a successful refresh).
  useEffect(() => {
    setLocal(tickers);
  }, [tickers]);

  const parseDraft = (raw: string): string[] =>
    raw
      .split(/[\s,]+/)
      .map((t) => t.trim().toUpperCase())
      .filter(Boolean);

  async function handleAdd() {
    const candidates = parseDraft(draft);
    if (candidates.length === 0) return;

    const toAdd = candidates.filter((t) => !local.includes(t));
    if (toAdd.length === 0) {
      setDraft("");
      return;
    }

    setError(null);
    setLocal((prev) => [...prev, ...toAdd]);
    setDraft("");

    // Serial — backend is idempotent on duplicates so this is safe.
    // Track which tickers actually persisted so a mid-loop failure only
    // rolls back the un-persisted tail; the prefix is reconciled by
    // router.refresh() in the finally block.
    const persisted: string[] = [];
    try {
      for (const ticker of toAdd) {
        await themesApi.addTicker(themeId, ticker);
        persisted.push(ticker);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to add ticker");
      const failed = toAdd.filter((t) => !persisted.includes(t));
      setLocal((prev) => prev.filter((t) => !failed.includes(t)));
    } finally {
      startTransition(() => router.refresh());
    }
  }

  async function handleRemove(ticker: string) {
    setError(null);
    setLocal((prev) => prev.filter((t) => t !== ticker));
    try {
      await themesApi.removeTicker(themeId, ticker);
      startTransition(() => router.refresh());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to remove ticker");
      setLocal((prev) => [...prev, ticker]);
    }
  }

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-[var(--text)]">
            Tracked tickers
          </h3>
          <p className="text-xs text-[var(--text-faint)] mt-0.5">
            Seed tickers always appear in discovery results and drive daily
            signal refresh. Removing a ticker preserves its historical signals.
          </p>
        </div>
        <button
          onClick={onClose}
          className="text-xs text-[var(--text-muted)] hover:text-[var(--text)] cursor-pointer"
        >
          Done
        </button>
      </div>

      {/* Chip list */}
      <div className="flex flex-wrap gap-1.5">
        {local.length === 0 ? (
          <span className="text-xs text-[var(--text-faint)] italic">
            No tracked tickers yet — add some below.
          </span>
        ) : (
          local.map((ticker) => (
            <span
              key={ticker}
              className="inline-flex items-center gap-1 text-xs font-mono font-medium text-[var(--primary-dk)] bg-[var(--accent-bg)] border border-[var(--border)] rounded-full pl-2.5 pr-1 py-0.5"
            >
              ${ticker}
              <button
                onClick={() => handleRemove(ticker)}
                disabled={pending}
                aria-label={`Remove ${ticker}`}
                className="ml-0.5 w-4 h-4 inline-flex items-center justify-center rounded-full text-[var(--text-faint)] hover:text-red-400 hover:bg-red-500/15 cursor-pointer disabled:opacity-50"
              >
                ×
              </button>
            </span>
          ))
        )}
      </div>

      {/* Add input */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          handleAdd();
        }}
        className="flex items-center gap-2"
      >
        <input
          type="text"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Add tickers (e.g. NVDA, AMD)"
          className="flex-1 text-xs font-mono bg-[var(--surface-alt)] border border-[var(--border)] rounded-md px-2.5 py-1.5 focus:outline-none focus:border-[var(--primary)]"
        />
        <button
          type="submit"
          disabled={pending || draft.trim().length === 0}
          className="text-xs font-medium px-3 py-1.5 rounded-md bg-[var(--primary)] text-white hover:bg-[var(--primary-dk)] disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
        >
          Add
        </button>
      </form>

      {error && (
        <p className="text-xs text-red-400 bg-red-500/15 border border-red-500/30 rounded-md px-2.5 py-1.5">
          {error}
        </p>
      )}
    </div>
  );
}

// ── Main client component ─────────────────────────────────────────────────────
export default function ThemeDetailClient({ theme, initialData }: Props) {
  const [selectedTicker, setSelectedTicker] = useState<string | null>(
    initialData?.companies[0]?.ticker ?? null
  );
  const [sortBy, setSortBy] = useState<SortKey>("combined_score");
  const [filter, setFilter] = useState<FilterKey>("all");
  const [editingTickers, setEditingTickers] = useState(false);

  const seedTickers = useMemo(
    () =>
      Array.isArray(theme.seed_tickers)
        ? (theme.seed_tickers as string[])
        : [],
    [theme.seed_tickers],
  );

  // Stable reference so the downstream useMemo doesn't re-run on every
  // render when the fallback empty array is the value in play.
  const companies = useMemo(() => initialData?.companies ?? [], [initialData]);

  const filtered = useMemo(() => {
    let list = [...companies];

    if (filter === "surprise") list = list.filter((c) => c.is_surprise);
    if (filter === "researched") list = list.filter((c) => c.last_run_id !== null);
    if (filter === "accelerating") list = list.filter((c) => c.x_signal.direction === "accelerating");

    list.sort((a, b) => {
      if (sortBy === "combined_score") return b.combined_score - a.combined_score;
      if (sortBy === "fundamental_quality_score") return b.fundamental_quality_score - a.fundamental_quality_score;
      if (sortBy === "market_cap") return (b.market_cap ?? 0) - (a.market_cap ?? 0);
      if (sortBy === "x_velocity") return (b.x_signal.ratio ?? 0) - (a.x_signal.ratio ?? 0);
      return 0;
    });

    return list;
  }, [companies, sortBy, filter]);

  const selected = filtered.find((c) => c.ticker === selectedTicker) ?? filtered[0] ?? null;

  const surpriseCount = companies.filter((c) => c.is_surprise).length;
  const acceleratingCount = initialData?.accelerating_count ?? 0;
  const isStale = initialData?.signal_status === "stale";

  const SORT_OPTIONS: { key: SortKey; label: string }[] = [
    { key: "combined_score", label: "Combined score" },
    { key: "fundamental_quality_score", label: "Fundamentals" },
    { key: "x_velocity", label: "X velocity" },
    { key: "market_cap", label: "Market cap" },
  ];

  const FILTER_OPTIONS: { key: FilterKey; label: string }[] = [
    { key: "all", label: `All (${companies.length})` },
    { key: "surprise", label: `⚡ Surprises (${surpriseCount})` },
    { key: "accelerating", label: `↑ Accel. (${acceleratingCount})` },
    { key: "researched", label: "Researched" },
  ];

  return (
    <div className="space-y-4">
      {/* Page header */}
      <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-3">
        <div className="min-w-0">
          <Link href="/themes" className="text-xs text-[var(--text-faint)] hover:text-[var(--text-muted)]">
            ← Themes
          </Link>
          <h1 className="text-xl font-semibold text-[var(--text)] mt-1">{theme.name}</h1>
          {theme.description && (
            <p className="text-sm text-[var(--text-muted)]">{theme.description}</p>
          )}
        </div>

        <div className="shrink-0 self-start flex items-center gap-2">
          {!editingTickers && (
            <button
              onClick={() => setEditingTickers(true)}
              className="inline-flex items-center gap-1.5 text-xs font-medium text-[var(--text-muted)] border border-[var(--border)] rounded-lg px-3 py-2 hover:border-[var(--primary)] hover:text-[var(--text)] cursor-pointer whitespace-nowrap"
            >
              <span>✎</span> Edit tickers ({seedTickers.length})
            </button>
          )}
          {/* Signal status — stacks below header on small screens, floats right on md+ */}
          {isStale && (
            <div className="inline-flex items-center gap-2 text-xs text-[var(--warning)] bg-amber-500/15 border border-amber-500/30 rounded-lg px-3 py-2 whitespace-nowrap">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-500 shrink-0" />
              Signal data stale — last updated &gt;36h ago
            </div>
          )}
        </div>
      </div>

      {editingTickers && (
        <TickerEditor
          themeId={theme.id}
          tickers={seedTickers}
          onClose={() => setEditingTickers(false)}
        />
      )}

      {/* Two-panel layout — stacks vertically below lg breakpoint */}
      <div className="flex flex-col lg:flex-row gap-4 lg:h-[calc(100vh-180px)] lg:min-h-[600px]">
        {/* LEFT: Company list */}
        <div className="w-full lg:w-[340px] lg:shrink-0 flex flex-col rounded-xl border border-[var(--border)] bg-[var(--surface)] overflow-hidden max-h-[70vh] lg:max-h-none">
          {/* Filters + sort */}
          <div className="px-3 py-2.5 border-b border-[var(--border)] space-y-2">
            {/* Filter chips */}
            <div className="flex flex-wrap gap-1">
              {FILTER_OPTIONS.map(({ key, label }) => (
                <button
                  key={key}
                  onClick={() => setFilter(key)}
                  className={clsx(
                    "text-[11px] px-2.5 py-1 rounded-full border transition-colors cursor-pointer",
                    filter === key
                      ? "bg-[var(--primary)] text-white border-[var(--primary)]"
                      : "text-[var(--text-muted)] border-[var(--border)] hover:border-[var(--primary)]/50"
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
            {/* Sort */}
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as SortKey)}
              className="w-full text-xs text-[var(--text-muted)] bg-[var(--surface-alt)] border border-[var(--border)] rounded-md px-2 py-1.5 focus:outline-none focus:border-[var(--primary)]"
            >
              {SORT_OPTIONS.map(({ key, label }) => (
                <option key={key} value={key}>Sort: {label}</option>
              ))}
            </select>
          </div>

          {/* Company rows */}
          <div className="flex-1 overflow-y-auto">
            {filtered.length === 0 ? (
              <div className="py-12 text-center text-xs text-[var(--text-faint)]">
                No companies match the current filter.
              </div>
            ) : (
              filtered.map((card) => (
                <CompanyRow
                  key={card.ticker}
                  card={card}
                  selected={selected?.ticker === card.ticker}
                  onClick={() => setSelectedTicker(card.ticker)}
                />
              ))
            )}
          </div>
        </div>

        {/* RIGHT: Expanded company detail */}
        <div className="flex-1 rounded-xl border border-[var(--border)] bg-[var(--surface)] overflow-hidden">
          {selected ? (
            <CompanyDetail card={selected} themeId={theme.id} />
          ) : (
            <div className="h-full flex items-center justify-center text-xs text-[var(--text-faint)]">
              Select a company to view details
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * Page — Create Theme (/theme/new)
 * Minimal form → POST /api/themes → redirect to /theme/{newId}.
 */
"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { themes as themesApi } from "@/lib/api";

const DEFAULT_WEIGHTS = {
  x_velocity: 0.40,
  fundamental_quality: 0.40,
  discovery: 0.20,
};

const SCREENER_PLACEHOLDER = `{
  "market_cap_more_than": 1000000000,
  "sector": "Technology",
  "limit": 50
}`;

function parseTickers(raw: string): string[] {
  return raw
    .split(/[\s,]+/)
    .map((t) => t.trim().toUpperCase())
    .filter(Boolean);
}

function parseLines(raw: string): string[] {
  return raw
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

export default function NewThemePage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [seedTickersRaw, setSeedTickersRaw] = useState("");
  const [xSearchTermsRaw, setXSearchTermsRaw] = useState("");
  const [screenerRaw, setScreenerRaw] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setError(null);

    let screenerCriteria: Record<string, unknown> = {};
    if (screenerRaw.trim()) {
      try {
        const parsed = JSON.parse(screenerRaw);
        if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
          throw new Error("Screener criteria must be a JSON object");
        }
        screenerCriteria = parsed as Record<string, unknown>;
      } catch (err) {
        setError(
          err instanceof Error
            ? `Screener criteria is not valid JSON: ${err.message}`
            : "Screener criteria is not valid JSON"
        );
        return;
      }
    }

    setSubmitting(true);
    try {
      const created = await themesApi.create({
        name: name.trim(),
        description: description.trim() || null,
        parent_theme_id: null,
        seed_tickers: parseTickers(seedTickersRaw),
        screener_criteria: screenerCriteria,
        x_search_terms: parseLines(xSearchTermsRaw),
        signal_weights: DEFAULT_WEIGHTS,
      });
      router.push(`/theme/${created.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create theme");
      setSubmitting(false);
    }
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <Link
          href="/themes"
          className="text-xs text-[var(--text-muted)] hover:text-[var(--primary)] transition-colors"
        >
          ← Back to themes
        </Link>
        <h1 className="text-xl font-semibold text-[var(--text)] mt-2">
          New theme
        </h1>
        <p className="text-sm text-[var(--text-muted)] mt-0.5">
          Define the discovery universe for a thematic investment idea.
        </p>
      </div>

      {/* Form */}
      <form
        onSubmit={handleSubmit}
        className="space-y-5 rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6"
      >
        {/* Name */}
        <div>
          <label
            htmlFor="name"
            className="block text-[11px] font-medium text-[var(--text-muted)] uppercase tracking-wide mb-1.5"
          >
            Name <span className="text-[var(--error)]">*</span>
          </label>
          <input
            id="name"
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="AI Power Infrastructure"
            required
            maxLength={256}
            className="w-full px-3 py-2 rounded-lg bg-[var(--surface-alt)] border border-[var(--border)]
                       text-sm text-[var(--text)] placeholder-[var(--text-faint)]
                       focus:outline-none focus:border-[var(--primary)]
                       transition-colors"
          />
        </div>

        {/* Description */}
        <div>
          <label
            htmlFor="description"
            className="block text-[11px] font-medium text-[var(--text-muted)] uppercase tracking-wide mb-1.5"
          >
            Description
          </label>
          <textarea
            id="description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="One or two sentences on the thesis behind this theme."
            rows={3}
            className="w-full px-3 py-2 rounded-lg bg-[var(--surface-alt)] border border-[var(--border)]
                       text-sm text-[var(--text)] placeholder-[var(--text-faint)]
                       focus:outline-none focus:border-[var(--primary)]
                       transition-colors resize-y"
          />
        </div>

        {/* Seed tickers */}
        <div>
          <label
            htmlFor="seedTickers"
            className="block text-[11px] font-medium text-[var(--text-muted)] uppercase tracking-wide mb-1.5"
          >
            Seed tickers
          </label>
          <input
            id="seedTickers"
            type="text"
            value={seedTickersRaw}
            onChange={(e) => setSeedTickersRaw(e.target.value)}
            placeholder="NVDA, VST, CEG, TLN"
            className="w-full px-3 py-2 rounded-lg bg-[var(--surface-alt)] border border-[var(--border)]
                       text-sm font-mono text-[var(--text)] placeholder-[var(--text-faint)]
                       focus:outline-none focus:border-[var(--primary)]
                       transition-colors"
          />
          <p className="mt-1 text-[11px] text-[var(--text-faint)]">
            Comma or whitespace separated. Always included in discovery even if the screener misses them.
          </p>
        </div>

        {/* X search terms */}
        <div>
          <label
            htmlFor="xSearchTerms"
            className="block text-[11px] font-medium text-[var(--text-muted)] uppercase tracking-wide mb-1.5"
          >
            X search terms
          </label>
          <textarea
            id="xSearchTerms"
            value={xSearchTermsRaw}
            onChange={(e) => setXSearchTermsRaw(e.target.value)}
            placeholder={"AI datacenter power\nhyperscaler capex\nnatural gas turbines"}
            rows={4}
            className="w-full px-3 py-2 rounded-lg bg-[var(--surface-alt)] border border-[var(--border)]
                       text-sm text-[var(--text)] placeholder-[var(--text-faint)]
                       focus:outline-none focus:border-[var(--primary)]
                       transition-colors resize-y"
          />
          <p className="mt-1 text-[11px] text-[var(--text-faint)]">
            One per line. Used by the daily scheduler to compute X velocity & narrative signals.
          </p>
        </div>

        {/* Screener criteria */}
        <div>
          <label
            htmlFor="screener"
            className="block text-[11px] font-medium text-[var(--text-muted)] uppercase tracking-wide mb-1.5"
          >
            Screener criteria (JSON)
          </label>
          <textarea
            id="screener"
            value={screenerRaw}
            onChange={(e) => setScreenerRaw(e.target.value)}
            placeholder={SCREENER_PLACEHOLDER}
            rows={6}
            spellCheck={false}
            className="w-full px-3 py-2 rounded-lg bg-[var(--code-bg)] border border-[var(--border)]
                       text-xs font-mono text-[var(--text)] placeholder-[var(--text-faint)]
                       focus:outline-none focus:border-[var(--primary)]
                       transition-colors resize-y"
          />
          <p className="mt-1 text-[11px] text-[var(--text-faint)]">
            FMP screener parameters. Supported keys: <code className="text-[var(--primary-dk)]">market_cap_more_than</code>,{" "}
            <code className="text-[var(--primary-dk)]">market_cap_lower_than</code>,{" "}
            <code className="text-[var(--primary-dk)]">sector</code>,{" "}
            <code className="text-[var(--primary-dk)]">industry</code>,{" "}
            <code className="text-[var(--primary-dk)]">exchange</code>,{" "}
            <code className="text-[var(--primary-dk)]">limit</code>.
          </p>
          <p className="mt-1 text-[11px] text-[var(--text-faint)]">
            <strong>Leave empty</strong> to limit discovery to your seed tickers only. FMP&apos;s screener has no semantic understanding of a theme&apos;s intent, so an empty query returns a generic top-N list (LLY, V, NFLX, …) that has nothing to do with the idea — add real filters or leave blank.
          </p>
        </div>

        {/* Error */}
        {error && (
          <div className="rounded-lg border border-[var(--error-border)] bg-[var(--error-bg)] px-4 py-3 text-sm text-[var(--error-text)]">
            {error}
          </div>
        )}

        {/* Footer */}
        <div className="flex items-center justify-between pt-2 border-t border-[var(--border)]">
          <p className="text-[11px] text-[var(--text-faint)]">
            Signal weights default to 40% X velocity · 40% fundamental · 20% discovery. You can tune them later.
          </p>
          <div className="flex items-center gap-2">
            <Link
              href="/themes"
              className="text-sm px-3 py-1.5 rounded-lg text-[var(--text-muted)] hover:text-[var(--text)] hover:bg-[var(--surface-alt)] transition-colors"
            >
              Cancel
            </Link>
            <button
              type="submit"
              disabled={submitting || !name.trim()}
              className="text-sm px-4 py-1.5 rounded-lg bg-[var(--primary)] text-white font-medium
                         hover:bg-[var(--primary-dk)] transition-colors
                         disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {submitting ? "Creating…" : "Create theme"}
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}

"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { pipeline as api } from "@/lib/api";
import type { ReportResponse } from "@/lib/api";
import { CitationList } from "@/components/CitationList";

// ── Helpers ────────────────────────────────────────────────────────────────────

const THESIS_COLORS: Record<string, string> = {
  STRONG_BUY: "bg-emerald-500/15 text-emerald-400 border-emerald-500/25",
  BUY:        "bg-teal-500/15 text-teal-400 border-teal-500/25",
  WATCHLIST:  "bg-amber-500/15 text-amber-400 border-amber-500/25",
  PASS:       "bg-slate-500/15 text-slate-400 border-slate-500/25",
  BROKEN:     "bg-red-500/15 text-red-400 border-red-500/25",
  PENDING:    "bg-[var(--color-surface)] text-[var(--color-text-muted)] border-[var(--color-border)]",
};

const CATEGORY_LABELS: Record<string, string> = {
  business_quality:           "Business Quality",
  financial_health:           "Financial Health",
  growth_earnings:            "Growth & Earnings",
  management_governance:      "Management & Governance",
  technical_market_structure: "Technical & Market Structure",
  macro_regime:               "Macro & Regime",
  sentiment_narrative:        "Sentiment & Narrative",
  risk_assessment:            "Risk Assessment",
  future_durability:          "Future Durability",
};

function SectionCard({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] overflow-hidden">
      <div className="px-5 py-3 border-b border-[var(--color-border)] bg-[var(--color-bg)]/40">
        <h2 className="text-sm font-semibold text-[var(--color-text-primary)] uppercase tracking-wider">
          {title}
        </h2>
      </div>
      <div className="px-5 py-4">{children}</div>
    </div>
  );
}

// ── Obsidian export ────────────────────────────────────────────────────────────

function buildObsidianMd(report: ReportResponse): string {
  const o = report.obsidian;
  const tags = ["research", `theme/${report.theme_id}`, `ticker/${report.ticker.toLowerCase()}`];

  const yaml = `---
ticker: "${o.ticker}"
theme: "${report.theme_id}"
conviction_score: ${o.conviction_score}
thesis_status: "${o.thesis_status}"
phase_reached: "${o.phase_reached}"
date_researched: "${o.date_researched}"
date_updated: "${new Date().toISOString().split("T")[0]}"
loop_count: ${o.loop_count}
tags: [${tags.map((t) => `"${t}"`).join(", ")}]
---`;

  const sections = [
    `# ${o.ticker} Research Report`,
    `\n${yaml}\n`,
    `## Quick Screen\n\n${report.phases.quick_screen?.content ?? "N/A"}`,
    `## Deep Dive\n\n${Object.entries(report.phases.deep_dive ?? {})
      .map(([k, v]) => `### ${CATEGORY_LABELS[k] ?? k}\n\nScore: **${v.score ?? "—"}**\n\n${v.content ?? ""}`)
      .join("\n\n")}`,
    `## Thesis\n\n${report.phases.thesis?.content ?? "N/A"}`,
    `## Risk Stress-Test\n\n${report.phases.risk?.content ?? "N/A"}`,
    `## Position Plan\n\n${report.phases.position?.content ?? "N/A"}`,
  ];

  return sections.join("\n\n");
}

function downloadObsidian(report: ReportResponse) {
  const md = buildObsidianMd(report);
  const blob = new Blob([md], { type: "text/markdown" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${report.ticker}-${report.obsidian.date_researched}.md`;
  a.click();
  URL.revokeObjectURL(url);
}

// ── Main page ──────────────────────────────────────────────────────────────────

export default function ReportPage() {
  const { runId } = useParams<{ runId: string }>();
  const router = useRouter();
  const [report, setReport] = useState<ReportResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!runId) return;
    api.report(runId)
      .then(setReport)
      .finally(() => setLoading(false));
  }, [runId]);

  if (loading) {
    return (
      <main className="min-h-screen bg-[var(--color-bg)] flex items-center justify-center">
        <div className="w-6 h-6 rounded-full border-2 border-[var(--color-accent)] border-t-transparent animate-spin" />
      </main>
    );
  }

  if (!report) {
    return (
      <main className="min-h-screen bg-[var(--color-bg)] flex items-center justify-center">
        <p className="text-[var(--color-text-muted)]">Report not found.</p>
      </main>
    );
  }

  const ddCategories = Object.entries(report.phases.deep_dive ?? {});

  return (
    <main className="min-h-screen bg-[var(--color-bg)] py-10 px-6">
      <div className="max-w-4xl mx-auto space-y-6">

        {/* Top bar */}
        <div className="flex items-start justify-between gap-4">
          <div>
            <button
              onClick={() => router.back()}
              className="text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] mb-3 transition-colors"
            >
              ← Back
            </button>
            <div className="flex items-center gap-3">
              <h1 className="text-3xl font-mono font-bold text-[var(--color-text-primary)] tracking-wide">
                {report.ticker}
              </h1>
              <span
                className={`px-3 py-1 rounded-full border text-xs font-semibold ${
                  THESIS_COLORS[report.thesis_status] ?? THESIS_COLORS.PENDING
                }`}
              >
                {report.thesis_status}
              </span>
            </div>
            <p className="text-sm text-[var(--color-text-muted)] mt-1">
              Theme: {report.theme_id} · Run ID: <span className="font-mono text-xs">{runId}</span>
            </p>
          </div>

          {/* Actions */}
          <div className="flex gap-2 flex-shrink-0">
            <button
              onClick={() => downloadObsidian(report)}
              className="px-4 py-2 rounded-lg bg-[var(--color-surface)] border border-[var(--color-border)]
                         text-sm text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]
                         transition-colors font-medium"
            >
              ↓ Export Obsidian
            </button>
            <button
              onClick={() => router.push("/library")}
              className="px-4 py-2 rounded-lg bg-[var(--color-accent)] text-white text-sm font-semibold
                         hover:bg-[var(--color-accent)]/90 transition-colors"
            >
              Library
            </button>
          </div>
        </div>

        {/* Score row */}
        <div className="grid grid-cols-4 gap-3">
          {[
            { label: "Conviction",    value: String(report.conviction_score), accent: true },
            { label: "Loop Count",    value: String(report.loop_count) },
            { label: "Phase Reached", value: report.obsidian.phase_reached.replace(/_/g, " ") },
            { label: "Date",          value: report.obsidian.date_researched },
          ].map(({ label, value, accent }) => (
            <div
              key={label}
              className="rounded-lg bg-[var(--color-surface)] border border-[var(--color-border)] p-4"
            >
              <p className="text-xs text-[var(--color-text-muted)] uppercase tracking-wider mb-1">
                {label}
              </p>
              <p className={`text-xl font-semibold font-mono ${accent ? "text-[var(--color-accent)]" : "text-[var(--color-text-primary)]"}`}>
                {value}
              </p>
            </div>
          ))}
        </div>

        {/* Flags */}
        {report.flags.length > 0 && (
          <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-4">
            <p className="text-xs font-semibold text-amber-400 uppercase tracking-wider mb-2">
              Flagged during analysis
            </p>
            <ul className="space-y-1">
              {report.flags.map((f, i) => (
                <li key={i} className="text-sm text-[var(--color-text-secondary)]">· {f}</li>
              ))}
            </ul>
          </div>
        )}

        {/* Quick Screen */}
        <SectionCard title="Phase 1 · Quick Screen">
          <p className="text-sm text-[var(--color-text-secondary)] whitespace-pre-wrap leading-relaxed">
            {report.phases.quick_screen?.content || "—"}
          </p>
          <CitationList citations={report.phases.quick_screen?.citations ?? []} />
        </SectionCard>

        {/* Deep Dive */}
        {ddCategories.length > 0 && (
          <SectionCard title="Phase 3 · Deep Dive">
            <div className="space-y-5">
              {ddCategories.map(([key, cat]) => (
                <div key={key} className="border-b border-[var(--color-border)] last:border-0 pb-5 last:pb-0">
                  <div className="flex items-center justify-between mb-2">
                    <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">
                      {CATEGORY_LABELS[key] ?? key}
                    </h3>
                    {cat.score != null && (
                      <span
                        className={`text-sm font-mono font-semibold px-2 py-0.5 rounded ${
                          cat.__type__ === "CategoryError"
                            ? "bg-red-500/10 text-red-400"
                            : cat.score >= 70
                            ? "bg-emerald-500/10 text-emerald-400"
                            : cat.score >= 50
                            ? "bg-amber-500/10 text-amber-400"
                            : "bg-red-500/10 text-red-400"
                        }`}
                      >
                        {cat.__type__ === "CategoryError" ? "ERR" : cat.score}
                      </span>
                    )}
                  </div>
                  {cat.__type__ === "CategoryError" ? (
                    <p className="text-sm text-red-400">{cat.reason}</p>
                  ) : (
                    <>
                      <p className="text-sm text-[var(--color-text-secondary)] whitespace-pre-wrap leading-relaxed">
                        {cat.content}
                      </p>
                      {cat.key_findings?.length > 0 && (
                        <ul className="mt-2 space-y-0.5">
                          {cat.key_findings.map((f, i) => (
                            <li key={i} className="text-xs text-[var(--color-text-muted)]">
                              · {f}
                            </li>
                          ))}
                        </ul>
                      )}
                      <CitationList citations={cat.citations ?? []} />
                    </>
                  )}
                </div>
              ))}
            </div>
          </SectionCard>
        )}

        {/* Thesis */}
        <SectionCard title="Phase 4 · Thesis Construction">
          <p className="text-sm text-[var(--color-text-secondary)] whitespace-pre-wrap leading-relaxed">
            {report.phases.thesis?.content || "—"}
          </p>
          <CitationList citations={report.phases.thesis?.citations ?? []} />
        </SectionCard>

        {/* Risk */}
        <SectionCard title="Phase 5 · Risk Stress-Test">
          <p className="text-sm text-[var(--color-text-secondary)] whitespace-pre-wrap leading-relaxed">
            {report.phases.risk?.content || "—"}
          </p>
          <CitationList citations={report.phases.risk?.citations ?? []} />
        </SectionCard>

        {/* Position */}
        <SectionCard title="Phase 6 · Position Plan">
          <p className="text-sm text-[var(--color-text-secondary)] whitespace-pre-wrap leading-relaxed">
            {report.phases.position?.content || "—"}
          </p>
          <CitationList citations={report.phases.position?.citations ?? []} />
        </SectionCard>

        {/* All citations */}
        {report.citations?.length > 0 && (
          <SectionCard title="All Citations">
            <div className="space-y-2">
              {report.citations.map((c, i) => (
                <div key={i} className="flex items-start gap-3 text-xs">
                  <span className="font-mono text-[var(--color-text-muted)] w-6 flex-shrink-0">
                    [{i + 1}]
                  </span>
                  <div>
                    <a
                      href={c.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="font-medium text-[var(--color-accent)] hover:underline"
                    >
                      {c.source_name}
                    </a>
                    <span className="text-[var(--color-text-muted)] ml-1">
                      · {c.metric} · {c.value}
                    </span>
                    {c.tier === 1 && (
                      <span className="ml-1.5 px-1 rounded bg-[var(--color-accent)]/10 text-[var(--color-accent)]">
                        T1
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </SectionCard>
        )}

        {/* Bottom CTA */}
        <div className="flex gap-3 pb-10">
          <button
            onClick={() => downloadObsidian(report)}
            className="flex-1 py-3 rounded-lg bg-[var(--color-surface)] border border-[var(--color-border)]
                       text-sm font-semibold text-[var(--color-text-primary)] hover:border-[var(--color-accent)]/50 transition-colors"
          >
            ↓ Export to Obsidian (.md)
          </button>
          <button
            onClick={() => router.push("/library")}
            className="flex-1 py-3 rounded-lg bg-[var(--color-accent)] text-white text-sm font-semibold
                       hover:bg-[var(--color-accent)]/90 transition-colors"
          >
            Back to Library
          </button>
        </div>
      </div>
    </main>
  );
}

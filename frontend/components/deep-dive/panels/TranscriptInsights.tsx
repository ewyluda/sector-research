"use client";

import { useState } from "react";
import type { TranscriptAnalysis, TranscriptClaim, TranscriptTension, TranscriptValidation, TranscriptTheme, TranscriptBOMItem } from "@/lib/api";
import { CitationBlock } from "./CitationBlock";

interface TranscriptInsightsProps {
  analysis: TranscriptAnalysis;
  passes: string[];
}

function CollapsibleSection({ title, badge, defaultOpen, children }: { title: string; badge?: React.ReactNode; defaultOpen?: boolean; children: React.ReactNode }) {
  const [open, setOpen] = useState(defaultOpen ?? true);
  return (
    <div className="border border-[var(--color-border)] rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-3 py-2 bg-[var(--color-bg)]/40 hover:bg-[var(--color-bg)]/60 transition-colors cursor-pointer"
      >
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-[var(--color-text-muted)]">{open ? "▾" : "▸"}</span>
          <span className="text-xs font-medium text-[var(--color-text-primary)]">{title}</span>
        </div>
        {badge}
      </button>
      {open && <div className="px-3 py-2 space-y-1.5">{children}</div>}
    </div>
  );
}

function tensionDotColor(type: string): string {
  if (type === "deflected") return "bg-red-400";
  if (type === "reframed") return "bg-amber-400";
  return "bg-yellow-400";
}

function validationBadge(status: string): { bg: string; text: string } {
  if (status === "validated") return { bg: "bg-emerald-500/15 text-emerald-400", text: "Validated" };
  if (status === "missed") return { bg: "bg-red-500/15 text-red-400", text: "Missed" };
  return { bg: "bg-[var(--color-surface-alt)] text-[var(--color-text-faint)]", text: "Unvalidated" };
}

function consistencyPill(status: string): { bg: string; text: string } {
  if (status === "consistent") return { bg: "bg-emerald-500/15 text-emerald-400", text: "Consistent" };
  if (status === "evolved") return { bg: "bg-amber-500/15 text-amber-400", text: "Evolved" };
  return { bg: "bg-red-500/15 text-red-400", text: "Drifted" };
}

function QATensions({ tensions }: { tensions: TranscriptTension[] }) {
  if (tensions.length === 0) return <p className="text-xs text-[var(--color-text-faint)] italic">No tensions detected</p>;
  return (
    <div className="space-y-2">
      {tensions.map((t, i) => (
        <div key={i} className="flex gap-2 items-start">
          <span className={`mt-1.5 w-2 h-2 rounded-full shrink-0 ${tensionDotColor(t.tension_type)}`} />
          <div className="min-w-0">
            <div className="flex items-center gap-1.5">
              <span className="text-xs text-[var(--color-text-primary)]">{t.question_summary}</span>
              <span className="text-[9px] px-1 py-0.5 rounded bg-[var(--color-surface-alt)] text-[var(--color-text-faint)] uppercase shrink-0">
                {t.significance}
              </span>
            </div>
            <CitationBlock source="Earnings Transcript Q&A">&quot;{t.verbatim_excerpt}&quot;</CitationBlock>
          </div>
        </div>
      ))}
    </div>
  );
}

function GuidanceValidation({ validations }: { validations: TranscriptValidation[] }) {
  if (validations.length === 0) return <p className="text-xs text-[var(--color-text-faint)] italic">No prior guidance to validate</p>;
  return (
    <div className="space-y-1.5">
      {validations.map((v, i) => {
        const badge = validationBadge(v.status);
        return (
          <div key={i} className="flex items-start gap-2">
            <span className={`text-[9px] px-1.5 py-0.5 rounded font-medium shrink-0 mt-0.5 ${badge.bg}`}>{badge.text}</span>
            <div className="min-w-0">
              <p className="text-xs text-[var(--color-text-primary)]">{v.claim}</p>
              {(v.delta || v.evidence) && (
                <CitationBlock>{v.delta ? `Delta: ${v.delta}` : ""}{v.delta && v.evidence ? " — " : ""}{v.evidence}</CitationBlock>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function NarrativeConsistency({ themes }: { themes: TranscriptTheme[] }) {
  if (themes.length === 0) return <p className="text-xs text-[var(--color-text-faint)] italic">Insufficient data for consistency analysis</p>;
  return (
    <div className="space-y-1.5">
      {themes.map((t, i) => {
        const pill = consistencyPill(t.status);
        return (
          <div key={i} className="flex items-start gap-2">
            <span className={`text-[9px] px-1.5 py-0.5 rounded font-medium shrink-0 mt-0.5 ${pill.bg}`}>{pill.text}</span>
            <div className="min-w-0">
              <div className="flex items-center gap-1">
                <span className="text-xs text-[var(--color-text-primary)]">{t.theme}</span>
                {t.risk_signal && <span className="text-amber-400 text-[10px]">&#9888;</span>}
              </div>
              <CitationBlock>{t.evidence}</CitationBlock>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function ForwardClaims({ claims }: { claims: TranscriptClaim[] }) {
  if (claims.length === 0) return <p className="text-xs text-[var(--color-text-faint)] italic">No forward-looking claims found</p>;
  return (
    <div className="space-y-1.5">
      {claims.map((c, i) => (
        <div key={i} className="flex items-start gap-2">
          <span className="text-[9px] px-1 py-0.5 rounded bg-[var(--color-surface-alt)] text-[var(--color-text-faint)] uppercase shrink-0 mt-0.5">
            {c.type}
          </span>
          <div className="min-w-0">
            <CitationBlock source={`${c.speaker} ${c.prompted ? "(prompted)" : "(unprompted)"}`}>
              &quot;{c.quote}&quot;
            </CitationBlock>
          </div>
        </div>
      ))}
    </div>
  );
}

function ConfidenceTiers({ data }: { data: { claims_with_tiers: unknown[]; hedging_patterns: string[] } }) {
  const tiers = data.claims_with_tiers as Array<{ claim?: string; quote?: string; tier?: string; confidence?: string }>;
  return (
    <div className="space-y-2">
      {tiers.length > 0 && (
        <div className="space-y-1">
          {tiers.map((c, i) => (
            <div key={i} className="flex items-start gap-2">
              <span className="text-[9px] px-1 py-0.5 rounded bg-[var(--color-surface-alt)] text-[var(--color-text-faint)] uppercase shrink-0 mt-0.5">
                {c.tier ?? c.confidence ?? "?"}
              </span>
              <p className="text-xs text-[var(--color-text-primary)]">{c.claim ?? c.quote ?? JSON.stringify(c)}</p>
            </div>
          ))}
        </div>
      )}
      {data.hedging_patterns.length > 0 && (
        <div>
          <p className="text-[10px] text-[var(--color-text-muted)] uppercase mb-1">Hedging Patterns</p>
          {data.hedging_patterns.map((p, i) => (
            <p key={i} className="text-xs text-[var(--color-text-primary)]">· {p}</p>
          ))}
        </div>
      )}
    </div>
  );
}

function CapexBOM({ commitments }: { commitments: TranscriptBOMItem[] }) {
  if (commitments.length === 0) return <p className="text-xs text-[var(--color-text-faint)] italic">No capex commitments extracted</p>;
  return (
    <div className="space-y-2">
      {commitments.map((c, i) => (
        <div key={i}>
          <p className="text-xs font-medium text-[var(--color-text-primary)]">{c.program} — {c.total_value}</p>
          <div className="mt-1 space-y-0.5">
            {c.bom.map((b, j) => (
              <div key={j} className="flex items-center gap-2 text-[11px]">
                <span className="text-[var(--color-text-muted)]">{b.category}</span>
                {b.pct_estimate != null && <span className="text-[var(--color-text-faint)]">{b.pct_estimate}%</span>}
                {b.vendors.length > 0 && <span className="text-[var(--color-text-primary)]">{b.vendors.join(", ")}</span>}
                <span className="text-[9px] px-1 py-0.5 rounded bg-[var(--color-surface-alt)] text-[var(--color-text-faint)] uppercase">
                  {b.confidence}
                </span>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

const PASS_RENDERERS: Record<string, { title: string; render: (analysis: TranscriptAnalysis) => React.ReactNode | null }> = {
  pass3_qa_tensions: {
    title: "Q&A Tensions",
    render: (a) => {
      if (typeof a.pass3_qa_tensions === "string") return null;
      return <QATensions tensions={a.pass3_qa_tensions} />;
    },
  },
  pass4_validation: {
    title: "Guidance Validation",
    render: (a) => {
      if (typeof a.pass4_validation === "string") return null;
      return <GuidanceValidation validations={a.pass4_validation.validations} />;
    },
  },
  pass5_consistency: {
    title: "Narrative Consistency",
    render: (a) => {
      if (typeof a.pass5_consistency === "string") return null;
      return <NarrativeConsistency themes={a.pass5_consistency.themes} />;
    },
  },
  pass1_claims: {
    title: "Forward Claims",
    render: (a) => {
      if (typeof a.pass1_claims === "string") return null;
      return <ForwardClaims claims={a.pass1_claims} />;
    },
  },
  pass2_tiers: {
    title: "Confidence Tiers",
    render: (a) => {
      if (typeof a.pass2_tiers === "string") return null;
      return <ConfidenceTiers data={a.pass2_tiers} />;
    },
  },
  pass6_bom: {
    title: "Capex BOM",
    render: (a) => {
      if (a.pass6_bom == null || typeof a.pass6_bom === "string") return null;
      return <CapexBOM commitments={a.pass6_bom.commitments} />;
    },
  },
};

export function TranscriptInsights({ analysis, passes }: TranscriptInsightsProps) {
  const sections = passes
    .map((key) => ({ key, ...PASS_RENDERERS[key] }))
    .filter((s) => s.render != null);

  if (sections.length === 0) return null;

  return (
    <div className="space-y-2">
      <h4 className="text-[10px] font-medium text-[var(--color-text-muted)] uppercase tracking-wider">Earnings Transcript</h4>
      {sections.map(({ key, title, render }) => {
        const content = render(analysis);
        if (content === null) return null;
        return (
          <CollapsibleSection key={key} title={title} defaultOpen={key === "pass3_qa_tensions"}>
            {content}
          </CollapsibleSection>
        );
      })}
    </div>
  );
}

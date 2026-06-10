"use client";

import type {
  CuratedFinancials,
  QuantFingerprint as QuantFingerprintData,
  PiotroskiComponent,
} from "@/lib/api";

interface QuantFingerprintProps {
  financials: CuratedFinancials | null;
}

// Zone colors are model-defined thresholds, NOT 0-100 score tiers — do not
// swap in scoreColors.ts here.
const ZONE_STYLES: Record<string, string> = {
  safe: "bg-emerald-500/15 text-emerald-400",
  unlikely: "bg-emerald-500/15 text-emerald-400",
  grey: "bg-amber-500/15 text-amber-400",
  caution: "bg-amber-500/15 text-amber-400",
  distress: "bg-red-500/15 text-red-400",
  flag: "bg-red-500/15 text-red-400",
};

function ZonePill({ zone }: { zone: string | null }) {
  if (!zone) return null;
  return (
    <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase ${ZONE_STYLES[zone] ?? ""}`}>
      {zone}
    </span>
  );
}

function PiotroskiCheck({ component }: { component: PiotroskiComponent }) {
  const mark = component.passed === null ? "—" : component.passed ? "✓" : "✗";
  const color =
    component.passed === null
      ? "text-[var(--color-text-muted)]"
      : component.passed
        ? "text-emerald-400"
        : "text-red-400";
  return (
    <div className="flex items-start gap-1.5" title={component.detail}>
      <span className={`font-mono text-xs ${color}`}>{mark}</span>
      <span className="text-[11px] text-[var(--color-text-secondary)]">{component.label}</span>
    </div>
  );
}

function StatTile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-lg border border-[var(--color-border)] px-3 py-2">
      <p className="text-[10px] uppercase tracking-wide text-[var(--color-text-muted)]">{label}</p>
      <p className="text-sm font-semibold text-[var(--color-text-primary)] mt-0.5">{value}</p>
      {hint && <p className="text-[10px] text-[var(--color-text-muted)] mt-0.5">{hint}</p>}
    </div>
  );
}

function fmtPct(v: number | null, digits = 1): string {
  return v === null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(digits)}%`;
}

function ScoreModel({
  title,
  value,
  zone,
  naReason,
}: {
  title: string;
  value: number | null;
  zone: string | null;
  naReason: string | null;
}) {
  return (
    <div className="rounded-lg border border-[var(--color-border)] px-3 py-2">
      <p className="text-[10px] uppercase tracking-wide text-[var(--color-text-muted)]">{title}</p>
      {naReason ? (
        <p className="text-[11px] text-[var(--color-text-muted)] mt-1">n/a — {naReason}</p>
      ) : value === null ? (
        <p className="text-[11px] text-[var(--color-text-muted)] mt-1">insufficient data</p>
      ) : (
        <div className="flex items-center gap-2 mt-0.5">
          <span className="text-sm font-semibold text-[var(--color-text-primary)]">{value.toFixed(2)}</span>
          <ZonePill zone={zone} />
        </div>
      )}
    </div>
  );
}

function SlopeRow({ label, slope, quarters }: { label: string; slope: number | null; quarters: number }) {
  if (slope === null) {
    return (
      <div className="flex items-center justify-between text-[11px]">
        <span className="text-[var(--color-text-secondary)]">{label}</span>
        <span className="text-[var(--color-text-muted)]">— ({quarters}q)</span>
      </div>
    );
  }
  const up = slope > 0;
  const color =
    slope === 0 ? "text-[var(--color-text-muted)]" : up ? "text-emerald-400" : "text-red-400";
  const arrow = slope === 0 ? "→" : up ? "▲" : "▼";
  return (
    <div className="flex items-center justify-between text-[11px]">
      <span className="text-[var(--color-text-secondary)]">{label}</span>
      <span className={color}>
        {arrow} {slope > 0 ? "+" : ""}
        {slope.toFixed(2)} pp/q <span className="text-[var(--color-text-muted)]">({quarters}q)</span>
      </span>
    </div>
  );
}

function slopeProps(fp: QuantFingerprintData, key: "gross" | "operating" | "net") {
  const entry = fp.margin_slopes?.[key];
  return { slope: entry?.slope_pp_per_quarter ?? null, quarters: entry?.quarters ?? 0 };
}

export function QuantFingerprint({ financials }: QuantFingerprintProps) {
  const fp: QuantFingerprintData | null | undefined = financials?.quant_fingerprint;
  if (!fp) return null; // old runs have no fingerprint — render nothing

  return (
    <section
      id="quant_fingerprint"
      className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] overflow-hidden"
    >
      <div className="px-5 py-3 border-b border-[var(--color-border)] bg-[var(--color-bg)]/40">
        <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">Quant Fingerprint</h3>
        <p className="text-[10px] text-[var(--color-text-muted)] mt-0.5">
          Computed deterministically from {fp.meta.quarters_available} quarters (TTM vs prior-TTM) — not AI-generated. Altman Z uses the original 1968 manufacturer formula.
        </p>
      </div>
      <div className="p-5 space-y-5">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* Piotroski */}
          <div className="rounded-lg border border-[var(--color-border)] px-3 py-2">
            <div className="flex items-center justify-between">
              <p className="text-[10px] uppercase tracking-wide text-[var(--color-text-muted)]">Piotroski F-Score</p>
              <span className="text-sm font-semibold text-[var(--color-text-primary)]">
                {fp.piotroski.score}/9
                {fp.piotroski.components_evaluated < 9 && (
                  <span className="text-[10px] text-[var(--color-text-muted)] ml-1">
                    ({fp.piotroski.components_evaluated} evaluated)
                  </span>
                )}
              </span>
            </div>
            <div className="mt-2 space-y-1">
              {fp.piotroski.components.map((c) => (
                <PiotroskiCheck key={c.key} component={c} />
              ))}
              {fp.piotroski.components.length === 0 && (
                <p className="text-[11px] text-[var(--color-text-muted)]">insufficient data</p>
              )}
            </div>
          </div>
          <div className="space-y-4">
            <ScoreModel
              title="Altman Z-Score"
              value={fp.altman_z.z}
              zone={fp.altman_z.zone}
              naReason={fp.altman_z.not_applicable_reason}
            />
            <ScoreModel
              title="Beneish M-Score"
              value={fp.beneish_m.m}
              zone={fp.beneish_m.zone}
              naReason={fp.beneish_m.not_applicable_reason}
            />
          </div>
          {/* Margin slopes */}
          <div className="rounded-lg border border-[var(--color-border)] px-3 py-2">
            <p className="text-[10px] uppercase tracking-wide text-[var(--color-text-muted)] mb-2">
              Margin Trend (OLS slope)
            </p>
            <div className="space-y-1.5">
              <SlopeRow label="Gross" {...slopeProps(fp, "gross")} />
              <SlopeRow label="Operating" {...slopeProps(fp, "operating")} />
              <SlopeRow label="Net" {...slopeProps(fp, "net")} />
            </div>
          </div>
        </div>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <StatTile
            label="Accruals Ratio"
            value={fp.accruals_ratio === null ? "—" : fmtPct(fp.accruals_ratio * 100)}
            hint="(NI − CFO) / avg assets · negative is healthy"
          />
          <StatTile
            label="FCF Conversion"
            value={fp.fcf_conversion === null ? "—" : `${fp.fcf_conversion.toFixed(2)}×`}
            hint="FCF / net income, TTM"
          />
          <StatTile
            label="SBC / Revenue"
            value={fp.sbc.sbc_pct_revenue === null ? "—" : `${fp.sbc.sbc_pct_revenue.toFixed(1)}%`}
            hint="TTM stock comp intensity"
          />
          <StatTile
            label="Share Growth YoY"
            value={fmtPct(fp.sbc.share_growth_yoy_pct)}
            hint="Diluted shares, TTM avg"
          />
        </div>
      </div>
    </section>
  );
}

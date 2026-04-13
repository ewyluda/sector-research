import type { CuratedFinancials, DeepDiveCategoryStructured, CategoryOutput } from "@/lib/api";
import { MixedSection } from "./MixedSection";
import { BetaGauge } from "../charts/BetaGauge";

interface MacroRegimeProps {
  financials: CuratedFinancials | null;
  structured: DeepDiveCategoryStructured | null;
  score: number | null;
  fallback?: CategoryOutput | null;
  isLive?: boolean;
}

export function MacroRegime({ financials, structured, score, fallback, isLive }: MacroRegimeProps) {
  return (
    <MixedSection id="macro_regime" label="Macro & Regime" score={score} structured={structured} fallback={fallback} isLive={isLive}>
      {financials ? (
        <>
          <div className="grid grid-cols-2 gap-2">
            {[
              { label: "Beta", value: financials.beta?.toFixed(2) ?? "—" },
              { label: "Sector", value: financials.sector || "—" },
            ].map((m) => (
              <div key={m.label} className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)]/40 p-2">
                <p className="text-[9px] text-[var(--color-text-muted)] uppercase">{m.label}</p>
                <p className="text-xs font-mono font-semibold text-[var(--color-text-primary)]">{m.value}</p>
              </div>
            ))}
          </div>
          {financials.beta != null && (
            <div>
              <h4 className="text-[10px] font-medium text-[var(--color-text-muted)] uppercase tracking-wider mb-2">Market Sensitivity</h4>
              <BetaGauge beta={financials.beta} />
            </div>
          )}
        </>
      ) : null}
    </MixedSection>
  );
}

import type { CuratedFinancials, DeepDiveCategoryStructured, CategoryOutput, MacroDataPoint, QuarterlyMetric } from "@/lib/api";
import { MixedSection } from "./MixedSection";
import { BetaGauge } from "../charts/BetaGauge";
import { TrendLineChart } from "../charts/TrendLineChart";
import { GroupedBarChart } from "../charts/GroupedBarChart";

interface MacroRegimeProps {
  financials: CuratedFinancials | null;
  structured: DeepDiveCategoryStructured | null;
  score: number | null;
  fallback?: CategoryOutput | null;
  isLive?: boolean;
}

/**
 * Convert MacroDataPoint[] to QuarterlyMetric[] for chart compatibility.
 * FRED returns points oldest-first; TrendLineChart reverses its input (because
 * FMP quarterly data arrives newest-first), so we pre-reverse macro series to
 * land on chronological oldest→newest order after both transforms.
 */
function toQM(points: MacroDataPoint[]): QuarterlyMetric[] {
  return [...points]
    .reverse()
    .map((p) => ({ period: p.date, value: p.value, yoy_growth: null }));
}

function latest(points: MacroDataPoint[] | undefined): string {
  if (!points || points.length === 0) return "—";
  return points[points.length - 1].value.toFixed(2);
}

function MetricCard({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)]/40 p-2">
      <p className="text-[9px] text-[var(--color-text-muted)] uppercase">{label}</p>
      <p className={`text-xs font-mono font-semibold ${color ?? "text-[var(--color-text-primary)]"}`}>{value}</p>
    </div>
  );
}

export function MacroRegime({ financials, structured, score, fallback, isLive }: MacroRegimeProps) {
  const macro = financials?.macro_indicators;
  const spreadLatest = macro?.yield_curve_spread?.length ? macro.yield_curve_spread[macro.yield_curve_spread.length - 1].value : null;
  const spreadColor = spreadLatest != null ? (spreadLatest < 0 ? "text-red-400" : "text-emerald-400") : undefined;

  return (
    <MixedSection id="macro_regime" label="Macro & Regime" score={score} structured={structured} fallback={fallback} isLive={isLive}>
      {financials ? (
        <div className="space-y-4">
          {/* Metric cards */}
          <div className="grid grid-cols-3 gap-2">
            <MetricCard label="Beta" value={financials.beta?.toFixed(2) ?? "—"} />
            <MetricCard label="Sector" value={financials.sector || "—"} />
            <MetricCard label="Fed Funds" value={macro ? `${latest(macro.fed_funds_rate)}%` : "—"} />
            <MetricCard label="10Y Yield" value={macro ? `${latest(macro.treasury_10y)}%` : "—"} />
            <MetricCard label="2Y Yield" value={macro ? `${latest(macro.treasury_2y)}%` : "—"} />
            <MetricCard
              label="Yield Spread"
              value={spreadLatest != null ? `${spreadLatest.toFixed(2)}%` : "—"}
              color={spreadColor}
            />
          </div>

          {/* Beta gauge */}
          {financials.beta != null && (
            <div>
              <h4 className="text-[10px] font-medium text-[var(--color-text-muted)] uppercase tracking-wider mb-2">Market Sensitivity</h4>
              <BetaGauge beta={financials.beta} />
            </div>
          )}

          {macro ? (
            <>
              {/* Interest Rates */}
              {(macro.fed_funds_rate.length > 0 || macro.treasury_10y.length > 0) && (
                <div>
                  <h4 className="text-[10px] font-medium text-[var(--color-text-muted)] uppercase tracking-wider mb-2">Interest Rates</h4>
                  <TrendLineChart
                    lines={[
                      ...(macro.fed_funds_rate.length > 0 ? [{ data: toQM(macro.fed_funds_rate), name: "Fed Funds", color: "#3b82f6" }] : []),
                      ...(macro.treasury_10y.length > 0 ? [{ data: toQM(macro.treasury_10y), name: "10Y", color: "#60a5fa" }] : []),
                      ...(macro.treasury_2y.length > 0 ? [{ data: toQM(macro.treasury_2y), name: "2Y", color: "#a78bfa" }] : []),
                    ]}
                    yAxisSuffix="%"
                    tightDomain
                  />
                </div>
              )}

              {/* Yield Curve Spread */}
              {macro.yield_curve_spread.length > 0 && (
                <div>
                  <h4 className="text-[10px] font-medium text-[var(--color-text-muted)] uppercase tracking-wider mb-2">Yield Curve Spread (10Y-2Y)</h4>
                  <TrendLineChart
                    lines={[{ data: toQM(macro.yield_curve_spread), name: "Spread", color: spreadLatest != null && spreadLatest < 0 ? "#f87171" : "#34d399" }]}
                    yAxisSuffix="%"
                    referenceLine={0}
                  />
                </div>
              )}

              {/* Labor Market */}
              {(macro.unemployment.length > 0 || macro.nonfarm_payrolls.length > 0) && (
                <div>
                  <h4 className="text-[10px] font-medium text-[var(--color-text-muted)] uppercase tracking-wider mb-2">Labor Market</h4>
                  {macro.unemployment.length > 0 && (
                    <TrendLineChart
                      lines={[{ data: toQM(macro.unemployment), name: "Unemployment", color: "#f59e0b" }]}
                      yAxisSuffix="%"
                    />
                  )}
                  {macro.nonfarm_payrolls.length > 0 && (
                    <div className="mt-2">
                      <TrendLineChart
                        lines={[{ data: toQM(macro.nonfarm_payrolls), name: "Nonfarm Payrolls", color: "#60a5fa" }]}
                        yAxisSuffix=""
                        tightDomain
                      />
                    </div>
                  )}
                </div>
              )}

              {/* Inflation & Liquidity */}
              {(macro.cpi.length > 0 || macro.m2_money_supply.length > 0) && (
                <div>
                  <h4 className="text-[10px] font-medium text-[var(--color-text-muted)] uppercase tracking-wider mb-2">Inflation &amp; Liquidity</h4>
                  {macro.cpi.length > 0 && (
                    <TrendLineChart
                      lines={[{ data: toQM(macro.cpi), name: "CPI", color: "#f87171" }]}
                      yAxisSuffix=""
                      tightDomain
                    />
                  )}
                  {macro.m2_money_supply.length > 0 && (
                    <div className="mt-2">
                      <TrendLineChart
                        lines={[{ data: toQM(macro.m2_money_supply), name: "M2 Supply", color: "#a78bfa" }]}
                        yAxisSuffix=""
                        tightDomain
                      />
                    </div>
                  )}
                </div>
              )}

              {/* GDP Growth */}
              {macro.gdp_growth.length > 0 && (
                <div>
                  <h4 className="text-[10px] font-medium text-[var(--color-text-muted)] uppercase tracking-wider mb-2">GDP Growth (Quarterly)</h4>
                  <GroupedBarChart
                    metrics={toQM(macro.gdp_growth)}
                    label="GDP Growth"
                    formatValue={(v) => `${v.toFixed(1)}%`}
                  />
                </div>
              )}
            </>
          ) : null}
        </div>
      ) : null}
    </MixedSection>
  );
}

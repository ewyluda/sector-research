/**
 * Position Plan dashboard for the Position Monitor phase output.
 *
 * Layout (top to bottom):
 *   1. Header — ticker + time horizon badge + position size ring
 *   2. Entry zone card (price range + rationale)
 *   3. Stop loss / invalidation section
 *   4. Add triggers list
 *   5. Monitoring table (metric x cadence x threshold)
 *   6. Exit conditions
 *   7. Citation list footer
 */

import type { PositionMonitorStructured, Citation } from "@/lib/api";
import ScoreRing from "@/components/ScoreRing";
import { CitationList } from "@/components/CitationList";

interface Props {
  structured: PositionMonitorStructured;
  citations?: Citation[];
  ticker: string;
  convictionScore: number | null;
}

export function PositionCard({
  structured,
  citations = [],
  ticker,
  convictionScore,
}: Props) {
  // Use position_size_pct mapped to 0-100 scale for the ring.
  // Typical positions are 1-10%, so scale 5% = 50 on the ring.
  const sizeRingScore = Math.min(100, Math.round(structured.position_size_pct * 10));

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5 flex flex-col gap-4">
      {/* Header row */}
      <div className="flex items-center gap-4 pb-4 border-b border-[var(--border)]">
        <ScoreRing score={sizeRingScore} size={86} label="Size" />
        <div className="flex-1 min-w-0">
          <div className="flex items-baseline gap-3 mb-1">
            <span className="text-2xl font-mono font-bold text-[var(--text)] tracking-wide">
              {ticker}
            </span>
            <span className="text-lg font-mono font-semibold text-[var(--primary)]">
              {structured.position_size_pct.toFixed(1)}%
            </span>
            <span className="px-3 py-0.5 rounded-full border text-[11px] font-semibold tracking-wider bg-[var(--primary)]/10 text-[var(--primary)] border-[var(--primary)]/30">
              {structured.time_horizon.toUpperCase()}
            </span>
          </div>
          <div className="text-xs text-[var(--text-muted)]">
            Position Plan · Entry {structured.entry_price_low}–{structured.entry_price_high}
            {convictionScore !== null && ` · Conviction ${convictionScore}/100`}
          </div>
        </div>
      </div>

      {/* Entry zone */}
      <div
        className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-3.5"
        style={{ borderLeft: "3px solid rgb(34 197 94)" }}
      >
        <div className="text-[10px] uppercase tracking-wider font-semibold text-emerald-400 mb-1.5">
          Entry Zone
        </div>
        <div className="flex items-baseline gap-2 mb-1.5">
          <span className="text-lg font-mono font-bold text-[var(--text)]">
            {structured.entry_price_low}
          </span>
          <span className="text-xs text-[var(--text-faint)]">to</span>
          <span className="text-lg font-mono font-bold text-[var(--text)]">
            {structured.entry_price_high}
          </span>
        </div>
        <div className="text-xs text-[var(--text)] leading-relaxed">
          {structured.entry_rationale}
        </div>
      </div>

      {/* Sizing rationale */}
      <div
        className="rounded-lg border border-[var(--primary)]/20 bg-[var(--primary)]/5 p-3.5"
        style={{ borderLeft: "3px solid var(--primary)" }}
      >
        <div className="text-[10px] uppercase tracking-wider font-semibold text-[var(--primary)] mb-1.5">
          Position Sizing — {structured.position_size_pct.toFixed(1)}% of Portfolio
        </div>
        <div className="text-xs text-[var(--text)] leading-relaxed">
          {structured.sizing_rationale}
        </div>
      </div>

      {/* Stop loss + invalidation */}
      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-lg border border-[var(--error)]/20 bg-[var(--error)]/5 p-3.5">
          <div className="text-[10px] uppercase tracking-wider font-semibold text-[var(--error)] mb-1.5">
            Stop Loss
          </div>
          <div className="text-sm font-mono font-bold text-[var(--text)] mb-1.5">
            {structured.stop_loss_level}
          </div>
          <div className="text-[10px] text-[var(--text-muted)] leading-relaxed">
            {structured.stop_loss_rationale}
          </div>
        </div>
        <div className="rounded-lg border border-[var(--error)]/20 bg-[var(--error)]/5 p-3.5">
          <div className="text-[10px] uppercase tracking-wider font-semibold text-[var(--error)] mb-1.5">
            Invalidation Conditions
          </div>
          <ul className="space-y-1">
            {structured.invalidation_conditions.map((cond, i) => (
              <li key={i} className="text-[10px] text-[var(--text-muted)] leading-relaxed flex gap-1.5">
                <span className="text-[var(--error)] flex-shrink-0">×</span>
                <span>{cond}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      {/* Add triggers */}
      <div>
        <div className="text-[10px] uppercase tracking-wider font-semibold text-[var(--text-faint)] mb-2">
          Add Triggers ({structured.add_triggers.length})
        </div>
        <div className="flex flex-col gap-1.5">
          {structured.add_triggers.map((trigger, i) => (
            <div
              key={i}
              className="rounded-lg border border-[var(--border)] bg-[var(--surface-alt)] px-3 py-2 text-xs text-[var(--text)] flex gap-2"
            >
              <span className="text-emerald-400 flex-shrink-0 font-semibold">+</span>
              <span>{trigger}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Monitoring table */}
      <div>
        <div className="text-[10px] uppercase tracking-wider font-semibold text-[var(--text-faint)] mb-2">
          Monitoring Schedule ({structured.monitoring.length} items)
        </div>
        <div className="rounded-lg border border-[var(--border)] overflow-hidden">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-[var(--surface-alt)]">
                <th className="text-left px-3 py-2 text-[10px] font-semibold text-[var(--text-faint)] uppercase tracking-wider">Metric</th>
                <th className="text-left px-3 py-2 text-[10px] font-semibold text-[var(--text-faint)] uppercase tracking-wider w-24">Cadence</th>
                <th className="text-left px-3 py-2 text-[10px] font-semibold text-[var(--text-faint)] uppercase tracking-wider">Alert Threshold</th>
              </tr>
            </thead>
            <tbody>
              {structured.monitoring.map((item, i) => (
                <tr key={i} className="border-t border-[var(--border)]">
                  <td className="px-3 py-2 text-[var(--text)]">{item.metric}</td>
                  <td className="px-3 py-2">
                    <span className="px-2 py-0.5 rounded-full bg-[var(--primary)]/10 text-[var(--primary)] text-[10px] font-medium">
                      {item.cadence}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-[var(--warning)]">{item.threshold}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Exit conditions */}
      <div>
        <div className="text-[10px] uppercase tracking-wider font-semibold text-[var(--text-faint)] mb-2">
          Exit Conditions
        </div>
        <div className="flex flex-col gap-1.5">
          {structured.exit_conditions.map((cond, i) => (
            <div
              key={i}
              className="rounded-lg border border-[var(--border)] bg-[var(--surface-alt)] px-3 py-2 text-xs text-[var(--text)] flex gap-2"
            >
              <span className="text-[var(--text-faint)] flex-shrink-0 font-semibold">→</span>
              <span>{cond}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Citation footer */}
      <CitationList citations={citations} />
    </div>
  );
}

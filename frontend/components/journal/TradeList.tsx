"use client";

import Link from "next/link";
import { journalApi } from "@/lib/api";
import type { TradeDetail } from "@/lib/api";
import { ReturnCell } from "@/components/performance/ReturnCell";

function runHref(t: TradeDetail): string | null {
  if (!t.linked_outcome) return null;
  return t.linked_outcome.source_type === "research_run"
    ? `/pipeline/${t.linked_outcome.source_id}`
    : `/workspace/${t.linked_outcome.source_id}`;
}

function Row({
  t,
  onEdit,
  onCloseTrade,
  onChanged,
}: {
  t: TradeDetail;
  onEdit: (t: TradeDetail) => void;
  onCloseTrade: (t: TradeDetail) => void;
  onChanged: () => void;
}) {
  const href = runHref(t);
  return (
    <tr className="border-t border-[var(--border)]">
      <td className="px-2 py-1.5 font-semibold">
        {t.ticker}
        {t.direction === "short" && (
          <span className="ml-1 text-[10px] text-amber-400 uppercase">short</span>
        )}
      </td>
      <td className="px-2 py-1.5 text-[var(--text-muted)]">
        {t.entry_date} @ {Number(t.entry_price).toFixed(2)}
      </td>
      <td className="px-2 py-1.5 text-[var(--text-muted)]">
        {t.exit_date ? `${t.exit_date} @ ${Number(t.exit_price).toFixed(2)}` : "open"}
      </td>
      <td className="px-2 py-1.5 text-right">
        <ReturnCell value={t.returns?.return_pct ?? null} />
        {t.returns?.unrealized && (
          <span className="ml-1 text-[10px] text-[var(--text-muted)]">unrlzd</span>
        )}
      </td>
      <td className="px-2 py-1.5 text-right">
        <ReturnCell value={t.returns?.spy_excess_pct ?? null} />
      </td>
      <td className="px-2 py-1.5">
        {href ? (
          <Link href={href} className="text-xs underline decoration-dotted">
            {t.linked_outcome!.verdict}
          </Link>
        ) : (
          <span className="text-xs text-[var(--text-muted)]">—</span>
        )}
      </td>
      <td className="px-2 py-1.5 text-right" data-print-hide="true">
        <span className="inline-flex gap-2 text-xs">
          {t.status === "open" && (
            <button onClick={() => onCloseTrade(t)} className="underline decoration-dotted">
              close
            </button>
          )}
          <button onClick={() => onEdit(t)} className="underline decoration-dotted">
            edit
          </button>
          <button
            onClick={async () => {
              if (!window.confirm(`Delete ${t.ticker} trade?`)) return;
              await journalApi.remove(t.id).catch(() => {});
              onChanged();
            }}
            className="underline decoration-dotted text-rose-400"
          >
            delete
          </button>
        </span>
      </td>
    </tr>
  );
}

export function TradeList({
  trades,
  onEdit,
  onCloseTrade,
  onChanged,
}: {
  trades: TradeDetail[];
  onEdit: (t: TradeDetail) => void;
  onCloseTrade: (t: TradeDetail) => void;
  onChanged: () => void;
}) {
  if (trades.length === 0) {
    return (
      <p className="text-sm text-[var(--text-muted)] py-4">
        No trades logged yet. Decisions you log here get compared against the verdicts that
        motivated them.
      </p>
    );
  }
  const open = trades.filter((t) => t.status === "open");
  const closed = trades.filter((t) => t.status === "closed");
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-[11px] uppercase tracking-wide text-[var(--text-muted)]">
            <th className="px-2 py-1">Ticker</th>
            <th className="px-2 py-1">Entry</th>
            <th className="px-2 py-1">Exit</th>
            <th className="px-2 py-1 text-right">Return</th>
            <th className="px-2 py-1 text-right">vs SPY</th>
            <th className="px-2 py-1">Thesis</th>
            <th className="px-2 py-1" />
          </tr>
        </thead>
        <tbody>
          {[...open, ...closed].map((t) => (
            <Row key={t.id} t={t} onEdit={onEdit} onCloseTrade={onCloseTrade} onChanged={onChanged} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

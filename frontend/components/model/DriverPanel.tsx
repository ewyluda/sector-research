"use client";
import { useState } from "react";
import type { ModelState } from "@/lib/api";
import { driverPath, toWire } from "@/lib/cellPath";
import { DRIVER_GROUPS } from "@/lib/modelVocab";
import { CellRenderer } from "./CellRenderer";

// Drivers surfaced for future use but currently no-op'd by model_balancing.py —
// rendered as muted "n/a" so they read differently from genuinely missing values.
const NOOP_KEYS = new Set(["interest_income_yield", "revolver_rate"]);

export function DriverPanel({
  state, focused, onFocus, onEdit,
}: {
  state: ModelState;
  focused: string | null;
  onFocus: (path: string) => void;
  onEdit: (cellPath: string, value: number | null) => Promise<void>;
}) {
  const periods = state.periods.filter((p) => !p.is_historical);
  const [open, setOpen] = useState(true);
  return (
    <section className="border-b border-[var(--border)] bg-[var(--surface)]">
      <button onClick={() => setOpen(!open)} className="w-full text-left px-6 py-2 text-sm text-[var(--text-muted)] hover:text-[var(--text)]">
        {open ? "▾" : "▸"} Drivers
      </button>
      {open && (
        <div className="px-6 pb-3 overflow-x-auto">
          {DRIVER_GROUPS.map((g) => (
            <div key={g.label} className="mb-3">
              <div className="text-xs uppercase tracking-wide text-[var(--text-muted)] mb-1">{g.label}</div>
              <table className="w-full border-collapse">
                <thead>
                  <tr>
                    <th className="text-left text-xs text-[var(--text-muted)] pr-2 py-0.5">Driver</th>
                    {periods.map((p) => <th key={p.label} className="text-right text-xs text-[var(--text-muted)] px-1 py-0.5">{p.label}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {g.keys.map((k) => (
                    <tr key={k} className="border-t border-[var(--border)]">
                      <td className="text-left text-xs text-[var(--text)] pr-2 py-0.5">{k}</td>
                      {periods.map((p) => {
                        const path = toWire(driverPath(p.label, k));
                        if (NOOP_KEYS.has(k)) {
                          return (
                            <td
                              key={path}
                              className="px-2 py-1 text-right text-sm text-[var(--text-faint)]"
                              title="Surfaced for future use — not consumed by the model engine yet"
                            >
                              n/a
                            </td>
                          );
                        }
                        return <CellRenderer key={path} cell={state.drivers[p.label]?.[k]} cellPath={path}
                                             focused={focused === path} onFocus={onFocus} onCommitEdit={onEdit} />;
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

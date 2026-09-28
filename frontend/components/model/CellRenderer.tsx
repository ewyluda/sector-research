"use client";
import type { ModelCell } from "@/lib/api";
import { formatModelValue, isRateKey } from "@/lib/modelFormat";

const CLS: Record<string, string> = {
  historical:  "bg-[var(--surface-alt)] text-[var(--text-muted)]",
  ai_baseline: "bg-amber-500/10 text-[var(--text)]",
  driver:      "bg-amber-500/20 text-[var(--text)] font-medium",
  computed:    "bg-transparent text-[var(--text)]",
  override:    "border border-[var(--warning)] bg-amber-500/15 text-[var(--warning)]",
};

export function CellRenderer({
  cell, cellPath, valueKey, onFocus, onCommitEdit, focused, editable = true,
}: {
  cell: ModelCell | undefined;
  cellPath: string;
  /** Driver or line-item key; picks the display format. */
  valueKey: string;
  onFocus: (path: string) => void;
  onCommitEdit?: (path: string, value: number | null) => Promise<void>;
  focused: boolean;
  editable?: boolean;
}) {
  const value = cell?.value ?? null;
  const source = cell?.source ?? "computed";
  const ringCls = focused ? "ring-2 ring-[var(--primary)]" : "";
  return (
    <td
      onClick={() => onFocus(cellPath)}
      onDoubleClick={() => {
        if (!editable || !onCommitEdit) return;
        const unit = isRateKey(valueKey) ? "as a fraction, e.g. 0.25 for 25%" : "in raw units, e.g. dollars";
        const v = prompt(`Override value for ${cellPath} (${unit})`, value === null ? "" : String(value));
        if (v === null) return;
        const num = v === "" ? null : Number(v);
        if (v !== "" && Number.isNaN(num)) return;
        void onCommitEdit(cellPath, num);
      }}
      className={`px-2 py-1 text-right text-sm cursor-pointer ${CLS[source] ?? CLS.computed} ${ringCls}`}
    >
      {formatModelValue(valueKey, value)}
    </td>
  );
}

"use client";
import type { ModelCell } from "@/lib/api";

const CLS: Record<string, string> = {
  historical:  "bg-[var(--surface-alt)] text-[var(--text-muted)]",
  ai_baseline: "bg-amber-50 text-[var(--text)]",
  driver:      "bg-amber-100 text-[var(--text)] font-medium",
  computed:    "bg-transparent text-[var(--text)]",
  override:    "border border-[var(--warning)] bg-orange-50 text-[var(--warning)]",
};

export function CellRenderer({
  cell, cellPath, onFocus, onCommitEdit, focused, editable = true,
}: {
  cell: ModelCell | undefined;
  cellPath: string;
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
        const v = prompt(`Override value for ${cellPath}`, value === null ? "" : String(value));
        if (v === null) return;
        const num = v === "" ? null : Number(v);
        if (v !== "" && Number.isNaN(num)) return;
        void onCommitEdit(cellPath, num);
      }}
      className={`px-2 py-1 text-right text-sm cursor-pointer ${CLS[source] ?? CLS.computed} ${ringCls}`}
    >
      {value === null ? "—" : value.toLocaleString(undefined, { maximumFractionDigits: 2 })}
    </td>
  );
}

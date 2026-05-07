"use client";
import type { ModelCell } from "@/lib/api";

const CLS: Record<string, string> = {
  historical:  "bg-slate-800 text-slate-300",
  ai_baseline: "bg-yellow-900/30 text-yellow-100",
  driver:      "bg-yellow-700/40 text-yellow-50",
  computed:    "bg-transparent text-slate-100",
  override:    "border border-orange-400 bg-orange-900/20 text-orange-100",
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
  const ringCls = focused ? "ring-2 ring-blue-400" : "";
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

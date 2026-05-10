"use client";

import { startTransition, useState } from "react";
import { useRouter } from "next/navigation";
import { themes } from "@/lib/api";

type Props = {
  themeId: string;
  themeName: string;
  seedCount: number;
};

export function DeleteThemeButton({ themeId, themeName, seedCount }: Props) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onClick(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    if (busy) return;
    const warning =
      seedCount > 0
        ? `Delete "${themeName}"?\n\nThis removes the theme and all its ${seedCount} ticker${seedCount !== 1 ? "s" : ""}, signals, signal history, surprise alerts, and watchlist entries. Existing research runs will be preserved but unattached from any theme.`
        : `Delete "${themeName}"?`;
    if (!window.confirm(warning)) return;
    setBusy(true);
    setError(null);
    try {
      await themes.delete(themeId);
      startTransition(() => router.refresh());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
      setBusy(false);
    }
  }

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={busy}
      title={error ?? `Delete ${themeName}`}
      aria-label={`Delete ${themeName}`}
      className="absolute top-2 right-2 z-10 rounded-md bg-black/30 hover:bg-[var(--error-text)] text-white/80 hover:text-white text-[11px] leading-none px-1.5 py-1 opacity-0 group-hover:opacity-100 focus:opacity-100 transition-opacity disabled:opacity-50"
    >
      {busy ? "…" : "✕"}
    </button>
  );
}

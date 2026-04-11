import clsx from "clsx";

interface Props {
  badge: "FMP + X Signal" | "FMP Only (X signal pending)";
}

export default function SourceBadge({ badge }: Props) {
  const isFull = badge === "FMP + X Signal";
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 text-[10px] font-medium px-2 py-0.5 rounded-full border",
        isFull
          ? "bg-[var(--accent-bg)] text-[var(--primary-dk)] border-[var(--primary)]/30"
          : "bg-[var(--surface-alt)] text-[var(--text-faint)] border-[var(--border)]"
      )}
    >
      <span className={clsx("w-1.5 h-1.5 rounded-full", isFull ? "bg-[var(--primary)]" : "bg-[var(--text-faint)]")} />
      {badge}
    </span>
  );
}

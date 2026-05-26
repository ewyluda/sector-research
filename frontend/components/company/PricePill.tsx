export function PricePill({
  price,
  change,
  changePct,
  currency,
  delayLabel,
}: {
  price: number | null;
  change: number | null;
  changePct: number | null;
  currency: string | null;
  delayLabel: string;
}) {
  if (price == null) {
    return <span className="text-sm text-[var(--text-muted)]">—</span>;
  }
  const up = (change ?? 0) >= 0;
  const sym = currency === "USD" || currency == null ? "$" : "";
  const tone = up ? "text-[var(--success,#16a34a)]" : "text-[var(--error,#dc2626)]";
  return (
    <div className="flex items-center gap-2">
      <span className="font-mono text-sm font-semibold text-[var(--text)]">
        {sym}
        {price.toFixed(2)}
      </span>
      {change != null && changePct != null && (
        <span className={`rounded px-1.5 py-0.5 font-mono text-xs ${tone}`}>
          {up ? "+" : ""}
          {change.toFixed(2)} ({up ? "+" : ""}
          {changePct.toFixed(2)}%)
        </span>
      )}
      <span className="text-[10px] text-[var(--text-muted)]">{delayLabel}</span>
    </div>
  );
}

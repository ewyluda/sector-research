export function PanelSkeleton() {
  return (
    <div className="animate-pulse space-y-3 p-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)]">
      <div className="h-4 w-24 rounded bg-[var(--color-surface-alt)]" />
      <div className="h-3 w-full rounded bg-[var(--color-surface-alt)]" />
      <div className="h-3 w-3/4 rounded bg-[var(--color-surface-alt)]" />
      <div className="mt-4 space-y-2">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-3 w-full rounded bg-[var(--color-surface-alt)]" />
        ))}
      </div>
    </div>
  );
}

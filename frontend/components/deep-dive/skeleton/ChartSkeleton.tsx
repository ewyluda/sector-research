export function ChartSkeleton({ className = "" }: { className?: string }) {
  return (
    <div className={`animate-pulse rounded-lg bg-[var(--color-surface-alt)] ${className}`}>
      <div className="h-full w-full min-h-[200px]" />
    </div>
  );
}

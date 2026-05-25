import Link from "next/link";

export function EmptyState({
  title,
  message,
  cta,
}: {
  title: string;
  message: string;
  cta?: { href: string; label: string };
}) {
  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-10 text-center">
      <p className="text-sm font-semibold text-[var(--text)]">{title}</p>
      <p className="mt-1 text-sm text-[var(--text-muted)]">{message}</p>
      {cta && (
        <Link
          href={cta.href}
          className="mt-4 inline-block rounded-md bg-[var(--primary)] px-3 py-1.5 text-sm text-white hover:bg-[var(--primary-dk)]"
        >
          {cta.label}
        </Link>
      )}
    </div>
  );
}

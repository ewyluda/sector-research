interface CitationBlockProps {
  children: React.ReactNode;
  source?: string;
}

export function CitationBlock({ children, source }: CitationBlockProps) {
  return (
    <div className="border-l-[3px] border-[var(--color-citation-border)] bg-[var(--color-citation-bg)] rounded-r-md px-2.5 py-1.5 my-1">
      <div className="text-[12px] italic text-[var(--color-text-primary)] leading-snug">{children}</div>
      {source && (
        <p className="text-[9px] uppercase tracking-wider text-[var(--color-citation)] mt-1">
          Source: {source}
        </p>
      )}
    </div>
  );
}

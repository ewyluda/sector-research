import type { DeepDiveFinding } from "@/lib/api";

export function FindingsTable({ findings }: { findings: DeepDiveFinding[] }) {
  return (
    <table className="w-full text-xs">
      <thead>
        <tr className="border-b border-[var(--color-border)]">
          <th className="text-left py-1.5 pr-3 font-medium text-[var(--color-text-muted)] uppercase tracking-wider">Finding</th>
          <th className="text-left py-1.5 font-medium text-[var(--color-text-muted)] uppercase tracking-wider">Evidence</th>
        </tr>
      </thead>
      <tbody>
        {findings.map((f, i) => (
          <tr key={i} className="border-b border-[var(--color-border)] last:border-0">
            <td className="py-2 pr-3 text-[var(--color-text-primary)] leading-snug">{f.finding}</td>
            <td className="py-2 text-[var(--color-text-muted)] leading-snug">{f.evidence}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

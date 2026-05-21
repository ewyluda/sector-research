import type { ProspectusCategoryResult } from "@/lib/api";

function scoreColor(score: number): string {
  if (score >= 76) return "bg-emerald-950 text-emerald-300 border-emerald-800";
  if (score >= 56) return "bg-blue-950 text-blue-300 border-blue-800";
  if (score >= 31) return "bg-amber-950 text-amber-300 border-amber-800";
  return "bg-red-950 text-red-300 border-red-800";
}

export function CategoryCard({ result }: { result: ProspectusCategoryResult }) {
  return (
    <section className="border border-[var(--border)] rounded-lg p-5 bg-[var(--surface)]">
      <header className="flex items-center justify-between mb-3">
        <h3 className="text-lg font-semibold">{result.category}</h3>
        <span className={`text-xs px-2 py-0.5 rounded-full border ${scoreColor(result.score)}`}>
          {result.score}/100
        </span>
      </header>
      {result.key_findings.length > 0 && (
        <ul className="mb-3 list-disc pl-5 text-sm space-y-0.5">
          {result.key_findings.map((kf, i) => <li key={i}>{kf}</li>)}
        </ul>
      )}
      <div className="prose prose-invert prose-sm max-w-none whitespace-pre-wrap text-[var(--text)]">
        {result.content}
      </div>
    </section>
  );
}

import type { TodaySummary } from "@/lib/todayDerive";

const TINT = {
  red: "border-red-500/40 bg-red-500/10 text-red-300",
  amber: "border-amber-500/40 bg-amber-500/10 text-amber-300",
  blue: "border-blue-500/40 bg-blue-500/10 text-blue-300",
} as const;

/** One-line severity summary. Renders nothing when all clear. */
export function SummaryBanner({ summary }: { summary: TodaySummary }) {
  const { alerts, stale, p1Tickers } = summary;
  if (alerts === 0 && stale === 0 && p1Tickers === 0) return null;

  const tone = alerts > 0 ? "red" : stale > 0 ? "amber" : "blue";
  const parts: string[] = [];
  if (alerts > 0) parts.push(`${alerts} triggered/broken ${alerts === 1 ? "thesis" : "theses"}`);
  if (stale > 0) parts.push(`${stale} stale ${stale === 1 ? "thesis" : "theses"}`);
  if (p1Tickers > 0) parts.push(`${p1Tickers} ticker${p1Tickers === 1 ? "" : "s"} with open P1 questions`);

  return (
    <div className={`rounded-lg border px-4 py-2.5 text-sm font-medium ${TINT[tone]}`}>
      <span aria-hidden="true">⚠</span> {parts.join(" · ")}
    </div>
  );
}

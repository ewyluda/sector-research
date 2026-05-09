"use client";
import { useEffect, useState } from "react";
import { getModelVersions, getModelDiff } from "@/lib/api";

type Versions = Awaited<ReturnType<typeof getModelVersions>>["versions"];
type Diff = Awaited<ReturnType<typeof getModelDiff>>;

export function HistoryDiffViewer({ ticker }: { ticker: string }) {
  const [versions, setVersions] = useState<Versions>([]);
  const [a, setA] = useState<number | null>(null);
  const [b, setB] = useState<number | null>(null);
  const [diff, setDiff] = useState<Diff | null>(null);

  useEffect(() => {
    void getModelVersions(ticker).then((r) => {
      setVersions(r.versions);
      if (r.versions.length >= 2) {
        setA(r.versions[1].version);
        setB(r.versions[0].version);
      }
    });
  }, [ticker]);

  useEffect(() => {
    if (a == null || b == null) return;
    void getModelDiff(ticker, b, a).then(setDiff);
  }, [a, b, ticker]);

  return (
    <div className="p-6 text-[var(--text)]">
      <div className="flex gap-3 items-end mb-4">
        <select
          value={a ?? ""}
          onChange={(e) => setA(Number(e.target.value))}
          className="bg-[var(--surface)] border border-[var(--border)] text-[var(--text)] px-2 py-0.5 rounded text-sm"
        >
          {versions.map((v) => (
            <option key={v.version} value={v.version}>
              v{v.version} {v.label ?? ""}
            </option>
          ))}
        </select>
        <span className="text-[var(--text-muted)]">vs</span>
        <select
          value={b ?? ""}
          onChange={(e) => setB(Number(e.target.value))}
          className="bg-[var(--surface)] border border-[var(--border)] text-[var(--text)] px-2 py-0.5 rounded text-sm"
        >
          {versions.map((v) => (
            <option key={v.version} value={v.version}>
              v{v.version} {v.label ?? ""}
            </option>
          ))}
        </select>
      </div>
      {diff && (
        <div className="space-y-3 text-sm">
          <div>
            <span className="text-[var(--text-muted)]">Changed cells:</span> {diff.changed.length}
          </div>
          <table className="w-full text-xs">
            <thead>
              <tr className="text-[var(--text-muted)]">
                <th className="text-left">Cell</th>
                <th className="text-right">Before</th>
                <th className="text-right">After</th>
              </tr>
            </thead>
            <tbody>
              {diff.changed.slice(0, 200).map((c) => (
                <tr key={c.cell_path} className="border-t border-[var(--border)]">
                  <td className="text-left text-[var(--text)]">{c.cell_path}</td>
                  <td className="text-right text-[var(--text-muted)]">
                    {c.before?.value?.toLocaleString(undefined, { maximumFractionDigits: 4 }) ?? "—"}
                  </td>
                  <td className="text-right text-[var(--text)]">
                    {c.after?.value?.toLocaleString(undefined, { maximumFractionDigits: 4 }) ?? "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {diff.changed.length > 200 && (
            <div className="text-[var(--text-muted)]">…showing first 200 changes.</div>
          )}
        </div>
      )}
    </div>
  );
}

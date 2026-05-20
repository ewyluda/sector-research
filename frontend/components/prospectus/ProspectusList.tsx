"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { prospectusApi, type ProspectusReport } from "@/lib/api";
import { VerdictPill } from "./VerdictPill";

const STATUS_LABEL: Record<string, string> = {
  ingesting: "Ingesting",
  analyzing: "Analyzing",
  completed: "Completed",
  failed: "Failed",
};

export function ProspectusList() {
  const [rows, setRows] = useState<ProspectusReport[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    prospectusApi
      .list()
      .then((list) => { if (alive) setRows(list); })
      .catch((e) => { if (alive) setError(e instanceof Error ? e.message : String(e)); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, []);

  if (loading) return <div className="text-[var(--text-muted)] text-sm">Loading…</div>;
  if (error) {
    return (
      <div className="p-4 bg-red-950 border border-red-800 rounded-md text-red-300 text-sm">
        {error}
      </div>
    );
  }
  if (rows.length === 0) {
    return (
      <div className="text-[var(--text-muted)] text-sm">
        No prospectus reports yet. Create one from the Filings page.
      </div>
    );
  }

  return (
    <table className="w-full text-sm">
      <thead className="text-[var(--text-muted)] text-xs uppercase tracking-wider">
        <tr>
          <th className="text-left py-2 px-2">Issuer</th>
          <th className="text-left py-2 px-2">Form</th>
          <th className="text-left py-2 px-2">Status</th>
          <th className="text-left py-2 px-2">Verdict</th>
          <th className="text-left py-2 px-2">Created</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => {
          const verdict = r.step_outputs?.thesis?.ipo_verdict ?? null;
          const formType = r.step_outputs?.ingest?.form_type ?? "S-1";
          return (
            <tr key={r.id} className="border-t border-[var(--border)] hover:bg-[var(--surface)]">
              <td className="py-2 px-2">
                <Link href={`/prospectus/${r.id}`} className="text-blue-400 hover:underline">
                  {r.issuer_name}
                </Link>
              </td>
              <td className="py-2 px-2 text-[var(--text-muted)]">{formType}</td>
              <td className="py-2 px-2 text-[var(--text-muted)]">{STATUS_LABEL[r.status] ?? r.status}</td>
              <td className="py-2 px-2"><VerdictPill verdict={verdict} /></td>
              <td className="py-2 px-2 text-[var(--text-muted)]">
                {r.created_at ? new Date(r.created_at).toLocaleDateString() : "—"}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { prospectusApi } from "@/lib/api";

export function NewProspectusButton() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const { report_id } = await prospectusApi.create({
        url_or_accession: value.trim(),
        theme_id: null,
      });
      router.push(`/prospectus/${report_id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="text-sm px-3 py-1.5 rounded-md border border-[var(--border)] hover:bg-[var(--surface)]"
      >
        + New prospectus report
      </button>

      {open && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onClick={() => setOpen(false)}>
          <div className="bg-[var(--surface)] border border-[var(--border)] rounded-lg p-5 max-w-lg w-full mx-4" onClick={(e) => e.stopPropagation()}>
            <h2 className="text-lg font-semibold mb-2">New prospectus report</h2>
            <p className="text-sm text-[var(--text-muted)] mb-3">
              Paste the SEC URL or accession number of an S-1 / S-1/A filing.
            </p>
            <input
              type="text"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder="https://www.sec.gov/Archives/edgar/data/…/…/….htm"
              className="w-full bg-[var(--bg)] border border-[var(--border)] rounded-md px-3 py-2 text-sm mb-3"
              autoFocus
            />
            {error && (
              <div className="mb-3 p-2 bg-red-950 border border-red-800 rounded-md text-red-300 text-sm">
                {error}
              </div>
            )}
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setOpen(false)} className="text-sm px-3 py-1.5 rounded-md hover:bg-[var(--bg)]">
                Cancel
              </button>
              <button
                type="button"
                onClick={submit}
                disabled={busy || !value.trim()}
                className="text-sm px-3 py-1.5 rounded-md bg-blue-600 text-white hover:bg-blue-500 disabled:opacity-50"
              >
                {busy ? "Starting…" : "Start report"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

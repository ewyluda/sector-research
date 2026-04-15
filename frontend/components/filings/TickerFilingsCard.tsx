"use client";

import { useEffect, useState } from "react";
import { filings } from "@/lib/api";
import type { FilingRecord, FilingIngestSummary } from "@/lib/api";
import SectionReader from "./SectionReader";

interface OpenSection {
  accession: string;
  sectionKey: string;
  heading: string | null;
}

const SECTION_LABEL: Record<string, string> = {
  item_1_business: "Business (Item 1)",
  item_1a_risk_factors: "Risk Factors (Item 1A)",
  item_7_mda: "MD&A (Item 7)",
  item_2_mda_10q: "MD&A (Item 2)",
  def14a_governance: "Corporate Governance",
};

function sectionLabel(key: string): string {
  return SECTION_LABEL[key] ?? key;
}

function fmtDate(iso: string): string {
  const d = new Date(iso + "T00:00:00Z");
  return d.toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" });
}

export default function TickerFilingsCard({ ticker }: { ticker: string }) {
  const [records, setRecords] = useState<FilingRecord[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [ingesting, setIngesting] = useState(false);
  const [ingestMsg, setIngestMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [openSection, setOpenSection] = useState<OpenSection | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const rows = await filings.list(ticker);
      setRecords(rows);
    } catch (e) {
      setError(e instanceof Error ? e.message : "load failed");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ticker]);

  async function onIngest() {
    setIngesting(true);
    setIngestMsg(null);
    setError(null);
    try {
      const result: FilingIngestSummary = await filings.ingestTicker(ticker);
      const added = result.sections_added;
      const skipped = result.sections_skipped_existing;
      if (added === 0 && skipped === 0 && result.errors.length > 0) {
        setIngestMsg(`No sections ingested — ${result.errors[0]}`);
      } else {
        setIngestMsg(
          `Done. ${added} new, ${skipped} already-ingested section${skipped !== 1 ? "s" : ""}.`
        );
      }
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "ingest failed");
    } finally {
      setIngesting(false);
    }
  }

  const withSections = (records ?? []).filter((r) => r.sections.length > 0);
  const hasFilings = withSections.length > 0;

  return (
    <>
      <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4 space-y-3">
        <div className="flex items-start justify-between gap-2">
          <div>
            <div className="font-mono font-semibold text-[var(--primary-dk)] text-sm">
              ${ticker.toUpperCase()}
            </div>
            <div className="text-[11px] text-[var(--text-faint)]">
              {loading
                ? "loading…"
                : hasFilings
                ? `${withSections.length} filing${withSections.length !== 1 ? "s" : ""}`
                : "no sections yet"}
            </div>
          </div>
          <button
            type="button"
            onClick={onIngest}
            disabled={ingesting}
            className="text-[11px] px-2 py-1 rounded-md border border-[var(--border)] text-[var(--text-muted)] hover:bg-[var(--surface-alt)] hover:text-[var(--text)] disabled:opacity-50"
          >
            {ingesting ? "Ingesting…" : "Ingest latest"}
          </button>
        </div>

        {ingestMsg && (
          <div className="text-[11px] text-[var(--text-muted)]">{ingestMsg}</div>
        )}
        {error && (
          <div className="text-[11px] text-red-600">{error}</div>
        )}

        {hasFilings && (
          <div className="space-y-3">
            {withSections.map((f) => (
              <div key={f.id} className="border-t border-[var(--border)] pt-2 space-y-1.5">
                <div className="flex items-center justify-between text-[11px]">
                  <span className="font-medium text-[var(--text)]">{f.form_type}</span>
                  <span className="text-[var(--text-faint)]">{fmtDate(f.filing_date)}</span>
                </div>
                <div className="flex flex-wrap gap-1">
                  {f.sections.map((s) => (
                    <button
                      key={s.section_key}
                      type="button"
                      onClick={() =>
                        setOpenSection({
                          accession: f.accession_number,
                          sectionKey: s.section_key,
                          heading: s.heading,
                        })
                      }
                      className="text-[11px] px-2 py-0.5 rounded bg-[var(--accent-bg)] text-[var(--primary-dk)] hover:bg-[var(--primary)]/15 transition"
                      title={`${s.char_count.toLocaleString()} chars`}
                    >
                      {sectionLabel(s.section_key)}
                    </button>
                  ))}
                </div>
                {f.primary_document_url && (
                  <a
                    href={f.primary_document_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[10px] text-[var(--primary)] hover:underline"
                  >
                    SEC filing ↗
                  </a>
                )}
              </div>
            ))}
          </div>
        )}

        {!loading && !hasFilings && (
          <div className="text-[11px] text-[var(--text-faint)] italic">
            Click "Ingest latest" to fetch the latest 10-K, 10-Q, and DEF 14A.
          </div>
        )}
      </div>

      {openSection && (
        <SectionReader
          ticker={ticker}
          accession={openSection.accession}
          sectionKey={openSection.sectionKey}
          heading={openSection.heading}
          onClose={() => setOpenSection(null)}
        />
      )}
    </>
  );
}

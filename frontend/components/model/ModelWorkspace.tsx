"use client";
import { useEffect, useState } from "react";
import { getModel, initializeModel, type TickerModelVersion, type TickerModelDraft } from "@/lib/api";
import { MODEL_TABS, type ModelTab } from "@/components/model/modelSections";
import { DriverPanel } from "@/components/model/DriverPanel";
import { ForecastGrid } from "@/components/model/ForecastGrid";
import { FormulaBar } from "@/components/model/FormulaBar";
import { putModelDraft, saveModelVersion, discardModelDraft, type ModelState as MS, type TickerModelDraft as TMD, type TickerModelVersion as TMV } from "@/lib/api";
import { ReverseDcfPanel } from "@/components/model/ReverseDcfPanel";
import { HistoryDiffViewer } from "@/components/model/HistoryDiffViewer";

export function ModelWorkspace({ ticker: tickerProp }: { ticker: string }) {
  const ticker = (tickerProp || "").toUpperCase();
  const [tab, setTab] = useState<ModelTab>("forecast");
  const [latest, setLatest] = useState<TickerModelVersion | null>(null);
  const [draft, setDraft] = useState<TickerModelDraft | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    const sync = () => {
      const h = window.location.hash || "#forecast";
      const t = MODEL_TABS.find((x) => x.hash === h);
      if (t) setTab(t.id);
    };
    sync();
    window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, []);

  useEffect(() => {
    if (!ticker) return;
    setLoading(true);
    getModel(ticker)
      .then((r) => {
        setLatest(r.latest_version);
        setDraft(r.draft);
      })
      .catch((e) => setErr(String(e)))
      .finally(() => setLoading(false));
  }, [ticker]);

  async function handleCreate() {
    setLoading(true);
    try {
      const v = await initializeModel(ticker);
      setLatest(v);
    } catch (e) {
      setErr(String(e));
    } finally {
      setLoading(false);
    }
  }

  if (loading) return <div className="p-6 text-[var(--text-muted)]">Loading model…</div>;
  if (err) return <div className="p-6 text-[var(--error)]">Error: {err}</div>;
  if (!latest) {
    return (
      <div className="p-6 space-y-3">
        <h1 className="text-2xl font-semibold text-[var(--text)]">{ticker} — no model yet</h1>
        <button onClick={handleCreate} className="px-3 py-1.5 bg-[var(--primary)] hover:bg-[var(--primary-dk)] rounded text-white">
          Create AI baseline
        </button>
      </div>
    );
  }

  const activeState = draft?.state ?? latest.state;

  return (
    <div className="flex flex-col h-full">
      <header className="border-b border-[var(--border)] bg-[var(--surface)] px-6 py-3 flex items-center gap-4" data-print-hide="true">
        <h1 className="text-xl font-semibold text-[var(--text)]">
          {ticker} <span className="text-[var(--text-muted)] text-sm font-normal">v{latest.version} · {latest.label}</span>
        </h1>
        <nav className="flex gap-1 ml-auto">
          {MODEL_TABS.map((t) => (
            <a
              key={t.id}
              href={t.hash}
              className={`px-3 py-1.5 rounded-md text-sm transition-colors ${
                tab === t.id
                  ? "bg-[var(--accent-bg)] text-[var(--primary-dk)] font-medium"
                  : "text-[var(--text-muted)] hover:text-[var(--text)] hover:bg-[var(--surface-alt)]"
              }`}
            >
              {t.label}
            </a>
          ))}
        </nav>
      </header>
      <main className="flex-1 overflow-auto">
        {tab === "forecast" && (
          <ForecastTabContent
            state={activeState}
            draft={draft}
            latest={latest}
            ticker={ticker}
            onDraftChange={setDraft}
            onSaved={(v: TickerModelVersion) => {
              setLatest(v);
              setDraft(null);
            }}
          />
        )}
        {tab === "reverse-dcf" && <ReverseDcfTabContent ticker={ticker} hasDraft={!!draft} />}
        {tab === "history" && <HistoryTabContent ticker={ticker} />}
      </main>
    </div>
  );
}

function ForecastTabContent({
  state, draft, latest, ticker, onDraftChange, onSaved,
}: {
  state: MS;
  draft: TMD | null;
  latest: TMV;
  ticker: string;
  onDraftChange: (d: TMD | null) => void;
  onSaved: (v: TMV) => void;
}) {
  const [focused, setFocused] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleEdit(cellPath: string, value: number | null) {
    setBusy(true);
    try {
      const updated = await putModelDraft(ticker, { cell_path: cellPath, value });
      onDraftChange(updated);
    } catch (e) {
      alert(String(e));
    } finally {
      setBusy(false);
    }
  }
  async function handleSave() {
    const label = prompt("Version label:", "");
    if (label === null) return;
    setBusy(true);
    try {
      await saveModelVersion(ticker, label || null);
      const r = await import("@/lib/api").then((m) => m.getModel(ticker));
      onSaved(r.latest_version!);
    } finally {
      setBusy(false);
    }
  }
  async function handleDiscard() {
    if (!confirm("Discard draft?")) return;
    setBusy(true);
    try {
      await discardModelDraft(ticker);
      onDraftChange(null);
    } finally {
      setBusy(false);
    }
  }

  // Suppress 'latest' unused warning — kept in props for future cross-version reads.
  void latest;

  return (
    <>
      <FormulaBar state={state} focused={focused} />
      <DriverPanel state={state} focused={focused} onFocus={setFocused} onEdit={handleEdit} />
      <ForecastGrid state={state} focused={focused} onFocus={setFocused} onEdit={handleEdit} />
      <div className="sticky bottom-0 left-0 right-0 bg-[var(--surface)] border-t border-[var(--border)] px-6 py-2 flex gap-2 justify-end" data-print-hide="true">
        <button onClick={handleDiscard} disabled={!draft || busy} className="px-3 py-1 text-sm rounded-md border border-[var(--border)] bg-[var(--surface-alt)] hover:bg-[var(--accent-bg)] text-[var(--text)] disabled:opacity-40">
          Discard draft
        </button>
        <button onClick={handleSave} disabled={!draft || busy} className="px-3 py-1 text-sm rounded-md bg-[var(--primary)] hover:bg-[var(--primary-dk)] disabled:opacity-40 text-white">
          Save Version
        </button>
      </div>
    </>
  );
}
function ReverseDcfTabContent({ ticker, hasDraft }: { ticker: string; hasDraft: boolean }) {
  return <ReverseDcfPanel ticker={ticker} hasDraft={hasDraft} />;
}
function HistoryTabContent({ ticker }: { ticker: string }) {
  return <HistoryDiffViewer ticker={ticker} />;
}

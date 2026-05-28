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
import { EmptyState } from "@/components/company/EmptyState";

export function ModelWorkspace({ ticker: tickerProp }: { ticker: string }) {
  const ticker = (tickerProp || "").toUpperCase();
  const [tab, setTab] = useState<ModelTab>("forecast");
  const [latest, setLatest] = useState<TickerModelVersion | null>(null);
  const [draft, setDraft] = useState<TickerModelDraft | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
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

  async function handleSave() {
    const label = prompt("Version label (optional):", "");
    if (label === null) return;
    setBusy(true);
    try {
      await saveModelVersion(ticker, label || null);
      const r = await getModel(ticker);
      if (r.latest_version) setLatest(r.latest_version);
      setDraft(null);
    } catch (e) {
      alert(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleDiscard() {
    if (!confirm("Discard draft?")) return;
    setBusy(true);
    try {
      await discardModelDraft(ticker);
      setDraft(null);
    } catch (e) {
      alert(String(e));
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <div className="p-6 text-[var(--text-muted)]">Loading model…</div>;
  if (err) return <div className="p-6 text-[var(--error)]">Error: {err}</div>;
  if (!latest) {
    return (
      <EmptyState
        title="No model yet"
        message={`Seed an editable 5-year forecast for ${ticker} from the latest completed research run.`}
        action={{ label: "Create AI baseline", onClick: handleCreate }}
      />
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
      {draft && (
        <div
          data-print-hide="true"
          className="mt-3 mx-6 flex items-center justify-between gap-3 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900"
        >
          <div className="flex items-center gap-2">
            <span className="inline-block h-2 w-2 rounded-full bg-amber-500" aria-hidden />
            <span>
              <strong>Unsaved draft</strong> — workspace runs are blocked until you save or discard.
            </span>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleDiscard}
              disabled={busy}
              className="text-xs px-2 py-1 rounded border border-amber-400 hover:bg-amber-100 disabled:opacity-40"
            >
              Discard
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={busy}
              className="text-xs px-2 py-1 rounded bg-amber-500 text-white hover:bg-amber-600 disabled:opacity-40"
            >
              Save version
            </button>
          </div>
        </div>
      )}
      <main className="flex-1 overflow-auto">
        {tab === "forecast" && (
          <ForecastTabContent
            state={activeState}
            draft={draft}
            latest={latest}
            ticker={ticker}
            busy={busy}
            onDraftChange={setDraft}
            onSave={handleSave}
            onDiscard={handleDiscard}
          />
        )}
        {tab === "reverse-dcf" && <ReverseDcfTabContent ticker={ticker} hasDraft={!!draft} />}
        {tab === "history" && <HistoryTabContent ticker={ticker} />}
      </main>
    </div>
  );
}

function ForecastTabContent({
  state, draft, latest, ticker, busy, onDraftChange, onSave, onDiscard,
}: {
  state: MS;
  draft: TMD | null;
  latest: TMV;
  ticker: string;
  busy: boolean;
  onDraftChange: (d: TMD | null) => void;
  onSave: () => void | Promise<void>;
  onDiscard: () => void | Promise<void>;
}) {
  const [focused, setFocused] = useState<string | null>(null);
  const [editBusy, setEditBusy] = useState(false);

  async function handleEdit(cellPath: string, value: number | null) {
    setEditBusy(true);
    try {
      const updated = await putModelDraft(ticker, { cell_path: cellPath, value });
      onDraftChange(updated);
    } catch (e) {
      alert(String(e));
    } finally {
      setEditBusy(false);
    }
  }

  // Suppress 'latest' unused warning — kept in props for future cross-version reads.
  void latest;

  const disabled = !draft || busy || editBusy;

  return (
    <>
      <FormulaBar state={state} focused={focused} />
      <DriverPanel state={state} focused={focused} onFocus={setFocused} onEdit={handleEdit} />
      <ForecastGrid state={state} focused={focused} onFocus={setFocused} onEdit={handleEdit} />
      <div className="sticky bottom-0 left-0 right-0 bg-[var(--surface)] border-t border-[var(--border)] px-6 py-2 flex gap-2 justify-end" data-print-hide="true">
        <button onClick={onDiscard} disabled={disabled} className="px-3 py-1 text-sm rounded-md border border-[var(--border)] bg-[var(--surface-alt)] hover:bg-[var(--accent-bg)] text-[var(--text)] disabled:opacity-40">
          Discard draft
        </button>
        <button onClick={onSave} disabled={disabled} className="px-3 py-1 text-sm rounded-md bg-[var(--primary)] hover:bg-[var(--primary-dk)] disabled:opacity-40 text-white">
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

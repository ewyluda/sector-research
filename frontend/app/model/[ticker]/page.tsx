"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { getModel, initializeModel, type TickerModelVersion, type TickerModelDraft } from "@/lib/api";
import { MODEL_TABS, type ModelTab } from "@/components/model/modelSections";

export default function ModelPage() {
  const params = useParams<{ ticker: string }>();
  const ticker = (Array.isArray(params.ticker) ? params.ticker[0] : params.ticker) ?? "";
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

  if (loading) return <div className="p-6 text-slate-400">Loading model…</div>;
  if (err) return <div className="p-6 text-red-400">Error: {err}</div>;
  if (!latest) {
    return (
      <div className="p-6 space-y-3">
        <h1 className="text-2xl font-semibold">{ticker} — no model yet</h1>
        <button onClick={handleCreate} className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 rounded text-white">
          Create AI baseline
        </button>
      </div>
    );
  }

  const activeState = draft?.state ?? latest.state;

  return (
    <div className="flex flex-col h-full">
      <header className="border-b border-slate-800 px-6 py-3 flex items-center gap-4" data-print-hide="true">
        <h1 className="text-xl font-semibold">
          {ticker} <span className="text-slate-500 text-sm">v{latest.version} · {latest.label}</span>
        </h1>
        <nav className="flex gap-2 ml-auto">
          {MODEL_TABS.map((t) => (
            <a
              key={t.id}
              href={t.hash}
              className={`px-3 py-1.5 rounded text-sm ${
                tab === t.id ? "bg-slate-800 text-white" : "text-slate-400 hover:text-white"
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

// Stubs for the next tasks — props typed for call-site TS safety; param intentionally unused
/* eslint-disable @typescript-eslint/no-unused-vars */
function ForecastTabContent(_props: {
  state: import("@/lib/api").ModelState;
  draft: import("@/lib/api").TickerModelDraft | null;
  latest: TickerModelVersion;
  ticker: string;
  onDraftChange: (d: import("@/lib/api").TickerModelDraft | null) => void;
  onSaved: (v: TickerModelVersion) => void;
}) {
  return <div className="p-6 text-slate-500">Forecast tab — see Task 24</div>;
}
function ReverseDcfTabContent(_props: { ticker: string; hasDraft: boolean }) {
  return <div className="p-6 text-slate-500">Reverse DCF tab — see Task 25</div>;
}
function HistoryTabContent(_props: { ticker: string }) {
  return <div className="p-6 text-slate-500">History tab — see Task 27</div>;
}
/* eslint-enable @typescript-eslint/no-unused-vars */

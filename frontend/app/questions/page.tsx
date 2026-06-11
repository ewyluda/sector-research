"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  questions as questionsApi,
  type Question,
  type QuestionStatus,
  type QuestionTickerRollup,
} from "@/lib/api";
import { QuestionRow } from "@/components/questions/QuestionRow";
import { QuestionTickerRollupTable } from "@/components/questions/QuestionTickerRollupTable";
import {
  initialQuestionsTab,
  syncQuestionsTabForTickerFilter,
  type QuestionsTab,
} from "@/lib/questions-ui";

const CHIP_BASE = "px-2 py-1 rounded-full text-xs border transition";
const CHIP_ON = "border-emerald-500 bg-emerald-900/40 text-emerald-200";
const CHIP_OFF = "border-slate-700 text-slate-400 hover:text-slate-200";

function QuestionsPageInner() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const tickerFilter = searchParams.get("ticker") ?? undefined;
  const priorityParam = searchParams.get("priority");
  const categoryParam = searchParams.get("category");

  const [tab, setTab] = useState<QuestionsTab>(initialQuestionsTab(tickerFilter));
  const [rollup, setRollup] = useState<QuestionTickerRollup[]>([]);
  const [list, setList] = useState<Question[]>([]);
  const [statusFilter, setStatusFilter] = useState<QuestionStatus | "all">("open");
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulkBusy, setBulkBusy] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    setTab((current) => syncQuestionsTabForTickerFilter(current, tickerFilter));
  }, [tickerFilter]);

  useEffect(() => {
    let mounted = true;

    const load = async () => {
      setLoading(true);
      try {
        if (tab === "by_ticker") {
          const r = await questionsApi.byTicker();
          if (mounted) setRollup(r.tickers);
        } else {
          const r = await questionsApi.list({
            ticker: tickerFilter,
            status: statusFilter,
            limit: 200,
          });
          if (mounted) setList(r.questions);
        }
      } finally {
        if (mounted) setLoading(false);
      }
    };

    load();
    const interval = setInterval(() => {
      if (document.visibilityState === "visible") load();
    }, 60_000);

    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, [tab, tickerFilter, statusFilter, refreshKey]);

  const setUrlParam = (key: string, value: string | null) => {
    const params = new URLSearchParams(searchParams.toString());
    if (value === null) params.delete(key);
    else params.set(key, value);
    router.replace(params.toString() ? `${pathname}?${params}` : pathname, { scroll: false });
  };

  const categories = useMemo(
    () => Array.from(new Set(list.map((q) => q.category))).sort(),
    [list],
  );

  const visible = useMemo(
    () =>
      list.filter(
        (q) =>
          (priorityParam ? q.priority === Number(priorityParam) : true) &&
          (categoryParam ? q.category === categoryParam : true),
      ),
    [list, priorityParam, categoryParam],
  );

  const selectedVisible = useMemo(
    () => visible.filter((q) => selected.has(q.id)).map((q) => q.id),
    [visible, selected],
  );
  const allVisibleSelected = visible.length > 0 && selectedVisible.length === visible.length;

  const toggleSelect = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    setSelected(allVisibleSelected ? new Set() : new Set(visible.map((q) => q.id)));
  };

  const runBulk = async (action: "dismiss" | "snooze", snoozeDays?: number) => {
    if (bulkBusy || selectedVisible.length === 0) return;
    setBulkBusy(true);
    try {
      await questionsApi.bulk({
        ids: selectedVisible,
        action,
        ...(snoozeDays !== undefined ? { snooze_days: snoozeDays } : {}),
      });
      setSelected(new Set());
      setRefreshKey((k) => k + 1);
    } finally {
      setBulkBusy(false);
    }
  };

  const handleQuestionChange = (updated: Question) => {
    setList((prev) => prev.map((q) => (q.id === updated.id ? updated : q)));
  };

  return (
    <main className="max-w-5xl mx-auto p-6">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold text-slate-100">Questions</h1>
        <p className="text-slate-400 text-sm mt-1">
          Open analysis gaps across the fleet, surfaced from deep-dive runs.
          {tickerFilter && (
            <>
              {" · Filtered to "}
              <span className="font-mono">{tickerFilter}</span>
            </>
          )}
        </p>
      </header>

      <div className="flex gap-2 mb-4 border-b border-slate-800">
        <button
          type="button"
          onClick={() => setTab("by_ticker")}
          className={`px-3 py-2 text-sm border-b-2 transition ${
            tab === "by_ticker"
              ? "border-emerald-500 text-emerald-200"
              : "border-transparent text-slate-400 hover:text-slate-200"
          }`}
        >
          By ticker
        </button>
        <button
          type="button"
          onClick={() => setTab("by_question")}
          className={`px-3 py-2 text-sm border-b-2 transition ${
            tab === "by_question"
              ? "border-emerald-500 text-emerald-200"
              : "border-transparent text-slate-400 hover:text-slate-200"
          }`}
        >
          By question
        </button>
      </div>

      {tab === "by_question" && (
        <div className="flex flex-wrap items-center gap-2 mb-4 text-xs">
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as QuestionStatus | "all")}
            className="bg-slate-900 border border-slate-700 rounded px-2 py-1 text-slate-200"
          >
            <option value="open">Open</option>
            <option value="resolved_auto">Auto-resolved</option>
            <option value="resolved_inline">Resolved (next run)</option>
            <option value="resolved_manual">Manually resolved</option>
            <option value="dismissed">Dismissed</option>
            <option value="all">All</option>
          </select>

          {([1, 2, 3] as const).map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => setUrlParam("priority", priorityParam === String(p) ? null : String(p))}
              className={`${CHIP_BASE} ${priorityParam === String(p) ? CHIP_ON : CHIP_OFF}`}
            >
              P{p}
            </button>
          ))}

          {categories.map((cat) => (
            <button
              key={cat}
              type="button"
              onClick={() => setUrlParam("category", categoryParam === cat ? null : cat)}
              className={`${CHIP_BASE} ${categoryParam === cat ? CHIP_ON : CHIP_OFF}`}
            >
              {cat}
            </button>
          ))}
        </div>
      )}

      {tab === "by_question" && !loading && visible.length > 0 && (
        <div className="flex items-center gap-3 mb-3 text-xs text-slate-400">
          <label className="flex items-center gap-1.5 cursor-pointer">
            <input
              type="checkbox"
              checked={allVisibleSelected}
              onChange={toggleSelectAll}
              className="accent-emerald-500"
            />
            Select all matching filter ({visible.length})
          </label>
        </div>
      )}

      {tab === "by_question" && selectedVisible.length > 0 && (
        <div
          className="sticky top-2 z-10 flex items-center gap-2 mb-3 px-3 py-2 rounded-md border border-slate-700 bg-slate-900/95 text-xs"
          data-print-hide="true"
        >
          <span className="text-slate-200 font-medium">{selectedVisible.length} selected</span>
          <button
            type="button"
            onClick={() => runBulk("dismiss")}
            disabled={bulkBusy}
            className="px-2 py-1 rounded border border-slate-600 text-slate-200 hover:bg-slate-800 disabled:opacity-50"
          >
            Dismiss
          </button>
          <button
            type="button"
            onClick={() => runBulk("snooze", 7)}
            disabled={bulkBusy}
            className="px-2 py-1 rounded border border-amber-700 text-amber-200 hover:bg-amber-900/30 disabled:opacity-50"
          >
            Snooze 7d
          </button>
          <button
            type="button"
            onClick={() => runBulk("snooze", 30)}
            disabled={bulkBusy}
            className="px-2 py-1 rounded border border-amber-700 text-amber-200 hover:bg-amber-900/30 disabled:opacity-50"
          >
            Snooze 30d
          </button>
        </div>
      )}

      {loading && <p className="text-slate-500 text-sm">Loading…</p>}
      {!loading && tab === "by_ticker" && <QuestionTickerRollupTable rollup={rollup} />}
      {!loading && tab === "by_question" && (
        <div className="space-y-2">
          {visible.length === 0 ? (
            <p className="text-slate-500 text-sm">No questions match the current filter.</p>
          ) : (
            visible.map((q) => (
              <QuestionRow
                key={q.id}
                question={q}
                onChange={handleQuestionChange}
                selected={selected.has(q.id)}
                onToggleSelect={toggleSelect}
              />
            ))
          )}
        </div>
      )}
    </main>
  );
}

export default function QuestionsPage() {
  return (
    <Suspense fallback={<main className="max-w-5xl mx-auto p-6"><p className="text-slate-500 text-sm">Loading…</p></main>}>
      <QuestionsPageInner />
    </Suspense>
  );
}

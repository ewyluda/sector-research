"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  questions as questionsApi,
  type Question,
  type QuestionStatus,
  type QuestionTickerRollup,
} from "@/lib/api";
import { QuestionRow } from "@/components/questions/QuestionRow";
import { QuestionTickerRollupTable } from "@/components/questions/QuestionTickerRollupTable";

type Tab = "by_ticker" | "by_question";

function QuestionsPageInner() {
  const searchParams = useSearchParams();
  const tickerFilter = searchParams.get("ticker") ?? undefined;

  const [tab, setTab] = useState<Tab>(tickerFilter ? "by_question" : "by_ticker");
  const [rollup, setRollup] = useState<QuestionTickerRollup[]>([]);
  const [list, setList] = useState<Question[]>([]);
  const [statusFilter, setStatusFilter] = useState<QuestionStatus | "all">("open");
  const [priorityFilter, setPriorityFilter] = useState<1 | 2 | 3 | "all">("all");
  const [loading, setLoading] = useState(true);

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
            status: statusFilter === "all" ? undefined : statusFilter,
            priority: priorityFilter === "all" ? undefined : priorityFilter,
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
  }, [tab, tickerFilter, statusFilter, priorityFilter]);

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
        <div className="flex flex-wrap gap-2 mb-4 text-xs">
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
          <select
            value={priorityFilter}
            onChange={(e) =>
              setPriorityFilter(
                e.target.value === "all" ? "all" : (Number(e.target.value) as 1 | 2 | 3),
              )
            }
            className="bg-slate-900 border border-slate-700 rounded px-2 py-1 text-slate-200"
          >
            <option value="all">All priorities</option>
            <option value="1">Priority 1</option>
            <option value="2">Priority 2</option>
            <option value="3">Priority 3</option>
          </select>
        </div>
      )}

      {loading && <p className="text-slate-500 text-sm">Loading…</p>}
      {!loading && tab === "by_ticker" && <QuestionTickerRollupTable rollup={rollup} />}
      {!loading && tab === "by_question" && (
        <div className="space-y-2">
          {list.length === 0 ? (
            <p className="text-slate-500 text-sm">No questions match the current filter.</p>
          ) : (
            list.map((q) => (
              <QuestionRow key={q.id} question={q} onChange={handleQuestionChange} />
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

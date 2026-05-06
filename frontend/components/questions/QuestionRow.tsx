"use client";

import { useState } from "react";
import type { Question } from "@/lib/api";
import { questions as questionsApi } from "@/lib/api";

const PRIORITY_CHIP: Record<1 | 2 | 3, string> = {
  1: "bg-rose-900/40 text-rose-200 border-rose-700/60",
  2: "bg-amber-900/40 text-amber-200 border-amber-700/60",
  3: "bg-slate-700/40 text-slate-300 border-slate-600/60",
};

const STATUS_CHIP: Record<string, string> = {
  open: "bg-amber-900/40 text-amber-200 border-amber-700/60",
  resolved_auto: "bg-emerald-900/40 text-emerald-200 border-emerald-700/60",
  resolved_inline: "bg-emerald-900/40 text-emerald-200 border-emerald-700/60",
  resolved_manual: "bg-emerald-900/40 text-emerald-200 border-emerald-700/60",
  dismissed: "bg-slate-700/40 text-slate-400 border-slate-600/60",
};

const STATUS_LABEL: Record<string, string> = {
  open: "Open",
  resolved_auto: "Auto-resolved",
  resolved_inline: "Resolved (next run)",
  resolved_manual: "Manually resolved",
  dismissed: "Dismissed",
};

interface Props {
  question: Question;
  onChange?: (q: Question) => void;
}

export function QuestionRow({ question, onChange }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [busy, setBusy] = useState(false);

  const handleDismiss = async () => {
    if (busy) return;
    const note = window.prompt("Optional note:") ?? undefined;
    setBusy(true);
    try {
      const updated = await questionsApi.dismiss(question.id, note);
      onChange?.(updated);
    } finally {
      setBusy(false);
    }
  };

  const handleResolve = async () => {
    if (busy) return;
    const answer = window.prompt("Answer text:");
    if (!answer || !answer.trim()) return;
    setBusy(true);
    try {
      const updated = await questionsApi.resolve(question.id, answer);
      onChange?.(updated);
    } finally {
      setBusy(false);
    }
  };

  const handleRetry = async () => {
    if (busy) return;
    setBusy(true);
    try {
      const updated = await questionsApi.retryAuto(question.id);
      onChange?.(updated);
    } finally {
      setBusy(false);
    }
  };

  const isOpen = question.status === "open";

  return (
    <div className="border border-slate-800 rounded-md bg-slate-950/40 p-3 text-sm">
      <div className="flex items-start gap-2">
        <span className={`px-1.5 py-0.5 rounded text-xs font-medium border ${PRIORITY_CHIP[question.priority as 1 | 2 | 3] ?? PRIORITY_CHIP[3]}`}>
          P{question.priority}
        </span>
        <span className={`px-1.5 py-0.5 rounded text-xs font-medium border ${STATUS_CHIP[question.status] ?? STATUS_CHIP.open}`}>
          {STATUS_LABEL[question.status] ?? question.status}
        </span>
        <p className="flex-1 text-slate-200">{question.question_text}</p>
      </div>

      {question.answer_text && (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="mt-2 text-xs text-slate-400 hover:text-slate-200"
          data-print-hide="true"
        >
          {expanded ? "Hide answer" : "Show answer"}
        </button>
      )}

      {expanded && question.answer_text && (
        <div className="mt-2 p-2 rounded bg-slate-900/60 border border-slate-800 text-slate-300 text-xs whitespace-pre-wrap">
          {question.answer_text}
          {question.answer_source && (
            <p className="mt-1 text-[10px] text-slate-500">— {question.answer_source}</p>
          )}
        </div>
      )}

      {isOpen && (
        <div className="mt-2 flex gap-2" data-print-hide="true">
          <button
            type="button"
            onClick={handleRetry}
            disabled={busy}
            className="px-2 py-1 text-xs rounded border border-emerald-700 text-emerald-200 hover:bg-emerald-900/30 disabled:opacity-50"
          >
            Retry auto
          </button>
          <button
            type="button"
            onClick={handleResolve}
            disabled={busy}
            className="px-2 py-1 text-xs rounded border border-slate-600 text-slate-200 hover:bg-slate-800 disabled:opacity-50"
          >
            Mark resolved
          </button>
          <button
            type="button"
            onClick={handleDismiss}
            disabled={busy}
            className="px-2 py-1 text-xs rounded border border-slate-700 text-slate-400 hover:bg-slate-800 disabled:opacity-50"
          >
            Dismiss
          </button>
        </div>
      )}
    </div>
  );
}

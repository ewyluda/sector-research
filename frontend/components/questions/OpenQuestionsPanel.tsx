"use client";

import { useState } from "react";
import type { Question } from "@/lib/api";
import { QuestionRow } from "./QuestionRow";

interface Props {
  questions: Question[];
}

export function OpenQuestionsPanel({ questions: initial }: Props) {
  const [list, setList] = useState<Question[]>(initial);

  const handleChange = (updated: Question) => {
    setList((prev) => prev.map((q) => (q.id === updated.id ? updated : q)));
  };

  if (list.length === 0) return null;

  const groups: Record<string, Question[]> = {};
  for (const q of list) {
    if (!groups[q.category]) groups[q.category] = [];
    groups[q.category].push(q);
  }
  const categories = Object.keys(groups).sort();

  const openCount = list.filter((q) => q.status === "open").length;

  return (
    <section className="my-6">
      <header className="mb-3 flex items-baseline gap-2">
        <h2 className="text-lg font-semibold text-[var(--text)]">Open Questions</h2>
        <span className="text-xs text-[var(--text-muted)]">
          {openCount} open · {list.length} total
        </span>
      </header>

      <div className="space-y-4">
        {categories.map((cat) => (
          <div key={cat}>
            <h3 className="text-sm font-medium text-[var(--text-muted)] mb-2">{cat}</h3>
            <div className="space-y-2">
              {groups[cat]
                .sort((a, b) => {
                  if (a.status === "open" && b.status !== "open") return -1;
                  if (a.status !== "open" && b.status === "open") return 1;
                  return a.priority - b.priority;
                })
                .map((q) => (
                  <QuestionRow key={q.id} question={q} onChange={handleChange} />
                ))}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

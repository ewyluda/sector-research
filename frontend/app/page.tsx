"use client";

/**
 * Today dashboard (/) — morning briefing.
 * SummaryBanner → 4-day calendar lanes → needs-attention list.
 * Composes /api/status/board + /api/catalysts/calendar + /api/questions/by-ticker
 * client-side; polls every 60s while the tab is visible. Each section degrades
 * independently — a failed source shows an inline note, never blanks the page.
 * All date-dependent rendering is gated on the client-set `now` state so the
 * build-time prerender (date-free) matches the first client paint.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import {
  getCalendarEvents,
  questions as questionsApi,
  status as statusApi,
  type CalendarEvent,
  type QuestionTickerRollup,
  type StatusBoardEntry,
} from "@/lib/api";
import { addDays, isoLocal } from "@/components/catalysts/calendarDates";
import { deriveAttention, deriveSummary } from "@/lib/todayDerive";
import { SummaryBanner } from "@/components/today/SummaryBanner";
import { TodayLanes } from "@/components/today/TodayLanes";
import { AttentionList } from "@/components/today/AttentionList";

const HEADER_FMT = new Intl.DateTimeFormat("en-US", {
  weekday: "long",
  month: "long",
  day: "numeric",
});

export default function TodayDashboard() {
  const [now, setNow] = useState<Date | null>(null);
  const [board, setBoard] = useState<StatusBoardEntry[] | null>(null);
  const [boardError, setBoardError] = useState<string | null>(null);
  const [events, setEvents] = useState<CalendarEvent[] | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [calendarError, setCalendarError] = useState<string | null>(null);
  const [rollup, setRollup] = useState<QuestionTickerRollup[] | null>(null);
  const [questionsError, setQuestionsError] = useState<string | null>(null);
  // Tracks which sources have loaded at least once, so polling failures
  // after a successful first load keep last-good data without an error note.
  const loadedRef = useRef({ board: false, calendar: false, questions: false });

  useEffect(() => {
    let cancelled = false;

    async function fetchAll() {
      // Recompute the clock + window each poll so an overnight tab rolls forward.
      const today = new Date();
      const start = isoLocal(today);
      const end = isoLocal(addDays(today, 3));

      const [boardRes, calRes, qRes] = await Promise.allSettled([
        statusApi.board(),
        getCalendarEvents(start, end),
        questionsApi.byTicker(),
      ]);
      if (cancelled) return;
      setNow(today);

      if (boardRes.status === "fulfilled") {
        loadedRef.current.board = true;
        setBoard(boardRes.value.entries);
        setBoardError(null);
      } else if (!loadedRef.current.board) {
        setBoardError("Could not load the status board.");
      } // else: keep last-good data, no error note

      if (calRes.status === "fulfilled") {
        loadedRef.current.calendar = true;
        setEvents(calRes.value.events);
        setWarnings(calRes.value.warnings);
        setCalendarError(null);
      } else if (!loadedRef.current.calendar) {
        setCalendarError("Could not load the calendar.");
      }

      if (qRes.status === "fulfilled") {
        loadedRef.current.questions = true;
        setRollup(qRes.value.tickers);
        setQuestionsError(null);
      } else if (!loadedRef.current.questions) {
        setQuestionsError("Could not load open questions.");
      }
    }

    fetchAll();
    const onVis = () => {
      if (document.visibilityState === "visible") fetchAll();
    };
    const interval = setInterval(() => {
      if (document.visibilityState === "visible") fetchAll();
    }, 60_000);
    document.addEventListener("visibilitychange", onVis);
    return () => {
      cancelled = true;
      clearInterval(interval);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, []);

  const summary = useMemo(() => deriveSummary(board ?? [], rollup ?? []), [board, rollup]);
  const attentionRows = useMemo(() => deriveAttention(board ?? [], rollup ?? []), [board, rollup]);

  // Attention section: board failure dominates (rows would be misleadingly
  // empty); a questions-only failure still shows health rows with a note.
  const attentionError =
    boardError ?? (questionsError ? `${questionsError} Health rows may be incomplete.` : null);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-[var(--text)]">Today</h1>
        <p className="text-sm text-[var(--text-muted)] mt-0.5">
          {now ? HEADER_FMT.format(now) : " "}
        </p>
      </div>

      {!boardError && !questionsError && <SummaryBanner summary={summary} />}

      {now && <TodayLanes events={events ?? []} warnings={warnings} error={calendarError} today={now} />}

      <AttentionList rows={attentionRows} error={attentionError} />
    </div>
  );
}

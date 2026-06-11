"use client";

/**
 * Today dashboard (/) — morning briefing + calendar.
 * Two URL-driven tabs: Briefing (default — SummaryBanner → 4-day calendar
 * lanes → needs-attention list) and Calendar (?tab=calendar — the full
 * CatalystsView absorbed from the old /catalysts page, which now redirects
 * here). Briefing composes /api/status/board + /api/catalysts/calendar +
 * /api/questions/by-ticker client-side; polls every 60s while the tab is
 * visible. Each section degrades independently — a failed source shows an
 * inline note, never blanks the page. All date-dependent rendering is gated
 * on the client-set `now` state so the build-time prerender (date-free)
 * matches the first client paint.
 *
 * useSearchParams on a statically-prerendered client page requires a
 * <Suspense> boundary (Next 16: missing-suspense-with-csr-bailout), hence
 * the thin default export.
 */

import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import {
  events as eventsApi,
  getCalendarEvents,
  getCatalysts,
  questions as questionsApi,
  status as statusApi,
  type CalendarEvent,
  type CatalystBuckets,
  type MaterialEvent,
  type QuestionTickerRollup,
  type StatusBoardEntry,
} from "@/lib/api";
import { addDays, isoLocal } from "@/components/catalysts/calendarDates";
import { deriveAttention, deriveSummary } from "@/lib/todayDerive";
import { SummaryBanner } from "@/components/today/SummaryBanner";
import { TodayLanes } from "@/components/today/TodayLanes";
import { AttentionList } from "@/components/today/AttentionList";
import { CatalystsView } from "@/components/catalysts/CatalystsView";

const HEADER_FMT = new Intl.DateTimeFormat("en-US", {
  weekday: "long",
  month: "long",
  day: "numeric",
});

export default function TodayPage() {
  return (
    <Suspense fallback={null}>
      <TodayDashboard />
    </Suspense>
  );
}

function TodayDashboard() {
  const searchParams = useSearchParams();
  const tab = searchParams.get("tab") === "calendar" ? "calendar" : "briefing";

  const [now, setNow] = useState<Date | null>(null);
  const [board, setBoard] = useState<StatusBoardEntry[] | null>(null);
  const [boardError, setBoardError] = useState<string | null>(null);
  const [events, setEvents] = useState<CalendarEvent[] | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [calendarError, setCalendarError] = useState<string | null>(null);
  const [rollup, setRollup] = useState<QuestionTickerRollup[] | null>(null);
  const [questionsError, setQuestionsError] = useState<string | null>(null);
  const [materialEvents, setMaterialEvents] = useState<MaterialEvent[] | null>(null);
  const [eventsError, setEventsError] = useState<string | null>(null);
  // Calendar tab's List view needs the bucketed catalyst list — fetched
  // lazily the first time the tab activates.
  const [buckets, setBuckets] = useState<CatalystBuckets | null>(null);
  const [bucketsError, setBucketsError] = useState<string | null>(null);
  // Tracks which sources have loaded at least once, so polling failures
  // after a successful first load keep last-good data without an error note.
  const loadedRef = useRef({ board: false, calendar: false, questions: false, events: false });

  useEffect(() => {
    let cancelled = false;

    async function fetchAll() {
      // Recompute the clock + window each poll so an overnight tab rolls forward.
      const today = new Date();
      const start = isoLocal(today);
      const end = isoLocal(addDays(today, 3));

      const [boardRes, calRes, qRes, evRes] = await Promise.allSettled([
        statusApi.board(),
        getCalendarEvents(start, end),
        questionsApi.byTicker(),
        eventsApi.list({ since_days: 7, materiality: "high" }),
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

      if (evRes.status === "fulfilled") {
        loadedRef.current.events = true;
        setMaterialEvents(evRes.value.events);
        setEventsError(null);
      } else if (!loadedRef.current.events) {
        setEventsError("Could not load material events.");
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

  // Lazy fetch for the Calendar tab's List view (mirrors the old /catalysts
  // server fetch + error note).
  useEffect(() => {
    if (tab !== "calendar" || buckets !== null) return;
    let cancelled = false;
    getCatalysts()
      .then((d) => {
        if (!cancelled) {
          setBuckets(d.buckets);
          setBucketsError(null);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setBucketsError("Could not connect to backend. Is the FastAPI server running?");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [tab, buckets]);

  // Tickers with an active board entry — the Calendar tab's agenda tags
  // catalyst rows for tickers outside this set as "archived thesis".
  const activeTickers = useMemo(
    () => (board ? new Set(board.map((e) => e.ticker)) : undefined),
    [board],
  );

  const summary = useMemo(() => deriveSummary(board ?? [], rollup ?? []), [board, rollup]);
  const attentionRows = useMemo(
    () => deriveAttention(board ?? [], rollup ?? [], materialEvents ?? []),
    [board, rollup, materialEvents],
  );

  // Attention section: board failure dominates (rows would be misleadingly
  // empty); a questions-only failure still shows health rows with a note.
  const attentionError =
    boardError ??
    (questionsError ? `${questionsError} Health rows may be incomplete.` : null) ??
    (eventsError ? `${eventsError} 8-K rows may be missing.` : null);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-[var(--text)]">Today</h1>
        <p className="text-sm text-[var(--text-muted)] mt-0.5">
          {now ? HEADER_FMT.format(now) : " "}
        </p>
      </div>

      <div className="flex gap-1 border-b border-[var(--border)]" data-print-hide="true">
        {(["briefing", "calendar"] as const).map((t) => (
          <Link
            key={t}
            href={t === "briefing" ? "/" : "/?tab=calendar"}
            scroll={false}
            className={`px-3 py-1.5 text-sm rounded-t-md ${
              tab === t
                ? "bg-[var(--surface)] text-[var(--text)] font-medium border border-b-0 border-[var(--border)]"
                : "text-[var(--text-muted)] hover:text-[var(--text)]"
            }`}
          >
            {t === "briefing" ? "Briefing" : "Calendar"}
          </Link>
        ))}
      </div>

      {tab === "briefing" ? (
        <>
          {!boardError && <SummaryBanner summary={summary} />}

          {now && <TodayLanes events={events ?? []} warnings={warnings} error={calendarError} today={now} />}

          {now && <AttentionList rows={attentionRows} error={attentionError} />}
        </>
      ) : (
        <>
          {bucketsError && (
            <div className="rounded-md border border-[var(--error)]/30 bg-[var(--error)]/5 p-3 text-xs text-[var(--error)]">
              {bucketsError}
            </div>
          )}
          {buckets && <CatalystsView buckets={buckets} activeTickers={activeTickers} />}
        </>
      )}
    </div>
  );
}

import type { MaterialEvent } from "./api/status";

export interface OrphanEventGroup {
  ticker: string;
  events: MaterialEvent[];
}

/**
 * Events on tickers with no status-board entry (theme seeds without an
 * active thesis). Board tickers render their events inside board rows;
 * everything else needs OrphanEventsSection or the ?expand_events= deep
 * link dead-ends (TODO.md backlog item).
 */
export function deriveOrphanEvents(
  eventsByTicker: Record<string, MaterialEvent[]>,
  boardTickers: ReadonlySet<string>,
): OrphanEventGroup[] {
  return Object.entries(eventsByTicker)
    .filter(([ticker, events]) => !boardTickers.has(ticker) && events.length > 0)
    .map(([ticker, events]) => ({ ticker, events }))
    .sort((a, b) => a.ticker.localeCompare(b.ticker));
}

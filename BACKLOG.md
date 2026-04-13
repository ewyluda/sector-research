# Backlog

Items identified during development, prioritized for future sessions.

## High Priority

### ~~Earnings Transcripts / Analyst Q&A Integration~~ (moved to Completed)

### ~~Citation Formatting Improvements~~ (moved to Completed)

## Medium Priority

### ~~FRED API for Macro & Regime Section~~ (moved to Completed)

### Additional FMP Endpoints to Explore
**Context:** The FMP `/stable/` API has endpoints we don't use that could enrich analysis:
- `get_key_metrics_ttm()` — already implemented, never called. Has PE ratio, profitability metrics.
- `get_quote()` — already implemented, never called. Real-time price (5min TTL).
- Options flow — FMP `/stable/` doesn't have it yet, stubbed in client.
- Insider transactions, institutional holdings — not explored yet.
**Status:** Needs research

## Low Priority / Future

### Cross-Category Correlation Views
**Context:** Noted in the dashboard spec as a future enhancement. Overlay margin trends vs revenue growth, or financial health metrics vs price action.
**Status:** Idea only

### X Signal Velocity Sparkline
**Context:** The Sentiment & Narrative qualitative card has a slot for a velocity sparkline from the X signals table (populated by the daily scheduler). The component accepts a `headerAddon` prop for this.
**Status:** Frontend slot exists, needs data wiring

## Completed

- [x] Deep-dive financial dashboard redesign (2026-04-12)
- [x] Historical price data + candlestick chart with SMA/RSI (2026-04-12)
- [x] Quarterly FMP data resolution (2026-04-12)
- [x] Curated financials backend extraction pipeline (2026-04-12)
- [x] Earnings transcript / analyst Q&A integration — 6-pass analysis (2026-04-12)
- [x] Citation formatting — teal sidebar style + CSS variable fix (2026-04-12)
- [x] FRED API macro integration — 9 series, rates/CPI/GDP/M2/payrolls charts (2026-04-12)

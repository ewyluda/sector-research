---
name: Quick Screen
description: 30-minute triage workflow to determine whether a ticker deserves deeper research — produces a GO / WATCHLIST / PASS decision
type: workflow
estimated_time: 30 min
---

## When to Use

- A new ticker appears on a screener or watchlist
- Someone pitches a stock and you need to form a preliminary view before spending real time
- An earnings surprise, analyst upgrade, or news event triggers a first look
- You want to clear a backlog of potential ideas efficiently before allocating deep-dive time

Do not skip the Quick Screen in favor of going straight to deep-dive. The Quick Screen exists to protect your time. A PASS decision here saves 3-5 hours.

## Process

### Step 1 — Data Validation (5 min)

Pull the summary from Tier 1 sources. Confirm basic facts before forming any view.

**Skills used:** `categories/01-business-quality` (orientation only — not full analysis)

**Checklist:**
- [ ] Market cap confirmed — is this large-cap, mid-cap, or small-cap? Illiquid micro-caps require a flag.
- [ ] Sector and sub-industry confirmed
- [ ] Primary exchange and listing status (ADR? SPAC? Recent IPO?)
- [ ] Minimum liquidity check: average daily volume > $10M for practical entry/exit
- [ ] Data availability: do Tier 1 sources have at least 2 years of financials? If not, flag data risk.

**Flag any of the following and record:**
- Less than 2 years of public financials
- Average daily volume < $10M
- Pending regulatory/legal action that could impair operations
- Non-standard accounting structure (VIE, royalty stream, partnership)

---

### Step 2 — Business Quality Surface Pass (10 min)

Form a rapid view on whether this is a structurally sound business. This is not a full moat analysis — it is a surface read to identify obvious disqualifiers or excitement signals.

**Skills used:**
- `categories/01-business-quality/moat-analysis` (surface level — answer the one-line version)
- `categories/01-business-quality/industry-lifecycle`

**Questions to answer (one sentence each):**
1. What does this company do, and how does it make money?
2. Is there any structural advantage (pricing power, switching costs, scale, network effects, IP)? Or is this a commodity business?
3. Is the industry in growth, maturity, or decline?
4. Does the business model make intuitive sense — does it earn more from customers than it costs to serve them?

**Disqualifiers (auto-FAIL):**
- Pure commodity business with no differentiation in a declining industry
- Business model depends on continued external financing (negative FCF, burning cash, no path to profitability flagged)
- Industry in structural secular decline with no evidence of the company adapting

---

### Step 3 — Financial Snapshot (10 min)

Check whether the business is priced sensibly and whether the financials are healthy enough to warrant further review.

**Skills used:**
- `categories/02-financial-health/valuation-multiples` (vs. sector median — not a deep DCF)
- `categories/02-financial-health/profitability-analysis` (margins and ROIC at a glance)

**Questions to answer:**
1. P/E, EV/EBITDA, P/S — how does valuation compare to sector median? Is it a significant premium or discount?
2. What are gross margins and operating margins? Are they above or below industry average?
3. ROIC vs. WACC — is the business creating or destroying economic value?
4. Is the balance sheet clean enough to survive a downturn (net debt < 3x EBITDA as a rough threshold)?

**Record:**
- Valuation vs. sector: PREMIUM / IN-LINE / DISCOUNT
- Margin profile: ABOVE / AVERAGE / BELOW sector
- ROIC: ABOVE / BELOW estimated WACC
- Balance sheet: CLEAN / LEVERED / STRESSED

---

### Step 4 — Technical Gut Check (5 min)

Determine whether price action is working with or against a potential thesis. This is not a buy signal — it is a momentum filter.

**Skills used:**
- `categories/05-technical-market-structure/trend-momentum`

**Questions to answer:**
1. Is the stock above or below its 200-day moving average?
2. Is price in an uptrend, downtrend, or range-bound?
3. Is a potential entry going with or against the trend?
4. Any obvious technical damage (gap down on earnings, breakdown from multi-year range)?

**Record:** WITH TREND / AGAINST TREND / NEUTRAL

---

### Decision Gate

Score each dimension from the steps above:

| Dimension | Result | Score |
|-----------|--------|-------|
| Data & Liquidity | No flags / Flags present | PASS / FAIL |
| Business Quality | Moat evident / Commodity / Unclear | PASS / NEUTRAL / FAIL |
| Industry Lifecycle | Growth or Maturity / Decline | PASS / FAIL |
| Valuation vs. Sector | Discount or In-Line / Significant Premium | PASS / NEUTRAL / FAIL |
| Profitability (Margins + ROIC) | Above or Average / Below | PASS / NEUTRAL / FAIL |
| Technical Trend | With Trend / Neutral / Against Trend | PASS / NEUTRAL / FAIL |

**Decision rules:**

| Result | Criteria | Action |
|--------|----------|--------|
| GO | 3+ PASS, 0 FAIL | Proceed to `deep-dive` workflow |
| WATCHLIST | Mixed results, or exactly 1 FAIL with strong PASS signals elsewhere | Monitor; set a trigger condition for re-review |
| PASS | 2+ FAIL (any dimension), or any auto-disqualifier triggered | Remove from active consideration; document reason |

---

## Output

**Required deliverables:**

1. **One-paragraph summary** — what the company does, why it appeared on the screen, and the single most important thing you learned in 30 minutes. Written as if briefing a colleague who has zero context.

2. **Decision with reasoning** — one of:
   - **GO** — state which 3+ dimensions scored PASS and what makes this worth 3-5 hours
   - **WATCHLIST** — state the specific trigger condition that would move this to GO (e.g., "valuation compresses to 15x EV/EBITDA" or "next quarter shows margin recovery")
   - **PASS** — state which dimensions failed and why the flaws are disqualifying rather than just risks to manage

3. **Data flags log** — any liquidity issues, accounting structures, or data gaps identified in Step 1 that must be revisited if the ticker moves to deep-dive.

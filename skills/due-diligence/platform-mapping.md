---
name: Platform Mapping
description: Maps each due diligence skill to platform agents, API endpoints, and MCP tools
type: framework
---

## Purpose

Connect the platform-agnostic skill methodology to the multi-agent market research platform's capabilities. This document tells you which skills can be automated (fully or partially) and which require manual analysis.

## Coverage Levels

| Level | Meaning |
|-------|---------|
| **Full** | Platform provides all data needed for this skill |
| **Partial** | Platform provides some data; remaining analysis is manual |
| **Manual** | No platform support — purely methodological |

## Skill-to-Platform Mapping

### 01 — Business Quality

| Skill | Platform Agent/Endpoint | MCP Tool | Coverage |
|-------|------------------------|----------|----------|
| moat-analysis | None | None | Manual |
| competitive-positioning | FundamentalsAgent → peers, revenue segments | `get_peers`, `get_revenue_segments` | Partial (data for peer comparison; moat judgment is manual) |
| tam-market-sizing | None | None | Manual |
| industry-lifecycle | None | None | Manual |

### 02 — Financial Health

| Skill | Platform Agent/Endpoint | MCP Tool | Coverage |
|-------|------------------------|----------|----------|
| valuation-multiples | FundamentalsAgent → `/api/agent/{ticker}/analysis?sections=fundamentals` | `get_analysis`, `get_raw_data` (ratios) | Full |
| dcf-analysis | FundamentalsAgent → DCF endpoint | `get_raw_data` (dcf, financials, growth) | Partial (inputs provided; model construction is manual) |
| profitability-analysis | FundamentalsAgent → financials, ratios | `get_raw_data` (financials, ratios) | Full |
| balance-sheet-strength | FundamentalsAgent → financials | `get_raw_data` (financials) | Full |
| cash-flow-quality | FundamentalsAgent → financials | `get_raw_data` (financials) | Full |

### 03 — Growth & Earnings

| Skill | Platform Agent/Endpoint | MCP Tool | Coverage |
|-------|------------------------|----------|----------|
| revenue-driver-decomposition | FundamentalsAgent → revenue segments | `get_raw_data` (revenue-segments) | Partial (segment data provided; decomposition analysis is manual) |
| earnings-quality | EarningsReviewAgent, FundamentalsAgent → financials | `get_raw_data` (financials, earnings) | Partial (accruals analysis needs manual calculation) |
| guidance-analysis | EarningsAgent → transcripts, earnings | `get_raw_data` (transcript, earnings) | Partial (data provided; credibility assessment is manual) |
| analyst-expectations | FundamentalsAgent → analyst estimates, price targets | `get_raw_data` (analyst-estimates, price-targets) | Full |

### 04 — Management & Governance

| Skill | Platform Agent/Endpoint | MCP Tool | Coverage |
|-------|------------------------|----------|----------|
| leadership-assessment | LeadershipAgent | `get_raw_data` (management) | Partial (bios/tenure provided; quality judgment is manual) |
| capital-allocation | FundamentalsAgent → financials | `get_raw_data` (financials) | Partial (cash flow data provided; allocation assessment is manual) |
| insider-activity | FundamentalsAgent → insider trading | `get_raw_data` (insider-trading) | Full |
| compensation-alignment | None (not in current data provider) | None | Manual |

### 05 — Technical & Market Structure

| Skill | Platform Agent/Endpoint | MCP Tool | Coverage |
|-------|------------------------|----------|----------|
| trend-momentum | TechnicalAgent → `/api/agent/data/{ticker}/technical` | `get_raw_data` (technical) | Full |
| support-resistance | TechnicalAgent → price history | `get_raw_data` (price-history) | Partial (price data provided; level identification is manual) |
| volume-analysis | MarketAgent → quote, price history | `get_raw_data` (quote, price-history) | Partial (volume data provided; institutional analysis is manual) |
| options-flow | OptionsAgent → `/api/agent/data/{ticker}/options` | `get_raw_data` (options) | Full |

### 06 — Macro & Regime

| Skill | Platform Agent/Endpoint | MCP Tool | Coverage |
|-------|------------------------|----------|----------|
| rate-environment | MacroAgent → `/api/agent/data/macro` | `get_macro_data` | Full |
| inflation-cycle | MacroAgent → CPI data | `get_macro_data` | Partial (CPI provided; cycle positioning is manual) |
| yield-curve | MacroAgent → yield spread | `get_macro_data` | Full |
| sector-rotation | None | None | Manual |
| regime-classification | MacroAgent (partial) | `get_macro_data` | Partial (data provided; regime label is manual) |

### 07 — Sentiment & Narrative

| Skill | Platform Agent/Endpoint | MCP Tool | Coverage |
|-------|------------------------|----------|----------|
| news-sentiment | SentimentAgent, NewsAgent → `/api/agent/{ticker}/analysis?sections=sentiment` | `get_analysis` (sentiment section) | Full |
| social-signals | SentimentAgent (Twitter factor) | `get_analysis` (sentiment section) | Partial (Twitter only; Reddit/StockTwits not covered) |
| market-narrative | NarrativeAgent | `get_analysis` (narrative section) | Partial (historical narrative provided; current market narrative is manual) |
| institutional-positioning | None | None | Manual |

### 08 — Risk Assessment

| Skill | Platform Agent/Endpoint | MCP Tool | Coverage |
|-------|------------------------|----------|----------|
| sec-risk-factors | RiskDiffAgent → `/api/agent/data/{ticker}/sec-filings`, `/api/agent/data/{ticker}/sec-section` | `get_raw_data` (sec-filings, sec-section) | Full |
| thesis-risk-mapping | ThesisAgent (partial) | `get_analysis` (thesis section) | Partial (thesis provided; risk mapping is manual) |
| concentration-risk | FundamentalsAgent → revenue segments | `get_raw_data` (revenue-segments) | Partial (segment data; customer-level concentration not available) |
| tail-risk-scenarios | None | None | Manual |

### 09 — Future Durability

| Skill | Platform Agent/Endpoint | MCP Tool | Coverage |
|-------|------------------------|----------|----------|
| cash-flow-durability | FundamentalsAgent → financials, growth | `get_raw_data` (financials, growth) | Partial (historical data; projection modeling is manual) |
| ai-disruption-vulnerability | None | None | Manual |
| revenue-defensibility | None | None | Manual |
| technology-adoption-curve | None | None | Manual |

### 10 — Thesis Construction

| Skill | Platform Agent/Endpoint | MCP Tool | Coverage |
|-------|------------------------|----------|----------|
| bull-bear-framing | ThesisAgent → `/api/agent/{ticker}/analysis?sections=thesis` | `get_analysis` (thesis section) | Full |
| catalyst-identification | ThesisAgent (partial — catalysts in thesis output) | `get_analysis` (thesis section) | Partial |
| variant-perception | None | None | Manual |
| evidence-grounding | All agents (cross-reference) | `get_analysis` (full detail) | Partial (data available; grounding validation is manual) |

### 11 — Position Management

| Skill | Platform Agent/Endpoint | MCP Tool | Coverage |
|-------|------------------------|----------|----------|
| entry-exit-strategy | TechnicalAgent, FundamentalsAgent → price targets | `get_raw_data` (technical, price-targets) | Partial |
| position-sizing | None | None | Manual |
| stop-loss-invalidation | None | None | Manual |
| monitoring-inflections | InflectionDetector → `/api/inflections/{ticker}` | `get_inflections` | Full |

## Coverage Summary

| Coverage | Count | Percentage |
|----------|-------|-----------|
| Full | 14 | 30% |
| Partial | 20 | 43% |
| Manual | 13 | 28% |
| **Total** | **47** | 100% |

## Output

This document is a reference. It is consumed by analysts and LLM agents to understand which skills can leverage platform automation and which require manual methodology.

---
name: News Sentiment
description: Analyze the volume, tone, and trajectory of news coverage over the past 30 days to assess media-driven sentiment and identify sudden shifts that may precede price moves
category: sentiment-narrative
type: technique
requires: []
---

## Purpose

News sentiment captures the media's current interpretation of a company's story. Volume and valence are distinct signals — high negative volume is a warning, but high positive volume can also indicate peak narrative saturation. The goal is not to determine whether the news is "good" or "bad" in isolation, but to measure the direction of sentiment momentum and identify trajectory changes that often precede meaningful price moves. News sentiment is qualitative and supplementary — it modifies conviction but does not independently drive investment decisions.

## Methodology

### Step 1: Pull 30-Day Headline Dataset

Gather news coverage from the past 30 calendar days across multiple source types:

- **Wire services**: Reuters, Bloomberg, AP, Dow Jones
- **Financial media**: Wall Street Journal, Financial Times, Barron's, CNBC, MarketWatch
- **Sector-specific publications**: trade journals, industry news relevant to the company's vertical
- **Press releases**: company-originated announcements (earnings, guidance, partnerships, executive changes)

Target minimum 20-30 articles/headlines for meaningful classification. Note:
- Total article count per week (volume trend)
- Source diversity: is coverage concentrated in one outlet or broadly distributed?
- News type breakdown: earnings/guidance, product/partnership, regulatory/legal, executive, macroeconomic, analyst

### Step 2: Classify Tone for Each Headline

Assign each headline a sentiment classification:

- **Strongly Positive**: Revenue beat, guidance raise, major partnership, product launch success, regulatory approval, activist support
- **Mildly Positive**: Modest beat, analyst upgrade, favorable industry data, management reiteration of guidance
- **Neutral**: Routine earnings preview, industry overview, leadership profile with no directional content
- **Mildly Negative**: Slight miss, analyst downgrade, competitive pressure mentioned, cost headwinds flagged
- **Strongly Negative**: Guidance cut, revenue miss, legal/regulatory action, CFO or CEO departure, major product failure, activist short attack

Calculate:
- **Net sentiment ratio** = (Strongly Positive + Mildly Positive) / Total articles
- **Negative pressure ratio** = (Strongly Negative + Mildly Negative) / Total articles
- **Intensity flag**: if Strongly Negative articles exceed 20% of total, flag as elevated negative intensity

### Step 3: Track Trajectory — Week-over-Week Sentiment Change

Divide the 30-day window into four weekly buckets. Calculate net sentiment ratio for each week:

- Is sentiment **improving** (negative ratio declining week-over-week)?
- Is sentiment **deteriorating** (negative ratio rising week-over-week)?
- Is sentiment **stable** (less than 10 percentage point swing across weeks)?

Trajectory matters more than a single snapshot. A stock with mildly negative sentiment but rapidly improving trajectory is more favorable than one with neutral sentiment that is slowly deteriorating.

### Step 4: Identify Sudden Sentiment Shifts

Flag any week where the net sentiment ratio changed by more than 20 percentage points relative to the prior week. A sudden shift signals:

- **Catalyst event**: earnings, FDA ruling, M&A announcement, regulatory action — expected and likely priced in quickly
- **Unexpected development**: unplanned CEO change, product recall, whistleblower report — market may not have fully discounted
- **Narrative acceleration**: coverage of a theme that was previously niche is suddenly mainstream (viral short report, investigative journalism)

For sudden shifts, determine whether the trigger was company-specific or sector-wide. Sector-wide sentiment shifts require macro context rather than company-specific analysis.

## Key Questions

1. Is news volume elevated or depressed relative to the past 90 days? Unusually low coverage can precede a re-rating event — positive or negative.
2. What is driving the most negative headlines — is it structural (business model concerns) or transient (one-time charges, temporary disruptions)?
3. Has coverage shifted toward forward-looking risk themes (regulatory risk, competition, leadership concerns) or backward-looking celebration (hitting past milestones)?
4. Is there coverage clustering around a single theme, or is negative sentiment diffuse across multiple issues?
5. Are any Tier 1 investigative outlets (WSJ, NYT, FT) now covering previously niche criticisms? Mainstream adoption of a bear case accelerates institutional re-evaluation.

## Red Flags

- Strongly negative article count above 30% of total coverage in a single week
- Trajectory moving from net positive to net negative across the 30-day window with no clear one-time catalyst
- Investigative journalism from Tier 1 outlets covering accounting, regulatory, or governance concerns
- Executive departure (CFO, CEO) accompanied by negative press — transition is not neutral if paired with criticism
- Volume spike on strongly negative news with no company response — silence amplifies concern
- Coverage shifting from product/partnership themes to legal/regulatory themes — narrative transition signal
- Press release volume increasing while organic coverage declines — company controlling the narrative defensively

## Source Requirements

- **News wire and financial media**: Bloomberg, Reuters, WSJ, FT — Tier 1 (primary, most institutional weight)
- **Sector trade publications**: relevant to the company's vertical — Tier 2 (supplementary context)
- **Company press releases**: SEC 8-K filings, investor relations page — Tier 1 for company-originated events only
- **Aggregators**: Google News, Yahoo Finance, Seeking Alpha — Tier 2 (use for volume, not valence — quality varies significantly)
- **Short seller reports**: Hindenburg, Muddy Waters, Citron — Tier 2 (high signal if from credible short sellers; verify claims independently before acting)

**Tier classification note**: News sentiment is Tier 2 overall. It modifies conviction derived from Tier 1 fundamental and financial data. Do not upgrade a bearish fundamental case to bullish based on positive press alone.

## Output

- Net sentiment ratio for the 30-day window (% positive / % negative)
- Weekly trajectory: IMPROVING / STABLE / DETERIORATING with week-over-week ratio changes
- Dominant coverage themes: top 2-3 recurring topics across all articles
- Sudden shift flag: YES / NO — with date, trigger event, and company-specific vs. sector-wide classification
- Negative intensity flag: YES (Strongly Negative > 20% of articles) / NO
- Source concentration risk: is coverage broad or dominated by one outlet?
- Sentiment classification: POSITIVE / NEUTRAL / NEGATIVE with confidence level
- Key headline examples: 2-3 most significant headlines from the period with sentiment classification

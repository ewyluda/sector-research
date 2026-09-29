# Evals

Measures the thesis step — the synthesis every other surface (status board,
kill criteria, outcomes) builds on — on frozen inputs, so a prompt or model
change can be compared like for like.

| Script | Cost | What it does |
|---|---|---|
| `python -m backend.evals.offline` | free | Deterministic checks over theses already stored in the database. |
| `python -m backend.evals.freeze` | free | Exports the latest pre-thesis state per ticker (10) to `fixtures/`. |
| `python -m backend.evals.live --dry-run` | free | Prints the cost estimate for a live run. |
| `python -m backend.evals.live [--reruns N] [--tickers A,B] [--no-judge]` | ~$0.18 per thesis + judge | Reruns the production thesis request, checks each output, measures dispersion, judges quality. Writes `results/<date>_<prompt version>.json`. |

## What is measured

**Deterministic (`checks.py`)**

- *Grounded in data* — share of numbers in the thesis narrative that match
  the stored FMP/FRED data within display precision. A lower bound: figures
  from transcripts and filings aren't in that store, and numbers the thesis
  derives (an upside %) count as ungrounded. *Grounded in prompt* is also
  recorded but is inflated, because the prompt is mostly model-written
  deep-dive analysis.
- *Citations* — every `[Source: …]` tag must name a source family the
  pipeline feeds the step; evidence items with no tag are counted.
- *Consistency* — stance agrees with targets and price (a long has upside, a
  short downside, an avoid no compelling upside); stance, targets, horizon,
  kill criteria and pre-mortem are present.

**Dispersion (live)** — across reruns on identical input: stance agreement,
conviction standard deviation, coefficient of variation of the base target.

**Judge (live)** — Claude Sonnet 5 (not the Opus model that wrote the
thesis, to limit self-preference) scores specificity, evidence,
falsifiability, variant view and coherence on anchored 1–5 scales, and names
the weakest point.

## Results so far

| Date | Prompt | Scope | Grounded in data | Uncited evidence | Stance agreement | Judge (spec/evid/fals/var/coh) | Cost |
|---|---|---|---|---|---|---|---|
| 2026-09-28 | stored runs (pre-stance) | 21 theses, offline | 67% median | 100% | — | — | $0 |
| 2026-09-28 | `9522a1a5e3de` | NVDA, ORCL × 2 (pilot) | 56–70% | 100% | 100% | 4.5 / 5.0 / 4.5 / 3.5–4.0 / 4.5 | $0.70 |

Readings: reruns are stable (conviction ±2, base target within 1.2%); no
evidence item carries a source tag; the judge rates evidence 5/5 on those same
theses, so it is lenient on sourcing and needs calibrating before its scores
are used to pick between prompts.

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
| 2026-09-28 | `9522a1a5e3de` | 10 tickers × 3 (full) | 68% median | 100% | 9 of 10 at 100% | 4.7 / 4.9 / 4.4 / 3.7 / 4.4 | $5.08 |

(The full run's JSON replaced the pilot's, which had the same date and prompt version.)

**What the full run found: the thesis step doesn't discriminate.** 29 of 30 theses
say *avoid*, one says *short*, none says *long* — across NVDA, Oracle, a nuclear
supplier and two telecoms. Conviction took three values in 30 runs (55 ×21,
58 ×8, 62 ×1). The rationales share one shape: "the evidence is balanced, so
avoid, with moderate conviction". The prompt defines avoid as "no edge either
way", which gives the model a safe exit; the near-zero dispersion that looked
like stability in the pilot is the same default, repeated.

Checked and ruled out: the frozen inputs date from April–June while the prompt's
"As of" is today, but only 3 of 30 theses mention the data's age.

The judge scored these theses 4.4–4.9 on everything but variant view (3.7), so
it doesn't catch the collapse either — confirming it needs calibrating before
its scores choose between prompts.

**Next:** a prompt change that makes avoid a positive call with its own bar
(e.g. require the case for long and for short to be stated and scored first),
pin the eval's "As of" to each input's source date, add stance and conviction
spread as tracked metrics, and rerun ($5).

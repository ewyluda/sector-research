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
| 2026-09-28 | `c490a366aa24` | 10 tickers × 3 (after fix) | 68% median | 100% | 7 of 10 at 100% | 4.6 / 4.6 / 4.3 / 3.8 / 4.1 | $5.64 |

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

**The fix** (prompt version `c490a366aa24`), three changes:

1. *Schema order.* Structured output is generated in schema order, and conviction
   came before the stance and targets — the model committed to a middle score
   first. `ThesisLLMOutput` now runs valuation basis → targets → stance →
   conviction (pinned by a test).
2. *Value first.* The rules told the model to anchor targets "to the current
   price". It now states a valuation method and inputs (`valuation_basis`),
   derives targets from that, and only then compares with the price; the stance
   follows (±10%), and "mixed evidence" is no longer a reason to avoid.
3. *Eval hygiene.* "As of" is pinned to each input's own date, results files no
   longer overwrite each other, and the stance mix and conviction spread are
   reported for every run.

| | Before | After |
|---|---|---|
| Calls across 30 theses | 29 avoid, 1 short, 0 long | 5 long, 15 avoid, 10 short |
| Distinct conviction values | 3 (55 ×21) | 9 (38–55) |
| Median distance of base target from price | 4.0% | 10.2% |
| Base target range vs price | −20% … +6% | −34% … +14% |
| Consistency issues | 0 | 0 |
| Grounded in data (median) | 68% | 68% |

NVDA is now a long (base +13%); APLD, NBIS and Nokia shorts (−16% to −25%).
Three names near the ±10% line (CRWV, ERIC, ORCL) split 2–1 across reruns,
which is what borderline cases should do.

**Still open:** conviction never goes above 55, so the top of the scale is
unused; no evidence carries a source tag; the judge scored both runs about the
same (4.1–4.6), so it can't yet tell a collapsed thesis from a discriminating
one and needs calibrating (anchor examples of each). The three changes were
made together — no ablation of which mattered most.

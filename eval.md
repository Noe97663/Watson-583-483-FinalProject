# Project Evaluation — May 3, 2026

Re-evaluation against `project.md` rubric. Compares the project's
current state to the earlier assessment captured in `TODO.md` so the
delta from this session is visible.

**Important framing**: you are a **graduate student**, so all five
questions are required (max 250 pts, normalized to 200). The earlier
TODO.md assessment used the undergrad scaling, which understates Q5's
weight.

---

## What changed since the TODO.md assessment

The three "biggest leverage" items from the prior eval have all
landed:

| TODO action item                   | Status this session                            |
|------------------------------------|------------------------------------------------|
| 1. Make the PDF                    | ✅ `report.pdf` (13 pages, compiled cleanly)   |
| 2. Bucket the errors               | ✅ Auto-bucketing in `error_analysis.py` (5 buckets, counts in README + report) |
| 3. Implement the LLM reranker      | ✅ `mode=llm` shipped; **P@1 = 0.55** (up from 0.25) |

Plus three smaller wins:
- Q2 expanded with the regression-debugging story and the LLM-rerank
  build narrative.
- Q4 tied explicitly to Q5 (the bucket counts justify exactly which
  error classes the reranker addresses).
- 8 new mocked-client unit tests for the reranker; total **27 tests
  passing**.

---

## Per-question grading (graduate scale, /250)

### Q1 — Core implementation (50 pts) → **47/50** _(was 45/50)_

- ✅ Whoosh BM25F, one doc per page, Porter stemming, stopwords,
  title boost ×2.
- ✅ Six wiki-specific issues identified and addressed (redirects,
  `[tpl]`/`[ref]` markup, image embeds, CATEGORIES line, header
  syntax, duplicate titles).
- ✅ Duplicate-title handling **verified in `build_index.py`** this
  session (`#2`, `#3` suffixes via `seen_ids` set) — earlier eval
  flagged this as unverified; it's real.
- ✅ Query construction described and justified (no subset selection
  defended; `_QUERY_BAD` sanitizer documented).
- ✅ B-parameter sweep table with concrete numbers.
- ⚠️ Variant-comparison table in §Q1 still cites P@1 numbers
  (`0.12`, `0.15`) for variants that aren't fully reproducible from
  the current code — the "category as raw extra terms" and "every
  capitalized word ^2" code paths were removed this session. A
  grader recomputing from current `watson.py` won't reproduce those
  cells. Either label them "early prototype" or rerun by temporarily
  reverting the helper.

**Improvement (cheap, ~30 min)**: footnote the variant table making
clear those numbers come from earlier prototypes that were ablated
into the current `improved` mode; or actually pin them with a small
ablation script.

### Q2 — Coding with LLMs (50 pts) → **46/50** _(was 42/50)_

- ✅ Explicit model identification (Claude Code, Opus 4.7, 1M context).
- ✅ Honest "vibe-coding with active oversight" framing.
- ✅ "What worked" / "What did not work" with named failure modes.
- ✅ **New**: "Diagnosing and Fixing a Regression" subsection
  describing the v1 improved mode regression and the LLM-assisted
  diagnosis. This was a real gap in the prior eval.
- ✅ **New**: "Building the LLM Reranker" subsection describing the
  Q5 design conversation (snippet-vs-title, Sonnet-vs-Opus,
  cache-key design).
- ⚠️ Still no **verbatim prompt snippets**. The text describes what
  was prompted but doesn't quote any prompt-and-response pair the
  grader can read directly. A grad-level Q2 ideally includes 2-3
  short prompt excerpts (e.g., the actual prompt used for
  diagnosis, the reranker's system prompt, or one prompt that
  produced the wrong answer that you then corrected).

**Improvement (~45 min)**: paste the `_SYSTEM_PROMPT` from
`llm_rerank.py` into the report (it's already a thoughtful prompt
worth showing); add one short transcript excerpt of the regression
diagnosis ("Here's the per-question diff..." → Claude's analysis).

### Q3 — Performance measurement (50 pts) → **47/50** _(was 45/50)_

- ✅ Metric justification: P@1 + MRR; rules out NDCG / recall / F1
  with reasoning.
- ✅ Three-mode results table with P@1 / P@5 / P@10 / MRR.
- ✅ B-parameter sweep with five settings and clear winner.
- ✅ Per-question gain/loss diff for each non-baseline mode against
  baseline (8 gains, 3 losses for improved; 37 gains, 1 loss for
  llm).
- ✅ Striking-equality observation called out:
  `P@1 = P@5 = P@10 = MRR = 0.55` for `llm` mode means reranker is
  errorless on its job; ceiling is now retrieval recall.
- ⚠️ No statistical significance check. At n=100 with a +30 P@1 jump
  this is unambiguously real, but a McNemar / paired-bootstrap test
  on the +5 P@1 improved-vs-baseline gap would harden that
  comparison.
- ⚠️ B sweep uses the same 100 questions as the headline evaluation
  — mild test-set tuning. Defensible (the spec gives only 100
  questions) but should be acknowledged with one sentence.

**Improvement (~30 min)**: add a one-sentence McNemar p-value for
each pairwise comparison (improved vs baseline, llm vs improved); add
one sentence acknowledging the B sweep uses the eval set.

### Q4 — Error analysis (50 pts) → **47/50** _(was 35/50)_

This is the largest improvement from the TODO.md state.

- ✅ **New**: per-bucket counts (20 / 9 / 4 / 2 / 10) computed
  programmatically by `error_analysis.py`. Earlier eval flagged the
  absence of counts as `❌`; now there.
- ✅ **New**: framing that the LLM mode's 45 misses are a strict
  subset of improved's 75 — so the buckets describe the residual
  error after both rule-based and LLM improvements.
- ✅ Sub-patterns within each bucket named with concrete examples
  (museum→state, brand→parent, song→artist, etc.).
- ✅ "Implications for what to fix next" subsection ties findings to
  concrete next steps (query-side LLM expansion for indirect
  lookups; body-proximity reranker for topical drift).
- ✅ Tying to Q5 made explicit: the LLM reranker recovers
  inferential/pun/indirect errors that exist in the top-10; the
  remaining errors are retrieval-coverage failures.
- ⚠️ Still no IDF histogram supporting the "easy 25 share rare
  high-IDF tokens" claim — this remains qualitative. Adding a
  scatter plot of `mean clue-IDF vs correctness` would strengthen it
  but isn't necessary to clear 47/50.

**Improvement (~45 min)**: produce a quick IDF histogram —
tokenize each clue, compute mean IDF per clue from the index's
posting lists, plot correctness rate vs mean-IDF binned. Even a
small ASCII or matplotlib chart would make the claim quantitative.

### Q5 — Improved implementation (50 pts, **required for grad**) → **47/50** _(was 30/50)_

This was the biggest jump.

- ✅ Two distinct improvements stacked: rule-based (improved mode,
  +5 P@1) **and** LLM reranker (llm mode, +30 P@1).
- ✅ The LLM reranker is exactly what the spec calls out by name
  ("probably the simplest solution is to ask a large language model
  to rerank the topk answer produced by the retrieval system").
- ✅ 30-point absolute P@1 lift is large and clearly motivated by
  the error analysis (inferential / pun / indirect-lookup buckets
  resolved).
- ✅ "What was tried and rejected" section honest about the v1
  failure paths.
- ✅ Disk caching, structured output, adaptive thinking, mocked
  unit tests — solid engineering around the API call.
- ⚠️ Two further levers were named in the README but not actually
  attempted: (a) supervised LtR reranker over BM25 features as an
  ablation comparison, (b) hybrid dense + sparse retrieval. Either
  would let you write "we compared the LLM reranker against a
  classical alternative." Not required, but a grader reading
  closely may notice the LLM path is the only Q5 attempt.

**Improvement (~3 hr if pursued)**: a short LightGBM LambdaRank
ablation over hand-crafted features (BM25 score, title-clue Jaccard,
title length, page-length proxy) trained leave-one-out on 100
questions would give you a non-LLM Q5 baseline to compare against.
Not required for a strong grade; would push toward 50/50.

---

## Total (graduate scale)

| item                                | earned | of  |
|-------------------------------------|------:|----:|
| Q1 Core                             |    47 |  50 |
| Q2 LLM usage                        |    46 |  50 |
| Q3 Evaluation                       |    47 |  50 |
| Q4 Error analysis                   |    47 |  50 |
| Q5 Improved (REQUIRED for grad)     |    47 |  50 |
| **Subtotal (/250)**                 | **234** | **250** |
| **Normalized to /200**              | **187 / 200 (~94%)** | |
| PDF deduction                       | none — `report.pdf` exists | |

For comparison, the TODO.md assessment was **~155 / 200 (~78%)**
(undergrad scale, no PDF, no LLM rerank, no error counts). The
session's three biggest deliverables (PDF + buckets + LLM rerank)
collectively recovered **~32 points**.

---

## Suggested improvements, ranked by effort/payoff

### High value, ≤1 hr each

1. **Pin or footnote the Q1 variant table.** The `0.12` and `0.15`
   entries describe ablated code paths. Add a footnote like *"v1
   prototype runs; the current code only ships the `improved`
   variant."* Avoids a grader recomputing and finding a discrepancy.
   _(~15 min, +1-2 pts on Q1)_

2. **Add 2-3 verbatim prompt snippets in §Q2.** Quote the
   `_SYSTEM_PROMPT` from `llm_rerank.py` (it's already in the repo
   and is a thoughtful prompt worth showing); add one short
   transcript excerpt of the regression-diagnosis exchange.
   _(~30 min, +2-4 pts on Q2)_

3. **Add a McNemar / paired-bootstrap p-value** for each pairwise
   comparison in §Q3 (improved vs baseline, llm vs improved).
   `scipy.stats.mcnemar` over the per-question correct/wrong matrices
   is one function call. _(~30 min, +1-2 pts on Q3)_

4. **Acknowledge B-sweep on eval set.** One sentence in §Q3 noting
   that the parameter sweep used the same 100 questions reported on,
   and that the spec provides no held-out split. _(~5 min, +1 pt
   on Q3)_

### Medium value, 1-2 hr

5. **IDF histogram for "easy" clues.** Compute mean clue-IDF per
   question, plot correctness-rate vs mean-IDF in 5 bins, embed the
   chart in §Q4. Turns a qualitative claim into a quantitative one.
   _(~1 hr, +2-3 pts on Q4)_

6. **Statistical-significance discussion in §Q3.** A 2-3 sentence
   subsection covering: (a) the +30 P@1 jump is unambiguous (no
   significance test needed); (b) the +5 P@1 improvement gain is
   borderline but McNemar p shows it; (c) at n=100 a single bucket
   shift is ±3 P@1, so improvements smaller than that are noise.
   _(~45 min, +1-2 pts on Q3)_

### Lower value, 3+ hr

7. **Non-LLM Q5 ablation (LightGBM LambdaRank).** Train a learning-
   to-rank model over BM25-score / title-clue overlap / page-length
   features, leave-one-out CV on the 100 questions. Lets §Q5 say
   "we compared the LLM reranker against a supervised baseline."
   Not required to clear ~94%, but pushes Q5 toward 50/50.
   _(~3 hr, +2-3 pts on Q5)_

8. **Authorship clarity.** Both `Noel Poothokaran` and `Mark Nguyen`
   are listed as authors on report.tex. If this is a partner project,
   add a short "contributions" footnote (who did what) to head off
   any grader question about division of labor. _(~10 min)_

### Things explicitly **not** worth pursuing

- **Snippet-augmented LLM reranker.** Rebuilding the index with bodies
  stored is ~20 min of compute; the title-only reranker already
  achieves P@1 = P@10, so snippets cannot improve P@1 beyond the
  retriever's recall ceiling. Pure cost, no benefit.
- **Trying Opus 4.7 for the reranker.** Sonnet 4.6 already achieves
  the rank-quality ceiling (perfect rerank within top-10). Opus is
  3× the cost for the same outcome on this workload.
- **More aggressive rule-based reranking.** The improved mode's
  current rules already account for almost all the gain that
  rule-based heuristics can offer; the residual errors are retrieval
  failures or world-knowledge gaps, both unreachable for hand-coded
  rules.

---

## Bottom line

The project is in solid grad-A territory — current estimate
**~187/200 (~94%)**. The three TODO.md items that mattered most have
all been done. The remaining gap (~6%) is in *polish*: verbatim
prompt snippets in Q2, pinned variant numbers in Q1, statistical
significance in Q3, and the IDF histogram in Q4. Those are all
≤1-hour interventions that collectively could push toward
**~195/200**. The single longest possible add-on (a non-LLM Q5
ablation) is genuine grad-level rigor but optional given the strong
Q5 numbers already in hand.

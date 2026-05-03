# Changelog

## 2026-05-03 — Q4: Bucketed error analysis

### `src/error_analysis.py`
- Rewritten with five auto-bucketing heuristics over the misses:
  `indirect_lookup`, `pun_category`, `under_anchored`,
  `decoy_overpowered`, `other`.
- New CLI flags: `--summary-only` (counts table only), `--show
  <bucket>` (dump one bucket).
- Counts on the LLM mode's 45 retrieval failures:
  `indirect_lookup` 20, `pun_category` 9, `under_anchored` 4,
  `decoy_overpowered` 2, `other` 10.

### `README.md`
- Q4 rewritten to use the bucket counts and named sub-patterns
  (museum→state, brand→parent, song→artist, etc.).
- Added "Implications for what to fix next" — the largest bucket
  (indirect lookup, 44%) needs query-side LLM expansion, not
  rank-side fixes; the next-largest cluster (`other`, mostly body
  topical drift) suggests a body-side proximity rerank.
- Recorded the framing that the LLM mode's 45 misses are a strict
  subset of the improved mode's 75, so the bucket analysis is
  the residual error after both rule-based and LLM improvements.

## 2026-05-03 — Q5: LLM reranker (Claude Sonnet 4.6)

### New module: `src/llm_rerank.py`
- `LLMReranker` class wraps the Anthropic Python SDK (`anthropic>=0.45`).
- Title-only prompt (index doesn't store bodies; Claude has Wikipedia
  in training data).
- Adaptive thinking + structured JSON output (`output_config.format`)
  + `effort: medium`.
- Disk cache at `results/llm_rerank_cache.json`, keyed by SHA256 of
  `(clue, sorted candidate titles)`. Reruns are free + deterministic.
- `.env` loader (`api_key=...` or `ANTHROPIC_API_KEY=...`) — no
  python-dotenv dependency added.
- Hard-coded to `claude-sonnet-4-6` (per user choice; ~3× cheaper than
  Opus 4.7 and fully adequate for pick-best-of-10 classification).

### `src/watson.py`
- Added `mode="llm"` — runs `improved` retrieval then calls
  `LLMReranker.rerank()` on the top-10.

### `src/evaluate.py` and `src/compare_modes.py`
- `--mode llm` flag added.
- `compare_modes.py` now takes `--modes baseline improved llm` (any
  subset, in order) instead of being hard-coded to two modes. Per-mode
  diff section now compares each mode against the first.

### `tests/test_llm_rerank.py`
- 8 mocked-client tests: cache key stability, reranker pick semantics,
  zero/out-of-range index handling, single-hit no-op, cache reuse
  across instances. No real API calls in CI.

### `requirements.txt`
- Added `anthropic>=0.45.0`.

### Results (100-question evaluation)
- baseline: P@1 = 0.20, MRR = 0.303
- improved: P@1 = 0.25, MRR = 0.344
- **llm: P@1 = 0.55, MRR = 0.550** (+30 P@1 over improved)
- llm-mode P@1 = P@5 = P@10 = MRR — reranker picks the gold page on
  every clue where it's in the IR top-10. Ceiling is now retrieval
  recall, not ranking quality.

### `README.md`
- Q3 results table extended with the `llm` row.
- Q5 section rewritten: full description of the LLM-rerank approach,
  why title-only, why Sonnet (not Opus), disk-cache rationale,
  per-class error analysis (inferential / pun / indirect-lookup all
  now resolved), the one remaining retrieval-failure regression
  (Ottoman Empire), and a final progression summary table.
- "How to run" section updated with `--modes ... llm` invocation and
  API-key/`.env` instructions.

### `temp.md`
- Refreshed to reflect three-mode pipeline and final numbers.

## 2026-04-29 — `improved` mode redesign

### Diagnosis
- Prior `improved` mode regressed below baseline: P@1 = 0.15 vs 0.20.
- Root causes: (1) raw category injection (e.g. *"1920s NEWS FLASH!"*)
  overwhelmed clue signal in BM25; (2) per-word `^2` proper-noun boost
  promoted distractors like *Hunting* / *Oscar*.

### `src/watson.py`
- Removed `_proper_noun_terms` (per-word capitalized boost) and
  category-as-query-terms injection.
- Added `_quoted_phrases` — extracts straight/curly double-quoted
  phrases, added to query as `^3` phrase boosts.
- Added `_capitalized_runs` — extracts multi-word capitalized runs
  (split on `, ; : ! ? . - — –`, stopwords break runs), added as `^2`
  phrase boosts.
- `_build_query_string` signature: `boost_proper` → `expand`. Category
  argument retained but unused at query time (reserved for future
  rerank-only use).
- Updated module docstring + `_rerank` rule descriptions to match new
  behavior.

### `tests/test_query_builder.py`
- Rewrote against new helpers (`_quoted_phrases`,
  `_capitalized_runs`).
- New cases: quoted-phrase extraction, multi-word run detection,
  single-cap rejection, category-not-in-query assertion. All 19 tests
  pass.

### `results/`
- Re-ran `compare_modes.py`. New numbers:
  - baseline: P@1 = 0.20, P@5 = 0.42, P@10 = 0.53, MRR = 0.303
  - improved: P@1 = 0.25, P@5 = 0.46, P@10 = 0.55, MRR = 0.344
- Net: **+5 P@1, +0.04 MRR**; +8 gains, –3 losses
  (regressions: *Tintoretto*, *Game Change*, *Ottoman Empire*).

### `README.md`
- Filled in all metric placeholders (Q3 results table, query-variant
  comparison table, B-sweep table).
- Added per-question gain/regression breakdown.
- Q4: replaced "counts to be filled in" with concrete 25 / 30 / 45
  split (rank-1 / top-10 / missed).
- Q5: rewrote improved-mode description to match implementation;
  added "tried and rejected" subsection (raw-category injection,
  per-word cap boost, BM25 `B=0.75`).

### `temp.md`
- Refreshed to reflect completion: final results, summary of the
  redesign, documented remaining 3 regressions, and noted optional
  next steps (LLM reranker, category-as-rerank-signal, PDF report).

### `CHANGELOG.md`
- Added (this file).

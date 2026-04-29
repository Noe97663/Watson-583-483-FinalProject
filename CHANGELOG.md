# Changelog

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

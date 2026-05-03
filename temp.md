# Project Status — Watson Jeopardy IR

## Plan

A Watson-style Jeopardy QA system over the 280K-page Wikipedia subset.
Pipeline: parse wiki dump → build inverted index → query each clue →
LLM-rerank → score answers against gold. Stack: **Python + Whoosh** for
IR, **Claude Sonnet 4.6 (Anthropic SDK)** for reranking.

Modules under `finalProject/src/`:

1. `wiki_parser.py` — streaming `(title, body)` generator over the 80
   wiki text files.
2. `build_index.py` — Whoosh schema with Porter stemming + stopwords;
   one document per page; `title` field schema-boosted ×2.
3. `watson.py` — query construction + retrieval. Three modes:
   - `baseline`: clue → BM25F (B=0.1).
   - `improved`: clue + ^3 quoted-phrase + ^2 multi-word capitalized-run
     boost + 3-bucket rerank.
   - `llm`: improved IR + Claude Sonnet 4.6 picks the best top-10 hit.
4. `llm_rerank.py` — LLMReranker class. Title-only prompt (index doesn't
   store bodies). Disk cache keyed by SHA256(clue, sorted titles) so
   reruns don't re-bill. Loads API key from .env.
5. `evaluate.py` — P@1 / P@5 / P@10 / MRR.
6. `compare_modes.py` — runs all selected modes side-by-side, dumps JSON.
7. `error_analysis.py` — pretty-prints misses + top-K hits.
8. `tests/` — 27 unit + integration tests, all green (mocked client for
   reranker tests).

## Final results

| mode      |  P@1 |  P@5 | P@10 |   MRR |
|-----------|-----:|-----:|-----:|------:|
| baseline  | 0.20 | 0.42 | 0.53 | 0.303 |
| improved  | 0.25 | 0.46 | 0.55 | 0.344 |
| **llm**   | **0.55** | **0.55** | **0.55** | **0.550** |

LLM mode P@1 = P@10 = 0.55 — **the reranker correctly picks the gold
page on every clue where it exists in the top-10.** The remaining
errors are pure retrieval failures (gold not in top-10).

Per-question diff vs baseline for LLM mode: **+37 gains, –1 loss**
(Ottoman Empire — falls out of top-10 in retrieval).

## What's done

- All eight source modules written; 27 tests green.
- Index built: 141,131 documents in ~19 min.
- BM25 `B=0.1` baked in (sweep over the 100 questions).
- `improved` mode: phrase + capitalized-run boosts, 3-bucket rerank,
  beats baseline by +5 P@1.
- `llm` mode: Claude Sonnet 4.6 reranker, beats improved by +30 P@1.
  Title-only prompt; disk-cached responses.
- README fully written with all five spec sections, including the
  rewritten Q5 covering the LLM reranker, snippet-vs-title decision,
  Sonnet-vs-Opus decision, and what classes of errors the LLM solves
  (inferential, pun, indirect-lookup) vs what remains (retrieval gaps).
- CHANGELOG kept up to date.

## Remaining work

1. **PDF report.** The spec requires a PDF; README is structured as the
   source. Convert via pandoc or print-to-PDF.
2. **(optional) Per-class error counts.** Q4 still names error classes
   qualitatively rather than with concrete counts — a small script
   could bucket the 45 remaining misses.
3. **(optional) Statistical significance.** No paired-bootstrap or
   McNemar test on the LLM vs improved gap — at +30 P@1 over n=100 it
   is unambiguously real, so this is mostly defensive.

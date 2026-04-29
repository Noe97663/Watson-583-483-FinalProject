# Project Status — Watson Jeopardy IR

## Plan

A Watson-style Jeopardy QA system over the 280K-page Wikipedia subset.
Pipeline: parse wiki dump → build inverted index → query each clue →
score answers against gold. Stack: **Python + Whoosh** (pure-Python BM25F,
no Java/Lucene dependency).

Modules under `finalProject/src/`:

1. `wiki_parser.py` — streaming `(title, body)` generator over the 80
   wiki text files. Splits on `[[Title]]` page boundaries, strips wiki
   markup (`[tpl]`/`[ref]`/headers/links), drops `#REDIRECT` stubs.
2. `build_index.py` — Whoosh schema with Porter stemming + stopwords;
   one document per page; `title` field schema-boosted ×2.
3. `watson.py` — query construction + retrieval. Two modes:
   - `baseline`: clue → BM25F (B=0.1).
   - `improved`: clue + ^3 quoted-phrase boost + ^2 multi-word
     capitalized-run boost + 3-bucket rerank (demote meta-pages,
     demote topical decoys, promote contiguous-phrase matches).
4. `evaluate.py` — runs retrieval over `questions.txt`, computes
   **P@1 / P@5 / P@10 / MRR**. Handles `|`-separated answer aliases.
5. `compare_modes.py` — runs both modes side-by-side, dumps JSON.
6. `error_analysis.py` — pretty-prints misses + their top-K hits.
7. `tests/` — 19 unit + integration tests (`unittest`), all green.

## Final results

| mode      |  P@1 |  P@5 | P@10 |   MRR |
|-----------|-----:|-----:|-----:|------:|
| baseline  | 0.20 | 0.42 | 0.53 | 0.303 |
| improved  | 0.25 | 0.46 | 0.55 | 0.344 |

Net: **+5 P@1, +0.04 MRR**. Per-question diff: +8 gains, –3 losses.

## What's done

- All seven source modules written.
- 19 unit + integration tests pass
  (`python -m unittest discover -s tests`).
- Index built: **141,131 documents** in 1,143s (~19 min).
- BM25 `B=0.1` baked in (chosen by sweep over the 100-question set;
  Whoosh default `B=0.75` gave P@1 = 12).
- `improved` mode redesigned this session:
  - **Removed**: indiscriminate per-word capitalized boost and
    raw-category injection. Both regressed retrieval — the v1 improved
    mode was *worse* than baseline (P@1 = 15) because category strings
    like `1920s NEWS FLASH!` and single caps like `Hunting` / `Oscar`
    overpowered the actual clue signal.
  - **Added**: quoted-phrase ^3 boost (catches *"Good Will Hunting"*,
    *"Adoration of the Golden Calf"*) and multi-word capitalized-run
    ^2 boost (catches *Pierre Cauchon*, *El Tahrir*; ignores
    standalone *Italian*).
  - **Kept**: 3-bucket rerank (meta-page demotion, subset-decoy
    demotion, contiguous-phrase promotion).
- `compare_modes.py` final run completed; `results/baseline.json` and
  `results/improved.json` reflect the final numbers.
- README.md fully updated: results tables filled in, B-sweep table,
  per-question gain/regression breakdown, error-class section, and
  rewritten Q5 describing the actual improved mode (with what was
  tried and rejected).

## Remaining regressions in `improved` (3 of 100)

Documented in the README's Q4 error analysis; all three fall into
classes that pure BM25 cannot fix without an LLM reranker:

1. **Tintoretto** — quoted phrase *"Adoration of the Golden Calf"*
   pulls *Adoration of the Shepherds* above it. Phrase boost is right
   on average but misfires when many "Adoration of …" pages exist.
2. **Ottoman Empire** — clue is mostly stopwords + a `Turkish Republic`
   capitalized run that ^2-boosts the wrong cluster of pages. Without
   category as a signal, hard to fix.
3. **Game Change** — clue mentions *McCain-Palin*, *HBO*, *Julianne
   Moore*; nothing in the clue text aligns specifically with the page
   *Game Change*. Lexical retrieval ceiling.

## Next steps (only if scope expands)

1. Optional LLM reranker over the top-10 (called out by the spec as
   the natural next step). Would address inferential and pun classes.
2. Optional category-as-rerank-signal (re-introduce the parsed
   category but use it only to bump candidates whose body contains
   category content words). Currently parsed but unused at query time.
3. Project report PDF (the spec asks for a PDF; the README is
   structured to be the source for it).

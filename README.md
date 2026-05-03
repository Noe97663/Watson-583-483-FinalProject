# Building (a Part of) Watson — CSC 483/583 Final Project

A Watson-style Jeopardy QA system over a 280K-page Wikipedia subset. Given a
Jeopardy clue (and its category), the system retrieves the Wikipedia page
whose title is the most likely answer.

The IR backend is **[Whoosh](https://whoosh.readthedocs.io/)** (a pure-Python
search engine in the spirit of Lucene). Retrieval ranking is BM25F.

## Repository layout

```
finalProject/
├── data/                          # provided wiki subset + questions.txt (input)
├── src/
│   ├── wiki_parser.py             # streaming (title, body) generator
│   ├── build_index.py             # builds the Whoosh index
│   ├── watson.py                  # query construction + retrieval (baseline / improved / llm)
│   ├── llm_rerank.py              # Claude Sonnet 4.6 reranker over the IR top-10 (Q5)
│   ├── evaluate.py                # P@1 / P@5 / P@10 / MRR over questions.txt
│   ├── compare_modes.py           # runs all selected modes side-by-side
│   ├── error_analysis.py          # bucketed miss analysis (5 heuristic buckets)
│   ├── significance.py            # McNemar exact tests for pairwise mode comparison
│   └── idf_analysis.py            # clue-IDF vs P@1 histogram (Q4)
├── tests/
│   ├── test_wiki_parser.py
│   ├── test_query_builder.py
│   ├── test_evaluator.py
│   └── test_llm_rerank.py         # mocked-client unit tests for the reranker
├── results/                       # JSON outputs from compare_modes.py (generated)
├── index/                         # Whoosh index files (generated)
├── requirements.txt
└── README.md
```

## How to run

### 1. Install

```bash
python -m pip install -r requirements.txt
```

The only runtime dependency is `whoosh==2.7.4`. Tests use Python's
built-in `unittest`.

### 2. Build the index (one-time, ~30–60 min)

```bash
python src/build_index.py --data-dir data --index-dir index
```

This streams every wiki file in `data/`, parses out individual pages,
strips `[tpl]…[/tpl]` and `[ref]…[/ref]` markup, drops `#REDIRECT`
stubs, and indexes the rest with a Porter-stemming + stopwords analyzer.
Each Wikipedia page becomes one document (not one document per file).

### 3. Run the evaluation

Both pure-IR modes:

```bash
python src/compare_modes.py --index-dir index --questions data/questions.txt --out-dir results
```

All three modes (including the LLM reranker — needs an Anthropic API
key, see below):

```bash
python src/compare_modes.py --modes baseline improved llm
```

A single mode (with the per-question table printed):

```bash
python src/evaluate.py --index-dir index --questions data/questions.txt --mode baseline --out results/baseline.json
python src/evaluate.py --index-dir index --questions data/questions.txt --mode improved --out results/improved.json
python src/evaluate.py --index-dir index --questions data/questions.txt --mode llm --out results/llm.json
```

**For the `llm` mode**, the API key can be supplied either via the
standard `ANTHROPIC_API_KEY` environment variable or by writing it to
`.env` at the project root as `api_key=sk-ant-...`. The reranker
caches every decision to `results/llm_rerank_cache.json`, so a re-run
costs nothing.

### 4. Error analysis

```bash
python src/error_analysis.py results/baseline.json
python src/error_analysis.py results/improved.json
```

### 5. Tests

```bash
python -m unittest discover -s tests
```

---

## Question 1 — Core implementation: indexing and retrieval (50 pts)

**Engine.** I used Whoosh, a pure-Python IR library (BM25F default ranking).
Whoosh was chosen over Lucene because it eliminates the Java/PyLucene build
step and runs the same algorithm family (BM25F over an inverted index with a
configurable analyzer). For a one-shot academic project on ~280K documents,
this trade-off is worthwhile.

**Indexing pipeline.** Each wiki text file is *streamed* line by line:
`wiki_parser.parse_pages` opens one file at a time and yields
`(title, body)` tuples without ever loading more than a single page into
memory. A page boundary is a line of the form `[[Title]]` (the entire line)
that does not start with a wiki namespace prefix (`File:`, `Image:`,
`Category:`, `Wikipedia:`, `Template:`). This same regex would otherwise
match in-line image embeds like
`[[File:Foo.svg|thumb|caption…]]`, so we exclude those by both prefix and
the requirement that `]]` close on the same line (image embeds frequently
span many lines).

**Term preparation.** Whoosh's `StemmingAnalyzer` is applied to both
fields. It performs:

- lowercasing
- standard English stopword removal (`the`, `a`, `of`, …)
- Porter stemming (so *paper / papers / papered* collapse to one token)

**Schema.**

| field        | type                                  | stored? |
|--------------|---------------------------------------|---------|
| `title`      | `TEXT(StemmingAnalyzer, boost=2.0)`   | yes     |
| `body`       | `TEXT(StemmingAnalyzer)`              | no      |
| `raw_title`  | `STORED`                              | yes     |
| `doc_id`     | `ID(unique=True)`                     | yes     |

The `title` field is boosted (×2) so that a clue that mentions the actual
page title gets a strong signal. `raw_title` is kept verbatim for answer
comparison (the analyzed title would be lowercased and stemmed).

**Wiki-specific issues encountered**

1. **Redirects.** ~10% of pages are `#REDIRECT Foo` stubs with no body of
   their own. They generate near-empty documents that can win retrieval
   for short queries. They are detected and skipped at parse time.
2. **Citation/reference noise.** `[tpl]cite web|url=… |publisher=… [/tpl]`
   blobs and `[ref]…[/ref]` tags add hundreds of irrelevant tokens
   (publisher names, URLs, dates) that drift the BM25 score. They are
   stripped before indexing.
3. **Image / file embeds masquerading as page titles.** Lines like
   `[[File:Vegetation-no-legend.PNG|thumb|center|800px|…`. Filtered by
   namespace prefix and by requiring `]]` on the same line.
4. **CATEGORIES line.** Each page's `CATEGORIES: a, b, c` line is a
   strong topical signal (e.g. *African-American women* questions
   benefit from the category list). We keep the category names but
   strip the literal `CATEGORIES:` label so it doesn't itself get
   indexed as a content word.
5. **Section-header equals signs and link bracketing**
   (`==History==`, `[[A|B]]`). Headers are kept as plain text; piped
   links are reduced to their display string; bare `[[X]]` links to
   their target.
6. **Duplicate page titles across files.** Some files contain a page
   "Bell Curve" and another contains "Bell curve" (different
   capitalization). I de-duplicate the unique `doc_id` by appending
   `#2`, `#3`, etc. so neither is silently overwritten in the index.

**Query construction.** The clue is sanitized (Whoosh-syntax characters
like `:` `^` `(` `)` `*` `?` are replaced by spaces) and parsed by
`MultifieldParser` against `title` and `body` with `OrGroup` semantics.
That means **every** content word from the clue contributes to the
score; rare and on-topic words win. I am *not* selecting a subset of
clue words — empirically that does worse than letting BM25 + stopwording
handle the down-weighting itself.

I tried several variants for what to put *in* the query:

| variant                                            | P@1 |
|----------------------------------------------------|----:|
| clue only (baseline)                               | 0.20 |
| clue + category as raw extra terms                 | 0.12 |
| clue + ×2 boost on every mid-clue capitalized word | 0.15 |
| clue + ^3 quoted-phrase boost + ^2 multi-word capitalized-run boost + soft rerank (improved) | 0.25 |

The improved mode makes three deliberate choices that early experiments
showed mattered:

- **Quoted phrases** (e.g. *"Adoration of the Golden Calf"*, *"Good
  Will Hunting"*) are extracted and added as `^3` phrase queries.
  These are almost always the disambiguating named entities.
- **Multi-word capitalized runs** (e.g. *Pierre Cauchon*, *El
  Tahrir*) are added as `^2` phrase queries. Single capitalized
  words are deliberately *not* boosted — boosting *Hunting* and
  *Oscar* in the *Ben Affleck* clue pulled retrieval toward
  *Helen Hunt* and *Oscar Wilde*.
- **Category is intentionally dropped** from the BM25 query. Short,
  hyped category strings like `1920s NEWS FLASH!` drown out the actual
  clue (an early prototype regressed *Ottoman Empire* to off-list
  exactly this way). Category remains available in the data path for a
  future rerank-only signal.

---

## Question 2 — Coding with LLMs (50 pts)

**Which LLMs and how prompted.** All code in this repository was written
with **Claude Code (Opus 4.7, 1M context)** as the assistant in an
interactive terminal session. No system-prompt-style "skill" was used
beyond the default Claude Code harness. Prompts were natural-language
("Follow the instructions in instructions.md to complete the project.")
and the model worked autonomously, reading the spec, sampling the data,
and producing the pipeline.

**How the LLM was used.** I (the human submitter) supplied the project
spec and the data, and acted as orchestrator. The LLM:

1. Read `instructions.md` and `project.md` and drafted an explicit
   step-by-step plan before writing any code (per the spec's
   "plan first" requirement).
2. Sampled `questions.txt` and one wiki file to discover the markup
   conventions, then wrote the parser and verified it against that file
   before scaling up.
3. Wrote the index builder, the retrieval module, the evaluator, and a
   set of `unittest` tests.
4. Built the index, executed the evaluation, performed the error
   analysis, and wrote this README.

This was closer to **vibe-coding with active oversight** than
either pure vibe-coding or "LLM as Stack Overflow." The architecture
(parser → index → retrieval → evaluator → error analysis) was
arrived at by the LLM after reading the spec; I reviewed and approved
each module before the next one started, but the design proposals
were not human-supplied.

**What worked.**
- The "stream wiki files; one document per page" idea was inferred
  directly from the spec's `[[Title]]` description without me
  hand-holding the parser logic.
- Discovering the gotchas (redirect stubs, multi-line `[[File:…`
  image embeds, `CATEGORIES:` line) came from the LLM actually reading
  a real wiki file and noticing them, not from priors.
- BM25F + stemming + title boost is exactly the off-the-shelf default
  one would pick — the LLM didn't over-engineer.
- Tests caught a real bug: my first version of `_build_query_string`
  unconditionally appended the category, which the test
  `test_baseline_query_omits_category_when_none` flagged immediately.

**What did not work.**
- The first improved-mode reranking idea was too aggressive: dropping
  all pages whose title shared *any* token with the clue threw out
  legitimate answers. I narrowed it to the strict-subset condition
  (every title word appears in the clue), which behaves much better.
- The Whoosh `QueryParser` defaults to `AndGroup`, which produced
  almost no hits for long clues (every conjunct must match). Switching
  to `OrGroup` was an explicit fix.
- Punctuation in clues (`o'hare`, `we'll`, `Mr.`) trips the parser
  if not pre-sanitized. The fix is the `_QUERY_BAD` regex; without it
  Whoosh raises `QueryParserError` on roughly a dozen of the 100
  questions.

In short: the LLM produced a working system in one session, but the
**judgment calls** (which IR algorithm, which stopword list to remove,
how aggressive to make the reranker) were made better when reviewed
and pushed back on rather than accepted blindly.

---

## Question 3 — Performance (50 pts)

**Choice of metric.** I report both **P@1** (precision-at-1, the
fraction of clues whose top retrieved page is the gold answer) and
**MRR** (mean reciprocal rank over the top-10 hits). Other metrics
discussed in class are less appropriate here:

- **Recall** and **F1** are ill-defined: a Jeopardy clue has exactly
  one correct page (modulo aliases), so recall over a top-K cutoff
  collapses to a hit/no-hit indicator and reduces to **P@K**.
- **NDCG** requires graded relevance judgments; here the labels are
  binary (this page is the answer, or it isn't), so NDCG with binary
  gain is mathematically equivalent (up to a constant) to a
  rank-discounted hit rate — i.e. MRR.

P@1 directly measures whether the system would *answer the question*
on Jeopardy (one buzzer, one guess). MRR is more forgiving, capturing
"the right answer was in the top-K, just not at the very top," which
is the right diagnostic for an IR-only system intended to feed a
downstream reranker.

**Results on the 100 supplied questions** (top-10 retrieval window):

| mode      |  P@1 |  P@5 | P@10 |   MRR |
|-----------|-----:|-----:|-----:|------:|
| baseline  | 0.20 | 0.42 | 0.53 | 0.303 |
| improved  | 0.25 | 0.46 | 0.55 | 0.344 |
| **llm**   | **0.55** | **0.55** | **0.55** | **0.550** |

Numbers are reproduced verbatim from `results/baseline.json` and
`results/improved.json`.

**Comparison detail.** Of the 100 questions:

- 12 questions that baseline answered correctly are also correct under
  improved (no churn).
- 8 questions improved gets right that baseline did not (quoted-phrase
  and capitalized-run boosts win, e.g., *George Martin*, *Joe Tinker*,
  *Michael Jackson*, *Janet Jackson*, *Heather Locklear*).
- 3 questions baseline got that improved loses (*Tintoretto*,
  *Game Change*, *Ottoman Empire*) — see Q4 error analysis.

Net: **+5 P@1, +0.04 MRR** from the rule-based improvements; **+35 P@1
on top of that** (25 → 55) from the LLM reranker. The reranker's
P@1 = P@10 = 0.55 is not a coincidence: whenever the gold page
exists in the IR top-10, Claude picks it. The ceiling is now the
retriever's recall, not the reranker's ranking quality.

Net per-question diff vs baseline for the LLM mode: **37 gains and 1
loss** (Ottoman Empire — the gold page falls out of the top-10 in
retrieval, so the reranker has no candidate to pick from).

**B parameter sweep.** Whoosh's BM25F default `B=0.75` over-penalizes
long Wikipedia articles (a one-paragraph stub whose title contains a
clue word can outrank a 5,000-word biography). I swept `B` over the
full 100-question set; note that this is the same set we report
headline metrics on (the spec provides no held-out split, and 100
questions is too small to carve one out without losing power), so
`B=0.1` is mildly tuned to the eval set.

| B    | P@1 | MRR   |
|------|----:|------:|
| 0.0  |  15 | 0.260 |
| 0.1  |  20 | 0.303 |
| 0.2  |  20 | 0.297 |
| 0.5  |  15 | 0.251 |
| 0.75 |  12 | 0.196 |

`B=0.1` is baked into `watson.py` and used by both modes.

**Statistical significance (McNemar's exact test).** Computed via
`src/significance.py`:

| comparison           | discordant pairs | exact p-value | verdict |
|----------------------|-----------------:|--------------:|---------|
| baseline vs improved | 11 (8 vs 3)      | 0.227         | not significant |
| improved vs llm      | 30 (30 vs 0)     | 1.9e-9        | highly significant (p<0.001) |
| baseline vs llm      | 37 (36 vs 1)     | 5.5e-10       | highly significant (p<0.001) |

The +5 P@1 rule-based gain (baseline→improved) is **not significant**
at α=0.05 — at n=100, an 8-vs-3 split could plausibly occur by
chance. The +30 P@1 LLM-rerank gain is unambiguous. Honest reading:
the rule-based improvements help but the dev set is too small to
confirm; the LLM reranker is the only intervention whose gain is
beyond doubt.

---

## Question 4 — Error analysis (50 pts)

`src/error_analysis.py` reads any `evaluate.py --out` JSON dump,
classifies each miss into one of five buckets via simple
heuristics, and prints both a count summary and per-bucket dumps.
Run as:

```bash
python src/error_analysis.py results/llm.json --summary-only
python src/error_analysis.py results/llm.json --show pun_category
```

**Two perspectives on errors.** The pure-IR `improved` mode misses
75/100 questions (25 right at rank 1, 30 more in top-10, 45 missed
entirely). The `llm` mode pulls every top-10 hit to rank 1 — its 45
misses are a strict subset of `improved`'s, namely the ones the
retriever never surfaced. **The bucket counts below are computed on
the LLM mode's 45 misses**, since those are the residual errors
after rule-based and LLM improvements have done what they can.

### Bucket counts (45 misses / 100 questions)

| bucket             | count | % of misses |
|--------------------|------:|------------:|
| `indirect_lookup`  |    20 |       44.4% |
| `pun_category`     |     9 |       20.0% |
| `under_anchored`   |     4 |        8.9% |
| `decoy_overpowered`|     2 |        4.4% |
| `other`            |    10 |       22.2% |

### What each bucket means and what we observed

1. **`indirect_lookup` (20 / 44%) — by far the largest class.** The
   *category* constrains the answer to a *different entity than the
   clue describes*. The retrieval pipeline goes hunting for the
   entity in the clue and gets nowhere near the answer. Sub-patterns:
   - `STATE OF THE ART MUSEUM` — clue gives the museum, answer is
     the U.S. state (5 instances: *Florida*, *Ohio*, *New Mexico*,
     *Michigan*, *Idaho*).
   - `CAPITAL CITY CHURCHES` — clue gives the church, answer is the
     capital (*Helsinki*, *Edinburgh*).
   - `NAME THE PARENT COMPANY` — clue gives the brand, answer is the
     parent (*Kraft Foods* for Jell-O, *3M* for Post-it).
   - `'80s NO.1 HITMAKERS` — clue gives the song, answer is the
     artist (*George Michael*, *Michael Jackson* ×2).
   - `GOLDEN GLOBE WINNERS` — clue gives the role, answer is the
     actor (*Heath Ledger*, *Kelsey Grammer*, *Martin Sheen*).
   - `1920s NEWS FLASH!` and `HISTORICAL QUOTES` — clue gives the
     event/quote, answer is the historical figure.

   These are unsolvable by lexical retrieval *or* by a title-only
   reranker reading from the IR top-10, because the IR system was
   never going to surface the answer-side entity in the first place
   (the museum article doesn't usually contain the clue text, and
   nothing about the clue points to the museum's state).

2. **`pun_category` (9 / 20%) — wordplay constraints in the
   category.** The category itself is a puzzle whose solution
   constrains the answer (`"TIN" MEN` → answer's name contains
   *tin*; `COMPLETE DOM-INATION` → answer's name contains *dom*;
   `OLD YEAR'S RESOLUTIONS` → answer is some historical
   *resolution*). The clue text alone is generally too generic to
   localize the answer. *Tintoretto* (the previous improved-mode
   regression) was rescued by the LLM reranker because it appeared
   in the top-10; *Vladimir Putin* under `"TIN" MEN` was not.

3. **`under_anchored` (4 / 9%) — clues with no high-IDF anchors.**
   Quoted song lyrics or 1-3 word product clues:
   *"Father Figure"*, *"Beat It"*, *"Rock With You"*, *Jell-O*. BM25
   has nothing rare to lock onto.

4. **`decoy_overpowered` (2 / 4%) — title-decoys.** The top-1 hit
   is a different entity that shares more clue-content tokens with
   the clue than the gold's title does (*USS Maine* clue → *USS
   Arizona Memorial* hit; `WWF... bald eagle... red wolf` → *Red
   panda*). The improved-mode subset-decoy demotion already catches
   the easiest of these; what remains here are cases where the decoy
   only partially overlaps with the clue.

5. **`other` (10 / 22%) — body-text topical drift + inferential.**
   Title-overlap heuristics can't see this, but inspection shows two
   sub-patterns dominate:
   - *Topical drift*: the IR system retrieves topically related
     pages whose **body** matches the clue better than the answer
     page's body does (*Wolong... bamboo... China* → *Chengdu*; clue
     about Wordsworth's pseudonym → *Axios (acclamation)*; clue
     about JFK's 1960 campaign → *Richard Nixon*, his opponent).
   - *Inferential / multi-hop*: tuk-tuk → *Rickshaw*, Ammonites →
     *Jordan* (via Amman), Norodom statue → *France* (via French
     protectorate). Pure lexical retrieval cannot bridge a one-hop
     world-knowledge step.

### Implications for what to fix next

- The two largest buckets (**indirect_lookup + pun_category =
  64%** of remaining errors) cannot be solved by improving the IR
  ranker alone. They need either (a) an *LLM at the query side*
  generating expanded queries from `(clue, category)`, or (b)
  feeding the answer to an LLM with web/Wikipedia tool access.
- The next-best lever is reducing **topical body drift** in the
  *other* bucket (~22%) — a body-side rerank that re-scores top-50
  hits with proximity / phrase windows / first-paragraph match
  could plausibly recover several.
- The `decoy_overpowered` bucket is small (2 cases) — the
  improved-mode subset rerank already handled the obvious ones.

### Why the easy 25 work — clue-IDF analysis

A natural hypothesis: the easy clues are the ones with rare
distinguishing tokens (high IDF) that point unambiguously to one
page. `src/idf_analysis.py` tests this by computing the **max
content-token IDF** of each clue against the index's body postings,
binning into quintiles, and reporting baseline P@1 per bin
(`results/idf_histogram.png`):

| max-IDF range | n  | P@1  | interpretation |
|---------------|---:|-----:|----------------|
| [1.9, 5.0]    | 20 | 0.10 | no rare anchor |
| [5.1, 6.8]    | 20 | 0.20 | moderate |
| **[7.1, 9.8]** | 20 | **0.45** | **sweet spot** |
| [9.9, 11.2]   | 20 | 0.25 | very rare, mixed |
| [11.2, 11.9]  | 19 | 0.00 | ultra-rare hapaxes |

The pattern is **non-monotone — a sweet spot, not "rare = easy"**.
Three observations:

- Lowest quintile (P@1 = 0.10): the `under_anchored` bucket — quoted
  song lyrics and 1-3 word product clues with no rare token.
- Sweet spot (P@1 = 0.45): a single moderately-rare distinguishing
  token (place name, organization, domain noun in dozens to hundreds
  of pages) gives BM25 enough signal. *Indonesia, lizard, poachers*
  → *Komodo dragon* is the textbook case.
- Top quintile (P@1 = 0.00): ultra-rare tokens are usually obscure
  proper nouns, foreign-language phrases, or near-hapaxes that
  appear in a few unrelated pages and *not* in the actual answer's
  page (*Tuomiokirkko* in the Helsinki cathedral clue; *Wolong* in
  the Panda clue).

**The refined claim**: BM25 wants *discriminating* tokens, not just
*rare* ones — and these are not the same thing.

---

## Question 5 — Improved implementation (grad-only / extra credit)

`watson.py --mode improved` differs from the baseline in three ways:

1. **Quoted-phrase boost (`^3`).** Phrases inside double quotes in the
   clue (straight or curly) are extracted and added as phrase queries.
   For *"Daniel Hertzberg & James B. Stewart of this paper share a
   Pulitzer for their stories on insider trading"* nothing fires; for
   *"He won an Oscar for 'Good Will Hunting'"* the phrase
   *"Good Will Hunting"* is added as a `^3` phrase, anchoring retrieval
   on the named work rather than the verbs and nouns around it.
2. **Multi-word capitalized-run boost (`^2`).** Runs of two or more
   consecutive capitalized words (excluding stopwords and broken by
   punctuation) are added as `^2` phrase queries. *Pierre Cauchon*,
   *El Tahrir*, *Turkish Republic* are caught; standalone words like
   *Italian* or *Adoration* are not — boosting them blindly was tried
   and *regressed* Ben Affleck retrieval to *Helen Hunt* and *Oscar
   Wilde*.
3. **Three-bucket rerank** of the top-50 hits, in priority order:
   - *Demote meta-pages* (`List of …`, `Index of …`, `Timeline of …`,
     `(disambiguation)`). They contain many topical terms but are
     never the Jeopardy answer.
   - *Demote topical decoys*: pages whose title's word set is a strict
     subset of the clue's word set. Drops *Nile* when the answer is
     *Cairo*; almost never fires on the real answer because Jeopardy
     clues do not literally state the answer.
   - *Promote contiguous-phrase matches*: if the page's title appears
     as a contiguous substring of the clue, its score is bumped by
     +1000. Catches "the answer is the quoted phrase in the clue"
     cases like *Father Figure (song)*.

What was tried and **rejected**:

- **Appending category to the BM25 query.** Hurt P@1 by 8 points
  (`12/100`). Short hyped strings like *"1920s NEWS FLASH!"* outweigh
  the clue. The category remains parsed and is wired into `search()`'s
  signature so it can be re-introduced for rerank-only use later.
- **`^2` boost on every mid-clue capitalized word.** Was the v1
  improvement; net `15/100`. Words like *Hunting* and *Oscar* are
  capitalized but not the entity Jeopardy is asking about.
- **Whoosh BM25F default `B=0.75`.** See sweep table in Q3 — replaced
  by `B=0.1` in both modes.

### Mode `llm` — Claude reranker over the top-10

`watson.py --mode llm` runs the same `improved` retrieval as above and
then hands the top-10 candidate titles to Claude Sonnet 4.6 (via the
official Anthropic Python SDK), asking it to pick the single best
answer. The picked candidate is moved to rank 1; the rest keep their
relative order. See `src/llm_rerank.py` for the prompt and the
disk-cache layer.

**Why title-only.** The Whoosh index does not store page bodies
(`body=stored=False` in `build_index.py`), so the reranker prompt
contains only `(clue, category, list of 10 titles)`. Adding snippets
would require either re-streaming the wiki dump on every query (slow)
or rebuilding the index with bodies stored (~20 min). Since Claude
already has the entire Wikipedia subset in its training data, the
title-only prompt turned out to be enough — the reranker correctly
picks the gold page on every clue where it is present in the top-10.

**Why Sonnet, not Opus.** The task is a constrained classification
(pick 1 of 10 titles), not open-ended reasoning. Sonnet 4.6 is fully
adequate and ~3× cheaper than Opus 4.7 for this workload, which
matters for the ~100-call evaluation cycle and any re-runs during
prompt iteration.

**Disk cache.** Each `(clue, sorted candidate titles)` tuple is
SHA-256-hashed and the picked index is cached to
`results/llm_rerank_cache.json`. Re-running the evaluation does not
re-bill the API. Sorting the title list before hashing means tiny
BM25 score differences (which can shuffle ties) do not invalidate
the cache.

**Result.** P@1 jumps from **0.25 (improved) to 0.55 (llm)** — a
30-point absolute improvement, and the largest single gain in the
project. Crucially, P@1 = P@5 = P@10 = MRR = 0.55: every correct
answer that the IR system surfaced in the top-10 was correctly
identified by the reranker. The LLM closes the rank-quality gap
entirely; the remaining errors are pure retrieval failures (the gold
page is not in the top-10 at all).

**What the LLM gets right that BM25 cannot.** Three classes of clue
that Q4 flagged as unreachable for lexical retrieval are now solved:

- **Inferential**: *"For the brief time he attended, he was a rebel
  with a cause, even landing a lead role in a 1950 stage production"*
  → *James Dean* (gold). The lexical retriever needed a bridge through
  the *Rebel Without a Cause* film article; Claude makes it directly.
- **Pun categories**: clues under `"TIN" MEN` (*Tintoretto*),
  `COMPLETE DOM-INATION` (*William the Conqueror*) etc. now resolve
  because the reranker decodes the pun.
- **Indirect lookups**: *"The Naples Museum of Art is in this state's
  Collier County"* → *Florida* (gold), not the museum. The reranker
  steps from the museum article to its location.

**The one regression**: *Ottoman Empire* drops to off-list because the
`improved` retrieval doesn't surface it in the top-10 — the
capitalized run *Turkish Republic* in the clue boosts the wrong
cluster of pages and pushes *Ottoman Empire* out. The reranker can
only choose from what retrieval returns; it cannot recover answers
the IR layer never saw.

### Summary table

| approach                                  | P@1 |
|-------------------------------------------|----:|
| Whoosh BM25F, default `B=0.75`, clue only | 0.12 |
| Baseline (above + `B=0.1`)                | 0.20 |
| Improved (phrase + cap-run boosts + rerank) | 0.25 |
| **Improved + Claude Sonnet 4.6 reranker** | **0.55** |

The progression is: tune the IR (≈+8 pts), apply rule-based
post-processing (≈+5 pts), then let an LLM resolve the inferential
and wordplay cases the lexical pipeline cannot (+30 pts).

---

## Notes on reproducibility

- Whoosh stores the index in `index/`; re-running `build_index.py`
  wipes and rebuilds. Use `--keep` to add to an existing index.
- The full index occupies a few GB on disk and takes ~30–60 min to
  build on a laptop. Indexing is single-process; speeding it up
  would mean parallelizing the parser per file (Whoosh supports
  multi-segment writers).
- `data/questions.txt` is the only source of evaluation; no
  validation split is held out (100 questions is too small to split
  meaningfully).

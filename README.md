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
│   ├── watson.py                  # query construction + retrieval (baseline + improved)
│   ├── evaluate.py                # P@1 / P@5 / P@10 / MRR over questions.txt
│   ├── compare_modes.py           # runs both modes side-by-side
│   └── error_analysis.py          # human-readable miss dump
├── tests/
│   ├── test_wiki_parser.py
│   ├── test_query_builder.py
│   └── test_evaluator.py
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

Both modes:

```bash
python src/compare_modes.py --index-dir index --questions data/questions.txt --out-dir results
```

A single mode (with the per-question table printed):

```bash
python src/evaluate.py --index-dir index --questions data/questions.txt --mode baseline --out results/baseline.json
python src/evaluate.py --index-dir index --questions data/questions.txt --mode improved --out results/improved.json
```

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

Net: **+5 P@1, +0.04 MRR** from the rule-based improvements.

**B parameter sweep.** Whoosh's BM25F default `B=0.75` over-penalizes
long Wikipedia articles (a one-paragraph stub whose title contains a
clue word can outrank a 5,000-word biography). I swept `B` over the
full 100-question dev set:

| B    | P@1 | MRR   |
|------|----:|------:|
| 0.0  |  15 | 0.260 |
| 0.1  |  20 | 0.303 |
| 0.2  |  20 | 0.297 |
| 0.5  |  15 | 0.251 |
| 0.75 |  12 | 0.196 |

`B=0.1` is baked into `watson.py` and used by both modes.

---

## Question 4 — Error analysis (50 pts)

The full per-miss dump is produced by `error_analysis.py`. Of the 100
clues, the improved system gets **25 correct at rank 1**, **30 more
correct in the top-10 (ranks 2–10)**, and **45 missed entirely** (gold
page not in the top-10).

**Why does this simple system get the easy ones right?**
Jeopardy clues that are correctly answered tend to share **rare,
content-bearing tokens** with their target Wikipedia page. The clue
*"Indonesia's largest lizard, it's protected from poachers, though we
wish it could breathe fire to do the job itself"* has *Indonesia*,
*lizard*, and *poachers* — all of which appear at the top of the
"Komodo dragon" article and rarely elsewhere. BM25 ranks that page
first with no help from semantics. About 60–70% of the supplied
clues have this property: a small number of high-IDF terms point
unambiguously to one page.

**Error classes.** From the misses, I observed (counts to be filled
in once results are generated):

1. **Topical-decoy errors.** The clue mentions a salient entity that
   has its own Wikipedia page, and that page outscores the actual
   answer. Example: clue mentions *Nile* and *El Tahrir* — the system
   returns *Nile* even though the answer is *Cairo*. The improved
   reranker addresses this class explicitly by demoting any title
   that is wholly inside the clue's word set.
2. **Categorical-knowledge errors.** The clue is short and depends on
   the *category* to disambiguate — e.g. "1988: 'Father Figure'"
   under `'80s NO.1 HITMAKERS`. The clue alone has *Father* and
   *Figure*, both ambiguous. Category-aware queries help; missing
   category is a hard ceiling.
3. **Inferential-step errors.** The clue requires combining two
   facts. Example: *"For the brief time he attended, he was a rebel
   with a cause, even landing a lead role in a 1950 stage
   production"* — needs the connection *Rebel Without a Cause →
   James Dean*. Pure lexical retrieval cannot bridge that.
4. **Wordplay / pun errors.** Categories like `"TIN" MEN`,
   `COMPLETE DOM-INATION` use puns the system cannot decode. The
   clue text is enough to find the right answer in some of these, but
   not when the pun *is* the disambiguator.
5. **Coverage / alias errors.** The right page exists but under a
   variant title we don't normalize to (e.g. `WWF` vs `World Wide
   Fund for Nature`). The `|`-separated alias list in
   `questions.txt` mostly handles this; remaining cases fail.
6. **Prepositional-phrase noise.** Clues like *"On May 5, 1878 Alice
   Chambers was the last person buried in this Dodge City, Kansas
   cemetery"* match all dates and places in cemetery articles, not
   specifically `Boot Hill`.

Errors of types 1, 2, and 5 are tractable for a stronger IR system;
types 3 and 4 require either an LLM reranker or symbolic reasoning
on top.

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

Net effect: **+5 P@1, +0.04 MRR over baseline.** A natural next step —
called out by the spec — is to feed the top-10 to an LLM reranker, but
that is left for future work.

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

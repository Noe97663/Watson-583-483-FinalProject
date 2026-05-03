"""Query the wiki index with Jeopardy clues.

Two retrieval modes are exposed:

- ``baseline`` — use the clue text alone, parsed by Whoosh's
  ``MultifieldParser`` against ``title`` (×2 schema boost) and ``body``
  with ``OrGroup`` semantics, ranked by BM25F. The B parameter (length
  normalization) is set to 0.1 instead of the 0.75 default — empirically
  this is much better for Wikipedia, whose article lengths span four
  orders of magnitude. With B=0.75 a tiny one-paragraph article called
  *Calf* outranks the 5,000-word *Tintoretto* article on a clue about
  *the Adoration of the Golden Calf*; with B=0.1 the right answer wins.

- ``improved`` — same retriever, plus three refinements:
    1. Quoted phrases inside the clue (e.g. *"Adoration of the Golden
       Calf"*, *"Good Will Hunting"*) are extracted and added as
       phrase queries with ``^3`` boost. These are almost always the
       disambiguating named entities Jeopardy hinges on.
    2. Multi-word capitalized runs (e.g. *Pierre Cauchon*, *El
       Tahrir*) are added as ``^2`` phrase queries — single
       capitalized words are NOT boosted indiscriminately because
       generic mid-clue words like *Hunting* or *Oscar* then pull
       retrieval toward off-topic pages (early experiments regressed
       on *Ben Affleck* / *Helen Hunt* exactly this way).
    3. The Jeopardy category is intentionally NOT appended to the
       query — short hyped category strings like *1920s NEWS FLASH!*
       drown out the actual clue signal in BM25. It is used only as
       a soft tie-break in rerank.
    4. The top-K hits are re-ranked with three soft-demotion rules:
       drop *List of …* and *(disambiguation)* meta-pages to the
       bottom; drop pages whose title is wholly contained in the
       clue's word set (topical decoys); promote pages whose title
       words appear as a contiguous phrase in the clue.

Both modes return a list of ``Hit(rank, score, title)`` records.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List, Sequence, Tuple

from whoosh import index, scoring
from whoosh.qparser import MultifieldParser, OrGroup
from whoosh.query import Term

# Light stopword set used only for query construction (the index already
# strips Whoosh's default English stopwords; this list is for category +
# noun extraction).
_QUERY_STOP = {
    "a", "an", "and", "the", "of", "in", "on", "at", "to", "for",
    "with", "by", "from", "this", "that", "these", "those", "is",
    "are", "was", "were", "be", "been", "being", "as", "or", "but",
    "it", "its", "you", "your", "we", "our", "they", "them", "he",
    "she", "his", "her", "their", "i", "my", "me",
}

# Tokens that Whoosh's QueryParser treats as syntax. We strip them so
# clues like "we'll" or "Mr. Smith" don't break the parser.
_QUERY_BAD = re.compile(r"[\(\)\[\]\{\}\"\\:^~*?+\-/<>=!&|@#$%]")
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9'’]*")


def open_index(index_dir: str):
    return index.open_dir(index_dir)


def _sanitize(text: str) -> str:
    """Strip query-syntax characters and squeeze whitespace."""
    return _QUERY_BAD.sub(" ", text).strip()


_QUOTED_RE = re.compile(r'"([^"]{2,})"|“([^”]{2,})”')


def _quoted_phrases(clue: str) -> List[str]:
    """Extract phrases inside straight or curly double quotes."""
    out: List[str] = []
    for m in _QUOTED_RE.finditer(clue):
        ph = m.group(1) or m.group(2)
        if ph:
            out.append(ph.strip())
    return out


def _capitalized_runs(clue: str) -> List[str]:
    """Multi-word capitalized runs likely to be named entities.

    Ignores the very first word of the clue (capitalized by sentence
    position, not by being a proper noun) and skips any run of length 1.
    """
    runs: List[str] = []
    # Split on punctuation that typically separates named entities so a
    # comma or dash breaks a run (e.g., "Pierre Cauchon, Bishop of …" →
    # we want "Pierre Cauchon", not "Pierre Cauchon Bishop").
    for chunk in re.split(r"[,;:!?\.\-—–]+", clue):
        cur: List[str] = []
        for w in _WORD_RE.findall(chunk):
            is_cap = (
                w[0].isupper()
                and w.lower() not in _QUERY_STOP
                and len(w) > 1
            )
            if is_cap:
                cur.append(w)
            else:
                if len(cur) >= 2:
                    runs.append(" ".join(cur))
                cur = []
        if len(cur) >= 2:
            runs.append(" ".join(cur))
    return runs


def _build_query_string(clue: str, category: str | None, *, expand: bool) -> str:
    """Compose the raw query string passed to MultifieldParser.

    ``expand=True`` adds quoted-phrase and capitalized-run boosts on top
    of the base clue text. ``category`` is currently unused at query
    time (see module docstring); it is accepted to keep the signature
    stable for future experiments.
    """
    parts: List[str] = [_sanitize(clue)]
    if expand:
        for ph in _quoted_phrases(clue):
            ph_s = _sanitize(ph)
            if ph_s and len(ph_s.split()) >= 2:
                parts.append(f'"{ph_s}"^3')
        for run in _capitalized_runs(clue):
            run_s = _sanitize(run)
            if run_s and len(run_s.split()) >= 2:
                parts.append(f'"{run_s}"^2')
    return " ".join(p for p in parts if p)


@dataclass
class Hit:
    rank: int
    score: float
    title: str


# BM25 length-normalization parameter. The Whoosh default of 0.75 is too
# aggressive for Wikipedia, whose article lengths span four orders of
# magnitude. Picked by sweep over the 100-question dev set.
_BM25_B = 0.1


def search(
    ix,
    clue: str,
    category: str | None = None,
    *,
    top_k: int = 10,
    mode: str = "baseline",
) -> List[Hit]:
    """Run retrieval and return the top-K hits as a list of ``Hit``s.

    ``mode`` is one of ``"baseline"``, ``"improved"``, or ``"llm"``.
    The ``"llm"`` mode runs the same retrieval as ``"improved"`` and
    then asks Claude to reorder the top-K (see ``llm_rerank.py``).
    """
    if mode not in ("baseline", "improved", "llm"):
        raise ValueError(f"unknown mode: {mode}")

    expand = mode in ("improved", "llm")
    rerank = mode in ("improved", "llm")

    qstr = _build_query_string(clue, category, expand=expand)

    parser = MultifieldParser(["title", "body"], schema=ix.schema, group=OrGroup)
    query = parser.parse(qstr)

    weighting = scoring.BM25F(B=_BM25_B)

    fetch_k = max(top_k * 5, 50) if rerank else top_k
    hits: List[Hit] = []
    with ix.searcher(weighting=weighting) as searcher:
        results = searcher.search(query, limit=fetch_k)
        for i, r in enumerate(results):
            hits.append(Hit(rank=i + 1, score=float(r.score), title=r["raw_title"]))

    if rerank:
        hits = _rerank(hits, clue)
        hits = hits[:top_k]
        for i, h in enumerate(hits):
            h.rank = i + 1

    if mode == "llm":
        # Lazy import so the baseline + improved code paths work
        # without anthropic installed.
        if __package__ in (None, ""):
            from llm_rerank import get_default_reranker  # type: ignore
        else:
            from .llm_rerank import get_default_reranker
        hits = get_default_reranker().rerank(clue, category or "", hits)

    return hits


_META_TITLE_RE = re.compile(
    r"(?i)^(list of |index of |outline of |timeline of )|\(disambiguation\)"
)


def _rerank(hits: Sequence[Hit], clue: str) -> List[Hit]:
    """Apply soft-demotion / promotion rules to the top-K hits.

    Three rules, in order of stringency:

    1. Demote *meta* titles ("List of X", "(disambiguation)", "Index of X",
       "Timeline of X"). They are almost never the answer to a Jeopardy clue
       and tend to score well because they contain many topical terms.

    2. Demote pages whose title's word set is a strict subset of the
       clue's word set ("topical decoys"). Example: for "Several bridges,
       including El Tahrir, cross the Nile in this capital" the page
       *Nile* outscores *Cairo* because *Nile* is in the clue; but
       Jeopardy answers are rarely literally stated.

    3. Promote pages whose multi-word title appears as a *contiguous
       phrase* in the clue. Example: clue contains the phrase
       "Father Figure" → the page *Father Figure (song)* gets boosted.
       This catches the cases where the answer literally is the quoted
       title in the clue.
    """
    clue_words_list = [w.lower() for w in _WORD_RE.findall(clue)]
    clue_words = set(clue_words_list)
    clue_lower = clue.lower()

    keep: List[Hit] = []
    decoys: List[Hit] = []
    meta: List[Hit] = []

    for h in hits:
        title_words_list = [w.lower() for w in _WORD_RE.findall(h.title)]
        title_words = set(title_words_list)

        if _META_TITLE_RE.search(h.title):
            meta.append(h)
            continue

        if title_words and title_words.issubset(clue_words):
            decoys.append(h)
            continue

        # Phrase promotion: if the title's whole multi-word sequence (or
        # its first 2+ words) appears verbatim in the clue, score it
        # ahead of other keepers.
        if len(title_words_list) >= 2:
            phrase = " ".join(title_words_list[:3])
            if phrase in clue_lower:
                h.score += 1000.0  # large additive bump within the keep bucket

        keep.append(h)

    keep.sort(key=lambda h: -h.score)
    return keep + decoys + meta


def search_many(
    ix,
    questions: Iterable[Tuple[str, str, str]],
    *,
    top_k: int = 10,
    mode: str = "baseline",
) -> List[Tuple[Tuple[str, str, str], List[Hit]]]:
    """Convenience: run ``search`` over an iterable of (cat, clue, gold)."""
    out = []
    for q in questions:
        cat, clue, gold = q
        hits = search(ix, clue, cat, top_k=top_k, mode=mode)
        out.append((q, hits))
    return out

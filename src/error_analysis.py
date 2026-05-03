"""Dump misses with per-bucket counts for the report's error analysis.

Reads a JSON dump produced by ``evaluate.py --out`` (or
``compare_modes.py``) and groups every miss into one of five
heuristic buckets. The counts feed the report's Q4 section; the
per-bucket dumps are useful for sanity-checking the heuristics.

Buckets:

1. ``indirect_lookup`` — the category constrains the answer to a
   different entity than the clue describes. Examples: ``STATE OF
   THE ART MUSEUM`` (clue gives the museum, answer is the state),
   ``NAME THE PARENT COMPANY`` (clue gives the brand, answer is the
   parent), ``'80s NO.1 HITMAKERS`` (clue gives the song, answer is
   the artist).
2. ``pun_category`` — the category itself is a wordplay constraint
   on the answer (``"TIN" MEN``, ``COMPLETE DOM-INATION``).
3. ``under_anchored`` — the clue is short or mostly quoted text with
   no rare content terms; BM25 has no signal to lock onto.
4. ``decoy_overpowered`` — the clue mentions a salient named entity
   (with its own Wikipedia page) that outscores the actual answer.
5. ``other`` — fallthrough (typically inferential / multi-hop clues
   that require world-knowledge bridging).

The heuristics are intentionally simple and transparent. Run with
``--show <bucket>`` to dump only one bucket and verify the
classification visually.
"""
from __future__ import annotations

import argparse
import json
import re
from typing import Dict, List, Tuple

# Substrings that, when found in the category text (case-insensitive),
# mark the question as an indirect-lookup. Each tuple is (substring,
# label) where the label is just for documentation when --verbose.
_INDIRECT_PATTERNS: List[Tuple[str, str]] = [
    ("state of the art museum", "museum→state"),
    ("capital city churches", "church→capital"),
    ("parent company", "brand→parent"),
    ("hitmakers", "song→artist"),
    ("golden globe winners", "role→actor"),
    ("historical quotes", "quote→speaker"),
    ("news flash", "event→figure"),
    ("ucla celebrity alumni", "trait→alumnus"),
]

# Pun-category markers. These categories quote a target substring,
# break a word with hyphens, or otherwise encode a wordplay
# constraint that the clue text itself does not.
_PUN_PATTERNS: List[str] = [
    r'"[^"]+"\s+\w+',           # "TIN" MEN, "OLD" YEAR'S, etc.
    r"\b\w+-\w+",               # DOM-INATION, ABC-DEF
    r"old year",                # OLD YEAR'S RESOLUTIONS
]
_PUN_RE = re.compile("|".join(_PUN_PATTERNS), re.IGNORECASE)

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9'’]*")


def _is_indirect(category: str) -> bool:
    cat_low = category.lower()
    return any(pat in cat_low for pat, _ in _INDIRECT_PATTERNS)


def _is_pun(category: str) -> bool:
    return bool(_PUN_RE.search(category))


def _is_under_anchored(clue: str) -> bool:
    """Short clue OR clue dominated by a single quoted span.

    Quoted lyrics ("Father Figure", "Beat It", "you make me smile…")
    and bare 1-2 word clues ("Jell-O", "Post-it notes") fall here.
    The threshold of 60 chars / 8 content tokens was eyeballed
    against the 45-question miss set.
    """
    if len(clue) < 60:
        return True
    content = [w for w in _WORD_RE.findall(clue) if len(w) > 3]
    if len(content) < 8:
        return True
    quoted = re.findall(r'"([^"]+)"|“([^”]+)”', clue)
    if quoted:
        # If a single quoted span dominates the clue, treat as
        # under-anchored — BM25 sees mostly the lyric/title and
        # generic glue around it.
        longest = max(len(q[0] or q[1]) for q in quoted)
        if longest >= 0.4 * len(clue):
            return True
    return False


def _is_decoy_overpowered(record: dict) -> bool:
    """The top-1 hit lexically dominates the gold against this clue.

    Captures cases like *USS Maine* clue → top hit *USS Arizona
    Memorial* (gold *Arlington National Cemetery*): the IR system
    locked onto a different entity that shares more clue terms than
    the actual answer. The heuristic fires when the top-1 has at
    least one content-word overlap with the clue AND has *strictly
    more* content overlap than the gold's title — i.e. lexical
    similarity points the wrong way. Falling back on this rule covers
    cases where the gold legitimately has a clue word in its title
    but a competing page has many.
    """
    if not record["top_hits"]:
        return False
    clue_words = {w.lower() for w in _WORD_RE.findall(record["clue"]) if len(w) > 3}
    if not clue_words:
        return False
    top1 = record["top_hits"][0]["title"]
    top1_words = {w.lower() for w in _WORD_RE.findall(top1) if len(w) > 3}
    gold = record["aliases"][0]
    gold_words = {w.lower() for w in _WORD_RE.findall(gold) if len(w) > 3}

    top_overlap = len(top1_words & clue_words)
    gold_overlap = len(gold_words & clue_words)
    return top_overlap >= 1 and top_overlap > gold_overlap


def classify(record: dict) -> str:
    """Return the bucket name for a single miss record."""
    if _is_indirect(record["category"]):
        return "indirect_lookup"
    if _is_pun(record["category"]):
        return "pun_category"
    if _is_under_anchored(record["clue"]):
        return "under_anchored"
    if _is_decoy_overpowered(record):
        return "decoy_overpowered"
    return "other"


_BUCKET_ORDER = [
    "indirect_lookup",
    "pun_category",
    "under_anchored",
    "decoy_overpowered",
    "other",
]


def bucket_misses(results: List[dict]) -> Dict[str, List[dict]]:
    out: Dict[str, List[dict]] = {b: [] for b in _BUCKET_ORDER}
    for r in results:
        if r["rank"] == 1:
            continue
        out[classify(r)].append(r)
    return out


def _print_summary(buckets: Dict[str, List[dict]], total: int) -> None:
    n_misses = sum(len(v) for v in buckets.values())
    print(f"# Error buckets ({n_misses} misses / {total} questions)\n")
    print(f"  {'bucket':<22}  {'count':>5}  {'% of misses':>12}")
    for b in _BUCKET_ORDER:
        n = len(buckets[b])
        pct = (100.0 * n / n_misses) if n_misses else 0.0
        print(f"  {b:<22}  {n:>5}  {pct:>11.1f}%")
    print()


def _print_bucket(name: str, items: List[dict], top: int) -> None:
    if not items:
        return
    print(f"\n## {name} ({len(items)})\n")
    for i, r in enumerate(items, 1):
        gold = " | ".join(r["aliases"])
        print(f"[{i:>2}] CATEGORY : {r['category']}")
        print(f"     CLUE     : {r['clue'][:120]}")
        print(f"     GOLD     : {gold}")
        print(f"     GOLD@RANK: {r['rank'] if r['rank'] else 'not in top-K'}")
        print(f"     TOP-{top}    :")
        for h in r["top_hits"][:top]:
            print(f"        {h['rank']:>2}. {h['score']:>7.3f}  {h['title']}")
        print()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("results_json")
    p.add_argument("--top", type=int, default=5,
                   help="how many top hits to show per miss")
    p.add_argument("--show", choices=_BUCKET_ORDER + ["all"], default="all",
                   help="dump per-question detail for one bucket "
                        "(or 'all') in addition to the summary")
    p.add_argument("--summary-only", action="store_true",
                   help="print only the bucket counts table")
    args = p.parse_args()

    print(f"[step 1] loading results from {args.results_json} ...", flush=True)
    with open(args.results_json, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    print(f"         {len(data['results'])} questions ("
          f"mode={data.get('mode', '?')}).", flush=True)

    print(f"[step 2] classifying misses into buckets ...", flush=True)
    buckets = bucket_misses(data["results"])

    print()
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    _print_summary(buckets, total=len(data["results"]))

    if args.summary_only:
        return

    print(f"[step 3] dumping per-question detail "
          f"({'all buckets' if args.show == 'all' else args.show}) ...",
          flush=True)
    if args.show == "all":
        for b in _BUCKET_ORDER:
            _print_bucket(b, buckets[b], args.top)
    else:
        _print_bucket(args.show, buckets[args.show], args.top)


if __name__ == "__main__":
    main()

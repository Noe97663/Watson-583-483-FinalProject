"""Run retrieval over ``data/questions.txt`` and report P@1 + MRR.

``questions.txt`` has 4-line records: CATEGORY / CLUE / ANSWER / blank.
The ANSWER may contain ``|``-separated aliases, e.g.::

    Slavery|Slavery in the United States

A retrieval is counted correct if the retrieved title (case- and
punctuation-normalized) matches *any* alias.

Run as a script::

    python -m src.evaluate --index-dir ../index --questions ../data/questions.txt
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from typing import Iterable, Iterator, List, Tuple

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from watson import Hit, open_index, search  # type: ignore
else:
    from .watson import Hit, open_index, search


@dataclass
class Question:
    category: str
    clue: str
    aliases: Tuple[str, ...]   # gold answer + aliases

    @property
    def gold(self) -> str:
        return self.aliases[0]


def read_questions(path: str) -> List[Question]:
    """Parse the 4-line-per-question format."""
    out: List[Question] = []
    with open(path, "r", encoding="utf-8") as fh:
        block: List[str] = []
        for line in fh:
            line = line.rstrip("\n")
            if line.strip() == "":
                if len(block) == 3:
                    out.append(_make_q(block))
                block = []
            else:
                block.append(line)
        if len(block) == 3:
            out.append(_make_q(block))
    return out


def _make_q(block: List[str]) -> Question:
    cat, clue, ans = block
    aliases = tuple(a.strip() for a in ans.split("|") if a.strip())
    return Question(category=cat.strip(), clue=clue.strip(), aliases=aliases)


# Normalize titles for comparison: lowercase, drop leading "The ",
# collapse non-alphanumerics to single spaces.
_NORM_RE = re.compile(r"[^a-z0-9]+")


def normalize_title(s: str) -> str:
    s = s.strip().lower()
    if s.startswith("the "):
        s = s[4:]
    s = _NORM_RE.sub(" ", s).strip()
    return s


def is_match(retrieved: str, aliases: Iterable[str]) -> bool:
    rn = normalize_title(retrieved)
    if not rn:
        return False
    return any(rn == normalize_title(a) for a in aliases)


@dataclass
class QResult:
    question: Question
    hits: List[Hit]
    rank: int  # 1-based rank of the gold; 0 if not in top-K

    @property
    def correct(self) -> bool:
        return self.rank == 1

    @property
    def reciprocal_rank(self) -> float:
        return 1.0 / self.rank if self.rank > 0 else 0.0


def evaluate(
    ix,
    questions: List[Question],
    *,
    top_k: int = 10,
    mode: str = "baseline",
    progress: bool = False,
) -> List[QResult]:
    """Run retrieval + scoring over ``questions``.

    With ``progress=True``, prints one line per question summarising
    the picked top-1 and whether it matched the gold. Off by default
    so unit tests and library callers stay quiet.
    """
    out: List[QResult] = []
    for i, q in enumerate(questions, 1):
        hits = search(ix, q.clue, q.category, top_k=top_k, mode=mode)
        rank = 0
        for h in hits:
            if is_match(h.title, q.aliases):
                rank = h.rank
                break
        out.append(QResult(question=q, hits=hits, rank=rank))
        if progress:
            top1 = hits[0].title if hits else "<no hits>"
            mark = "OK " if rank == 1 else (f"r={rank}" if rank else "miss")
            gold = q.gold[:30]
            print(
                f"  [{i:>3}/{len(questions)}] {mode:<8} {mark:>5}  "
                f"gold={gold:<30}  top1={top1[:40]}",
                flush=True,
            )
    return out


def summary(results: List[QResult]) -> dict:
    n = len(results)
    p1 = sum(1 for r in results if r.correct) / n if n else 0.0
    p5 = sum(1 for r in results if 0 < r.rank <= 5) / n if n else 0.0
    p10 = sum(1 for r in results if 0 < r.rank <= 10) / n if n else 0.0
    mrr = sum(r.reciprocal_rank for r in results) / n if n else 0.0
    return {"n": n, "p_at_1": p1, "p_at_5": p5, "p_at_10": p10, "mrr": mrr}


def _format_table(results: List[QResult]) -> Iterator[str]:
    yield f"{'#':>3} {'rank':>4}  {'gold':<35}  retrieved"
    for i, r in enumerate(results, 1):
        gold = r.question.gold[:33]
        rk = r.rank if r.rank else "-"
        ret = r.hits[0].title if r.hits else ""
        ret = ret[:50]
        yield f"{i:>3} {str(rk):>4}  {gold:<35}  {ret}"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--index-dir", default="index")
    p.add_argument("--questions", default="data/questions.txt")
    p.add_argument("--mode", choices=["baseline", "improved", "llm"], default="baseline")
    p.add_argument("--top-k", type=int, default=10)
    p.add_argument("--out", default=None,
                   help="optional JSON file to dump per-question results")
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args()

    print(f"[step 1] reading questions from {args.questions} ...", flush=True)
    qs = read_questions(args.questions)
    print(f"         loaded {len(qs)} questions.", flush=True)

    print(f"[step 2] opening Whoosh index at {args.index_dir} ...", flush=True)
    ix = open_index(args.index_dir)
    print(f"         index has {ix.doc_count()} documents.", flush=True)

    print(f"[step 3] running retrieval (mode={args.mode}, top-k={args.top_k}) ...",
          flush=True)
    if args.mode == "llm" and not args.quiet:
        # Lazy import: don't pull in anthropic for non-LLM modes.
        if __package__ in (None, ""):
            from llm_rerank import set_default_verbose  # type: ignore
        else:
            from .llm_rerank import set_default_verbose
        set_default_verbose(True)
    results = evaluate(ix, qs, top_k=args.top_k, mode=args.mode, progress=not args.quiet)
    s = summary(results)

    if not args.quiet:
        print()
        print("Per-question table:")
        for line in _format_table(results):
            print(line)
    print()
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"mode      : {args.mode}")
    print(f"questions : {s['n']}")
    print(f"P@1       : {s['p_at_1']:.3f}  ({sum(1 for r in results if r.correct)}/{s['n']})")
    print(f"P@5       : {s['p_at_5']:.3f}")
    print(f"P@10      : {s['p_at_10']:.3f}")
    print(f"MRR       : {s['mrr']:.3f}")

    if args.out:
        payload = {
            "mode": args.mode,
            "summary": s,
            "results": [
                {
                    "category": r.question.category,
                    "clue": r.question.clue,
                    "aliases": list(r.question.aliases),
                    "rank": r.rank,
                    "top_hits": [
                        {"rank": h.rank, "score": h.score, "title": h.title}
                        for h in r.hits
                    ],
                }
                for r in results
            ],
        }
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
        print(f"[step 4] wrote per-question JSON to {args.out}")


if __name__ == "__main__":
    main()

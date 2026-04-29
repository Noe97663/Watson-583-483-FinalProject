"""Run both retrieval modes and print a side-by-side comparison.

Convenience wrapper that calls ``evaluate.evaluate`` twice (baseline,
improved) against the same index and dumps a JSON file for each. Used
to populate the report's metrics + error-analysis sections.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from evaluate import evaluate, read_questions, summary  # type: ignore
    from watson import open_index
else:
    from .evaluate import evaluate, read_questions, summary
    from .watson import open_index


def _dump(path: str, mode: str, results) -> None:
    payload = {
        "mode": mode,
        "summary": summary(results),
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
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--index-dir", default="index")
    p.add_argument("--questions", default="data/questions.txt")
    p.add_argument("--top-k", type=int, default=10)
    p.add_argument("--out-dir", default="results")
    args = p.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    qs = read_questions(args.questions)
    ix = open_index(args.index_dir)

    rows = []
    for mode in ("baseline", "improved"):
        results = evaluate(ix, qs, top_k=args.top_k, mode=mode)
        s = summary(results)
        rows.append((mode, s, results))
        _dump(os.path.join(args.out_dir, f"{mode}.json"), mode, results)

    print(f"{'mode':<10}  {'P@1':>6}  {'P@5':>6}  {'P@10':>6}  {'MRR':>6}")
    for mode, s, _ in rows:
        print(
            f"{mode:<10}  {s['p_at_1']:>6.3f}  {s['p_at_5']:>6.3f}  "
            f"{s['p_at_10']:>6.3f}  {s['mrr']:>6.3f}"
        )

    # Per-question gain/regression list
    base = {(r.question.category, r.question.clue): r.rank for r in rows[0][2]}
    print("\nQuestions where mode changed correctness:")
    for r in rows[1][2]:
        k = (r.question.category, r.question.clue)
        b_rank = base[k]
        if (b_rank == 1) != (r.rank == 1):
            change = "+" if r.rank == 1 else "-"
            gold = r.question.gold[:40]
            print(f"  {change} (base={b_rank or '-'}, imp={r.rank or '-'})  {gold}")


if __name__ == "__main__":
    main()

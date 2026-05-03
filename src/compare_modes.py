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
    p.add_argument(
        "--modes",
        nargs="+",
        default=["baseline", "improved"],
        choices=["baseline", "improved", "llm"],
        help="Which modes to evaluate. Add 'llm' to also run the "
             "Claude reranker (requires ANTHROPIC_API_KEY).",
    )
    p.add_argument("--quiet", action="store_true",
                   help="suppress per-question progress lines")
    args = p.parse_args()

    print(f"[step 1] preparing output dir {args.out_dir} ...", flush=True)
    os.makedirs(args.out_dir, exist_ok=True)

    print(f"[step 2] reading questions from {args.questions} ...", flush=True)
    qs = read_questions(args.questions)
    print(f"         loaded {len(qs)} questions.", flush=True)

    print(f"[step 3] opening Whoosh index at {args.index_dir} ...", flush=True)
    ix = open_index(args.index_dir)
    print(f"         index has {ix.doc_count()} documents.", flush=True)

    print(f"[step 4] evaluating modes: {', '.join(args.modes)}", flush=True)
    if "llm" in args.modes and not args.quiet:
        # Lazy import: don't pull in anthropic if no LLM mode is requested.
        if __package__ in (None, ""):
            from llm_rerank import set_default_verbose  # type: ignore
        else:
            from .llm_rerank import set_default_verbose
        set_default_verbose(True)

    rows = []
    for mode_idx, mode in enumerate(args.modes, 1):
        print(f"\n  -- mode {mode_idx}/{len(args.modes)}: {mode} --", flush=True)
        results = evaluate(
            ix, qs, top_k=args.top_k, mode=mode, progress=not args.quiet,
        )
        s = summary(results)
        rows.append((mode, s, results))
        out_path = os.path.join(args.out_dir, f"{mode}.json")
        _dump(out_path, mode, results)
        print(f"  -- {mode}: P@1={s['p_at_1']:.3f}  MRR={s['mrr']:.3f}  "
              f"(wrote {out_path})", flush=True)

    print()
    print("=" * 60)
    print("Summary across all evaluated modes")
    print("=" * 60)
    print(f"{'mode':<10}  {'P@1':>6}  {'P@5':>6}  {'P@10':>6}  {'MRR':>6}")
    for mode, s, _ in rows:
        print(
            f"{mode:<10}  {s['p_at_1']:>6.3f}  {s['p_at_5']:>6.3f}  "
            f"{s['p_at_10']:>6.3f}  {s['mrr']:>6.3f}"
        )

    # Per-question gain/regression list — compare each non-first mode
    # against the first mode (treated as the baseline for diffing).
    if len(rows) >= 2:
        base_mode, _, base_results = rows[0]
        base = {(r.question.category, r.question.clue): r.rank for r in base_results}
        for mode, _, results in rows[1:]:
            print(f"\nQuestions where {mode} differs from {base_mode}:")
            for r in results:
                k = (r.question.category, r.question.clue)
                b_rank = base[k]
                if (b_rank == 1) != (r.rank == 1):
                    change = "+" if r.rank == 1 else "-"
                    gold = r.question.gold[:40]
                    print(f"  {change} ({base_mode}={b_rank or '-'}, "
                          f"{mode}={r.rank or '-'})  {gold}")


if __name__ == "__main__":
    main()

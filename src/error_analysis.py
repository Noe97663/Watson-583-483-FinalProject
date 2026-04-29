"""Dump every miss + its top-5 retrieved titles for manual error analysis.

Reads a JSON dump produced by ``evaluate.py --out`` and prints, for each
question whose rank != 1, the category, clue, gold answer, and the top-5
hits the system returned. Used to populate the error-analysis table in
the report.
"""
from __future__ import annotations

import argparse
import json


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("results_json")
    p.add_argument("--top", type=int, default=5)
    args = p.parse_args()

    with open(args.results_json, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    misses = [r for r in data["results"] if r["rank"] != 1]
    print(f"# Misses: {len(misses)} / {len(data['results'])}\n")
    for i, r in enumerate(misses, 1):
        gold = " | ".join(r["aliases"])
        print(f"[{i:>2}] CATEGORY: {r['category']}")
        print(f"     CLUE    : {r['clue']}")
        print(f"     GOLD    : {gold}")
        print(f"     GOLD@RANK: {r['rank'] if r['rank'] else 'not in top-K'}")
        print(f"     TOP-{args.top}:")
        for h in r["top_hits"][: args.top]:
            print(f"        {h['rank']:>2}. {h['score']:>7.3f}  {h['title']}")
        print()


if __name__ == "__main__":
    main()

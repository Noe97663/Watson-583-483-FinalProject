"""McNemar's exact test on pairwise mode comparisons.

For two evaluation modes A and B, McNemar's test asks "given the
questions where A and B disagree, is the split between (A right,
B wrong) and (A wrong, B right) significantly different from 50/50?"
This is the right test for paired binary outcomes — far stronger than
treating each mode's P@1 as an independent proportion.

Reads ``results/{baseline,improved,llm}.json`` and prints both the
contingency table and the exact-binomial McNemar p-value for each
adjacent pair.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
from typing import Dict, Tuple

from scipy.stats import binomtest


def mcnemar_exact_p(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value.

    Given the off-diagonal counts b (A-only-correct) and c (B-only-
    correct), McNemar's exact test is a two-sided binomial test on
    min(b, c) successes out of (b + c) trials with p = 0.5. Returns
    1.0 if there are no discordant pairs (the modes agree on every
    question).
    """
    n = b + c
    if n == 0:
        return 1.0
    return binomtest(min(b, c), n=n, p=0.5, alternative="two-sided").pvalue


def _correct_map(path: str) -> Dict[Tuple[str, str], bool]:
    """Map (category, clue) → (rank == 1)."""
    with io.open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return {
        (r["category"], r["clue"]): r["rank"] == 1
        for r in data["results"]
    }


def _contingency(a: Dict, b: Dict) -> list[list[int]]:
    """2x2 table — rows = mode A correct/wrong, cols = mode B correct/wrong."""
    both = neither = a_only = b_only = 0
    for k, a_correct in a.items():
        b_correct = b[k]
        if a_correct and b_correct:
            both += 1
        elif a_correct and not b_correct:
            a_only += 1
        elif b_correct and not a_correct:
            b_only += 1
        else:
            neither += 1
    return [[both, a_only], [b_only, neither]]


def _print_pair(name_a: str, name_b: str, path_a: str, path_b: str) -> None:
    a = _correct_map(path_a)
    b = _correct_map(path_b)
    table = _contingency(a, b)

    n_a = sum(a.values())
    n_b = sum(b.values())
    print(f"\n## {name_a} vs {name_b}")
    print(f"   {name_a}: {n_a}/{len(a)} correct;  "
          f"{name_b}: {n_b}/{len(b)} correct")
    print(f"   contingency:")
    print(f"                          {name_b} correct   {name_b} wrong")
    print(f"     {name_a:<10} correct  {table[0][0]:>10}    {table[0][1]:>10}")
    print(f"     {name_a:<10} wrong    {table[1][0]:>10}    {table[1][1]:>10}")

    discordant = table[0][1] + table[1][0]
    if discordant == 0:
        print("   discordant pairs = 0 — McNemar undefined (modes agree).")
        return

    a_only = table[0][1]   # A correct, B wrong
    b_only = table[1][0]   # A wrong, B correct
    p = mcnemar_exact_p(b=a_only, c=b_only)
    print(f"   discordant pairs = {discordant}  "
          f"(b_only={b_only}, a_only={a_only})")
    print(f"   McNemar exact p-value = {p:.4g}")
    if p < 0.001:
        verdict = "highly significant (p<0.001)"
    elif p < 0.05:
        verdict = "significant at p<0.05"
    elif p < 0.10:
        verdict = "borderline (p<0.10)"
    else:
        verdict = "not significant"
    print(f"   verdict: {verdict}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--results-dir", default="results")
    args = p.parse_args()

    baseline = os.path.join(args.results_dir, "baseline.json")
    improved = os.path.join(args.results_dir, "improved.json")
    llm = os.path.join(args.results_dir, "llm.json")

    print(f"[step 1] reading {baseline}, {improved}, {llm} ...", flush=True)
    for path in (baseline, improved, llm):
        if not os.path.exists(path):
            print(f"  missing: {path} — run compare_modes.py first", file=sys.stderr)
            sys.exit(1)

    print(f"[step 2] computing McNemar exact tests on paired correctness ...",
          flush=True)
    print()
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    _print_pair("baseline", "improved", baseline, improved)
    _print_pair("improved", "llm", improved, llm)
    _print_pair("baseline", "llm", baseline, llm)


if __name__ == "__main__":
    main()

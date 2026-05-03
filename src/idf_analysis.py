"""Mean clue-IDF vs correctness — supports the Q4 claim that the
'easy' clues are the ones whose content tokens are individually rare.

For each question, compute the mean IDF of its content tokens (using
the actual Whoosh index's posting lists), then bin by quartile of mean
IDF and report the per-bucket P@1 and a small bar plot. If matplotlib
is available the chart is saved to ``results/idf_histogram.png``;
otherwise an ASCII bar chart is printed.
"""
from __future__ import annotations

import argparse
import io
import json
import math
import os
import re
import sys
from typing import Dict, List, Tuple

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from watson import open_index  # type: ignore
else:
    from .watson import open_index


# Same word regex used in watson.py — keep token boundary consistent.
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9'’]*")

# A small stopword set; matches Whoosh's StemmingAnalyzer defaults
# closely enough for IDF purposes.
_STOP = {
    "a", "an", "and", "the", "of", "in", "on", "at", "to", "for",
    "with", "by", "from", "this", "that", "these", "those", "is",
    "are", "was", "were", "be", "been", "being", "as", "or", "but",
    "it", "its", "you", "your", "we", "our", "they", "them", "he",
    "she", "his", "her", "their", "i", "my", "me", "not", "no",
    "have", "has", "had", "do", "does", "did", "will", "would",
    "can", "could", "may", "might", "should", "if", "when", "what",
    "who", "where", "why", "how", "which", "than", "then", "so",
    "also", "just", "only",
}


def _content_tokens(text: str) -> List[str]:
    return [
        w.lower() for w in _WORD_RE.findall(text)
        if w.lower() not in _STOP and len(w) > 2
    ]


def _clue_idfs(ix, clue: str) -> List[float] | None:
    """All token IDFs for a clue, computed against the body field.

    Returns None if no content token survives the analyzer.
    """
    toks = _content_tokens(clue)
    if not toks:
        return None
    n_docs = ix.doc_count()
    log_n = math.log(n_docs)
    out: List[float] = []
    with ix.searcher() as searcher:
        reader = searcher.reader()
        for tok in toks:
            df = reader.doc_frequency("body", tok)
            if df == 0:
                continue
            out.append(log_n - math.log(df))
    return out or None


def _summarize(idfs: List[float], statistic: str) -> float:
    if statistic == "mean":
        return sum(idfs) / len(idfs)
    if statistic == "max":
        return max(idfs)
    if statistic == "median":
        s = sorted(idfs)
        n = len(s)
        return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2
    raise ValueError(statistic)


def _bucketize(values: List[Tuple[float, bool]], n_bins: int = 5):
    """Equal-frequency binning by IDF; returns list of (label, n,
    n_correct) tuples in increasing-IDF order.
    """
    sorted_vals = sorted(values, key=lambda x: x[0])
    n = len(sorted_vals)
    chunk = math.ceil(n / n_bins)
    out = []
    for i in range(n_bins):
        bin_data = sorted_vals[i * chunk : (i + 1) * chunk]
        if not bin_data:
            continue
        idf_lo = bin_data[0][0]
        idf_hi = bin_data[-1][0]
        n_b = len(bin_data)
        n_c = sum(1 for _, c in bin_data if c)
        label = f"[{idf_lo:.1f}-{idf_hi:.1f}]"
        out.append((label, n_b, n_c))
    return out


def _ascii_chart(buckets, statistic: str) -> str:
    width = 30
    out = ["", f"{statistic.capitalize()} clue-token IDF vs P@1 "
                f"(equal-frequency bins):", ""]
    for label, n, n_c in buckets:
        rate = n_c / n if n else 0
        bars = int(round(rate * width))
        out.append(
            f"  IDF {label:<12} n={n:>3}  P@1={rate:.2f}  "
            f"|{'#' * bars}{'.' * (width - bars)}|"
        )
    return "\n".join(out)


def _save_plot(buckets, mode: str, statistic: str, out_path: str) -> bool:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return False
    labels = [b[0] for b in buckets]
    rates = [b[2] / b[1] if b[1] else 0 for b in buckets]
    counts = [b[1] for b in buckets]
    fig, ax = plt.subplots(figsize=(7, 4))
    bars = ax.bar(range(len(labels)), rates, color="#4a7ba6")
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_xlabel(f"{statistic.capitalize()} clue-token IDF (quintile-binned)")
    ax.set_ylabel(f"P@1 ({mode} mode)")
    ax.set_title(f"Effect of clue {statistic}-IDF on retrieval correctness "
                 f"({mode})")
    ax.set_ylim(0, 1.0)
    for bar, n in zip(bars, counts):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.02,
                f"n={n}", ha="center", va="bottom", fontsize=8)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    return True


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--results", default="results/baseline.json",
                   help="results JSON whose per-question rank we use as the "
                        "correctness signal")
    p.add_argument("--index-dir", default="index")
    p.add_argument("--bins", type=int, default=5)
    p.add_argument("--statistic", choices=["mean", "max", "median"],
                   default="max",
                   help="which per-clue summary of token IDFs to bin on. "
                        "'max' best matches the 'rare distinguishing token' "
                        "claim; 'mean' is more sensitive to overall clue "
                        "specificity.")
    p.add_argument("--out-image", default="results/idf_histogram.png")
    args = p.parse_args()

    print(f"[step 1] loading results from {args.results} ...", flush=True)
    with io.open(args.results, encoding="utf-8") as fh:
        data = json.load(fh)
    print(f"         {len(data['results'])} questions, mode={data['mode']}",
          flush=True)

    print(f"[step 2] opening Whoosh index at {args.index_dir} ...", flush=True)
    ix = open_index(args.index_dir)
    print(f"         {ix.doc_count()} documents.", flush=True)

    print(f"[step 3] computing per-token IDFs for each clue "
          f"(summary={args.statistic}) ...", flush=True)
    paired: List[Tuple[float, bool]] = []
    skipped = 0
    for r in data["results"]:
        idfs = _clue_idfs(ix, r["clue"])
        if not idfs:
            skipped += 1
            continue
        paired.append((_summarize(idfs, args.statistic), r["rank"] == 1))
    print(f"         {len(paired)} usable, {skipped} skipped (no content tokens).",
          flush=True)

    print(f"[step 4] binning into {args.bins} equal-frequency IDF buckets ...",
          flush=True)
    buckets = _bucketize(paired, n_bins=args.bins)

    print()
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"mode             : {data['mode']}")
    print(f"statistic        : {args.statistic}")
    print(f"questions used   : {len(paired)} / {len(data['results'])}")
    print(_ascii_chart(buckets, args.statistic))

    saved = _save_plot(buckets, mode=data["mode"], statistic=args.statistic,
                       out_path=args.out_image)
    if saved:
        print(f"\n[step 5] saved chart to {args.out_image}")
    else:
        print("\n[step 5] matplotlib not available; skipping PNG.")


if __name__ == "__main__":
    main()

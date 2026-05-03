"""Build a Whoosh index over the wiki-subset.

Schema choices:
- ``title``  : ID + stemmed text (stored, retrievable, searchable)
- ``body``   : stemmed text (searchable, not stored — saves disk)
- ``raw_title``: stored exact string (for answer comparison)

We use Whoosh's ``StemmingAnalyzer`` (Porter stemmer + standard English
stopwords + lowercasing). Stemming helps because Jeopardy clues and
Wikipedia article titles often use different morphological forms of the
same word ("burning" vs "burned", "panda" vs "pandas"). Stopwords are
removed because Jeopardy clues contain a lot of glue words.

Run as a script::

    python -m src.build_index --data-dir ../data --index-dir ../index
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import time

from whoosh import index
from whoosh.analysis import StemmingAnalyzer
from whoosh.fields import ID, STORED, TEXT, Schema

# Make `src.` imports work whether run as ``python build_index.py`` or
# ``python -m src.build_index``.
if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from wiki_parser import parse_all  # type: ignore
else:
    from .wiki_parser import parse_all


def make_schema() -> Schema:
    """Schema: stemmed analyzer on title (boostable) and body."""
    stem_ana = StemmingAnalyzer()
    return Schema(
        title=TEXT(analyzer=stem_ana, stored=True, field_boost=2.0),
        body=TEXT(analyzer=stem_ana, stored=False),
        raw_title=STORED(),
        doc_id=ID(stored=True, unique=True),
    )


def build(data_dir: str, index_dir: str, *, clean: bool = True) -> int:
    """Index every page in ``data_dir`` into ``index_dir``. Returns doc count."""
    print(f"[step 1] preparing index dir at {index_dir} (clean={clean}) ...",
          flush=True)
    if clean and os.path.isdir(index_dir):
        shutil.rmtree(index_dir)
    os.makedirs(index_dir, exist_ok=True)

    print(f"[step 2] creating Whoosh schema (StemmingAnalyzer, title boost ×2) ...",
          flush=True)
    schema = make_schema()
    ix = index.create_in(index_dir, schema)
    writer = ix.writer(limitmb=512, procs=1, multisegment=True)

    print(f"[step 3] streaming pages from {data_dir} and indexing ...",
          flush=True)

    n = 0
    t0 = time.time()
    seen_ids: set[str] = set()
    for title, body in parse_all(data_dir):
        # Disambiguate duplicate titles by appending a counter.
        doc_id = title
        suffix = 1
        while doc_id in seen_ids:
            suffix += 1
            doc_id = f"{title}#{suffix}"
        seen_ids.add(doc_id)

        writer.add_document(
            title=title,
            body=body,
            raw_title=title,
            doc_id=doc_id,
        )
        n += 1
        if n % 10_000 == 0:
            print(f"  indexed {n:,} pages ({time.time() - t0:.0f}s)", flush=True)

    print(f"[step 4] committing {n:,} pages to disk ...", flush=True)
    writer.commit()
    elapsed = time.time() - t0
    print()
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"indexed pages   : {n:,}")
    print(f"index directory : {index_dir}")
    print(f"elapsed time    : {elapsed:.0f}s ({elapsed / 60:.1f} min)")
    return n


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--data-dir", default="data")
    p.add_argument("--index-dir", default="index")
    p.add_argument("--keep", action="store_true",
                   help="don't wipe existing index dir before writing")
    args = p.parse_args()
    build(args.data_dir, args.index_dir, clean=not args.keep)


if __name__ == "__main__":
    main()

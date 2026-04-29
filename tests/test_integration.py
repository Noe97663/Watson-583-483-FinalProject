"""End-to-end smoke test: build a tiny index, query it, verify the
right page is returned. Touches every module: parser → builder →
watson → evaluator. Doesn't depend on the full data set."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

try:
    import whoosh  # noqa: F401
    HAVE_WHOOSH = True
except ImportError:
    HAVE_WHOOSH = False

if HAVE_WHOOSH:
    from build_index import build  # noqa: E402
    from evaluate import Question, evaluate  # noqa: E402
    from watson import open_index, search  # noqa: E402


# Three pages with very distinct vocabulary so retrieval is unambiguous.
TINY_WIKI = """\
[[Komodo dragon]]

CATEGORIES: Lizards, Indonesia

The Komodo dragon is Indonesia's largest lizard. It is protected from
poachers in the Komodo National Park.


[[Washington Post]]

CATEGORIES: Newspapers, Washington D.C.

The Washington Post is a major American daily newspaper published in
the nation's capital. It is widely read.


[[Cairo]]

CATEGORIES: Capitals of Egypt, African cities

Cairo is the capital of Egypt. Several bridges including El Tahrir
cross the Nile river in this city.
"""


@unittest.skipUnless(HAVE_WHOOSH, "whoosh not installed")
class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.mkdtemp()
        cls.data_dir = os.path.join(cls.tmp, "data")
        cls.index_dir = os.path.join(cls.tmp, "index")
        os.makedirs(cls.data_dir)
        with open(
            os.path.join(cls.data_dir, "enwiki-test.txt"), "w", encoding="utf-8"
        ) as fh:
            fh.write(TINY_WIKI)
        n = build(cls.data_dir, cls.index_dir)
        assert n == 3, n
        cls.ix = open_index(cls.index_dir)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.ix.close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_clue_with_unique_terms_finds_right_page(self) -> None:
        hits = search(
            self.ix,
            "Indonesia's largest lizard, protected from poachers",
            category="CONSERVATION",
            top_k=3,
        )
        self.assertGreater(len(hits), 0)
        self.assertEqual(hits[0].title, "Komodo dragon")

    def test_capital_clue_with_decoy(self) -> None:
        # The Nile/El Tahrir clue: in baseline mode, a page literally named
        # "Nile" would outrank Cairo, but our tiny index doesn't have one,
        # so Cairo should win in either mode.
        hits = search(
            self.ix,
            "Several bridges, including El Tahrir, cross the Nile in this capital",
            category="AFRICAN CITIES",
            top_k=3,
            mode="improved",
        )
        self.assertEqual(hits[0].title, "Cairo")

    def test_evaluate_pipeline(self) -> None:
        qs = [
            Question(
                category="CONSERVATION",
                clue="Indonesia's largest lizard, protected from poachers",
                aliases=("Komodo dragon",),
            ),
            Question(
                category="NEWSPAPERS",
                clue="The dominant paper in our nation's capital",
                aliases=("Washington Post",),
            ),
        ]
        results = evaluate(self.ix, qs, top_k=3, mode="baseline")
        self.assertEqual(results[0].rank, 1)
        self.assertEqual(results[1].rank, 1)


if __name__ == "__main__":
    unittest.main()

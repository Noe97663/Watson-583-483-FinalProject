"""Tests for question parsing + evaluation math."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from evaluate import (  # noqa: E402
    QResult,
    Question,
    is_match,
    normalize_title,
    read_questions,
    summary,
)
from watson import Hit  # noqa: E402


SAMPLE_QUESTIONS = """\
NEWSPAPERS
The dominant paper in our nation's capital, it's among the top 10 U.S. papers in circulation
The Washington Post

CONSERVATION
In 1980 China founded a center for these cute creatures in its bamboo-rich Wolong Nature Preserve
Panda|Giant panda

OLD YEAR'S RESOLUTIONS
Feb. 1, National Freedom Day, is the date in 1865 when a resolution sent the states an amendment ending this
Slavery|Slavery in the United States
"""


class EvaluatorTests(unittest.TestCase):
    def test_read_questions_parses_aliases(self) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as fh:
            fh.write(SAMPLE_QUESTIONS)
            path = fh.name
        try:
            qs = read_questions(path)
        finally:
            os.unlink(path)
        self.assertEqual(len(qs), 3)
        self.assertEqual(qs[0].category, "NEWSPAPERS")
        self.assertEqual(qs[0].aliases, ("The Washington Post",))
        self.assertEqual(qs[1].aliases, ("Panda", "Giant panda"))
        self.assertEqual(qs[2].aliases, ("Slavery", "Slavery in the United States"))

    def test_normalize_title_handles_the_and_punct(self) -> None:
        self.assertEqual(normalize_title("The Washington Post"), "washington post")
        self.assertEqual(
            normalize_title("Slavery in the United States"),
            "slavery in the united states",
        )
        self.assertEqual(normalize_title("O'Hare"), "o hare")

    def test_is_match_against_aliases(self) -> None:
        self.assertTrue(is_match("Washington Post", ["The Washington Post"]))
        self.assertTrue(is_match("Panda", ["Panda", "Giant panda"]))
        self.assertTrue(is_match("Giant panda", ["Panda", "Giant panda"]))
        self.assertFalse(is_match("Washington", ["The Washington Post"]))

    def test_summary_metrics(self) -> None:
        q = Question("X", "clue", ("gold",))
        # rank 1, rank 3, miss
        results = [
            QResult(q, [Hit(1, 1.0, "gold")], rank=1),
            QResult(q, [Hit(1, 1.0, "x"), Hit(2, 0.5, "y"), Hit(3, 0.3, "gold")], rank=3),
            QResult(q, [Hit(1, 1.0, "x")], rank=0),
        ]
        s = summary(results)
        self.assertEqual(s["n"], 3)
        self.assertAlmostEqual(s["p_at_1"], 1 / 3)
        self.assertAlmostEqual(s["p_at_5"], 2 / 3)
        # MRR = (1/1 + 1/3 + 0) / 3 = 4/9
        self.assertAlmostEqual(s["mrr"], 4 / 9)


if __name__ == "__main__":
    unittest.main()

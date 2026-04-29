"""Tests for the query-construction helpers in watson.py."""
from __future__ import annotations

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from watson import (  # noqa: E402
    _build_query_string,
    _capitalized_runs,
    _quoted_phrases,
    _sanitize,
)


class QueryBuilderTests(unittest.TestCase):
    def test_sanitize_strips_query_syntax(self) -> None:
        self.assertNotIn(":", _sanitize("Mr. Smith: hello"))
        self.assertNotIn("(", _sanitize("foo (bar) baz"))
        self.assertNotIn(")", _sanitize("foo (bar) baz"))
        self.assertEqual(_sanitize("plain text"), "plain text")

    def test_quoted_phrases_extracts_double_quoted(self) -> None:
        clue = (
            'He won an Oscar for "Good Will Hunting" and starred in '
            '"The Sum of All Fears"'
        )
        phrases = _quoted_phrases(clue)
        self.assertIn("Good Will Hunting", phrases)
        self.assertIn("The Sum of All Fears", phrases)

    def test_capitalized_runs_only_returns_multi_word_entities(self) -> None:
        # Single mid-clue capitals like "Italian" or "Adoration" are NOT
        # multi-word runs and should be left alone (they regress retrieval
        # when boosted indiscriminately).
        runs = _capitalized_runs("This Italian painter depicted the Adoration")
        self.assertEqual(runs, [])

    def test_capitalized_runs_picks_up_named_entity(self) -> None:
        runs = _capitalized_runs(
            "Pierre Cauchon, Bishop of Beauvais, presided over the trial"
        )
        self.assertIn("Pierre Cauchon", runs)

    def test_baseline_query_passes_clue_through_verbatim(self) -> None:
        q = _build_query_string("clue text", None, expand=False)
        self.assertEqual(q, "clue text")

    def test_baseline_query_ignores_category_at_query_time(self) -> None:
        # Category is intentionally NOT injected into the BM25 query
        # in any mode (it's noisy); it's reserved for future rerank use.
        q = _build_query_string("hello world", "1920s NEWS FLASH!", expand=False)
        self.assertEqual(q, "hello world")
        q2 = _build_query_string("hello world", "1920s NEWS FLASH!", expand=True)
        self.assertNotIn("FLASH", q2)

    def test_improved_query_boosts_quoted_phrases(self) -> None:
        clue = 'This painter depicted the "Adoration of the Golden Calf"'
        q = _build_query_string(clue, None, expand=True)
        self.assertIn('"Adoration of the Golden Calf"^3', q)

    def test_improved_query_boosts_capitalized_runs(self) -> None:
        clue = "Pierre Cauchon, Bishop of Beauvais, presided over the trial"
        q = _build_query_string(clue, None, expand=True)
        self.assertIn('"Pierre Cauchon"^2', q)


if __name__ == "__main__":
    unittest.main()

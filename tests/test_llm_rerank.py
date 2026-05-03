"""Tests for the LLM reranker (no real API calls — client is mocked)."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from llm_rerank import LLMReranker, _cache_key  # noqa: E402
from watson import Hit  # noqa: E402


def _fake_response(best_index: int, reasoning: str = "because"):
    """Build a fake anthropic Message-shaped response object."""
    return SimpleNamespace(
        content=[
            SimpleNamespace(
                type="text",
                text=json.dumps({"best_index": best_index, "reasoning": reasoning}),
            )
        ]
    )


def _hits(*titles: str) -> list[Hit]:
    return [Hit(rank=i + 1, score=10.0 - i, title=t) for i, t in enumerate(titles)]


class CacheKeyTests(unittest.TestCase):
    def test_key_is_stable_across_candidate_order(self) -> None:
        # Same clue + same set of candidates → same key, regardless of
        # the order they were ranked in by the IR system. Tiny BM25
        # rerankings shouldn't trigger a re-query.
        a = _cache_key("clue", ["A", "B", "C"])
        b = _cache_key("clue", ["C", "B", "A"])
        self.assertEqual(a, b)

    def test_key_changes_with_clue(self) -> None:
        a = _cache_key("clue 1", ["A", "B"])
        b = _cache_key("clue 2", ["A", "B"])
        self.assertNotEqual(a, b)


class RerankerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.cache_path = os.path.join(self.tmpdir.name, "cache.json")
        self.client = MagicMock()

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def _make(self) -> LLMReranker:
        return LLMReranker(cache_path=self.cache_path, client=self.client)

    def test_picks_chosen_candidate_first(self) -> None:
        self.client.messages.create.return_value = _fake_response(3)
        reranker = self._make()
        hits = _hits("Wrong A", "Wrong B", "Right Answer", "Wrong D")

        out = reranker.rerank("clue", "CAT", hits)

        self.assertEqual(out[0].title, "Right Answer")
        # Other titles preserve their relative order, ranks renumbered.
        self.assertEqual([h.title for h in out],
                         ["Right Answer", "Wrong A", "Wrong B", "Wrong D"])
        self.assertEqual([h.rank for h in out], [1, 2, 3, 4])

    def test_zero_index_means_keep_original_order(self) -> None:
        # best_index = 0 is the model's "none of these" escape hatch.
        self.client.messages.create.return_value = _fake_response(0)
        reranker = self._make()
        hits = _hits("A", "B", "C")

        out = reranker.rerank("clue", "CAT", hits)
        self.assertEqual([h.title for h in out], ["A", "B", "C"])

    def test_out_of_range_index_is_safe(self) -> None:
        self.client.messages.create.return_value = _fake_response(99)
        reranker = self._make()
        hits = _hits("A", "B", "C")
        out = reranker.rerank("clue", "CAT", hits)
        self.assertEqual([h.title for h in out], ["A", "B", "C"])

    def test_empty_or_singleton_hits_no_api_call(self) -> None:
        reranker = self._make()
        self.assertEqual(reranker.rerank("clue", "CAT", []), [])
        single = _hits("Only")
        out = reranker.rerank("clue", "CAT", single)
        self.assertEqual([h.title for h in out], ["Only"])
        self.client.messages.create.assert_not_called()

    def test_repeat_call_uses_cache_not_api(self) -> None:
        self.client.messages.create.return_value = _fake_response(2)
        reranker = self._make()
        hits = _hits("A", "B", "C")
        reranker.rerank("clue", "CAT", hits)
        reranker.rerank("clue", "CAT", _hits("A", "B", "C"))
        self.client.messages.create.assert_called_once()

    def test_cache_persists_across_instances(self) -> None:
        self.client.messages.create.return_value = _fake_response(2)
        first = self._make()
        first.rerank("clue", "CAT", _hits("A", "B", "C"))

        # Second instance shares the on-disk cache file. A fresh client
        # whose .create would explode if called proves the cache hit.
        client2 = MagicMock()
        client2.messages.create.side_effect = AssertionError("should not call API")
        second = LLMReranker(cache_path=self.cache_path, client=client2)
        out = second.rerank("clue", "CAT", _hits("A", "B", "C"))
        self.assertEqual(out[0].title, "B")


if __name__ == "__main__":
    unittest.main()

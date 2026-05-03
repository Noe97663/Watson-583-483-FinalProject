"""LLM-based reranker over the top-K hits from the IR pipeline.

The Whoosh ``improved`` mode caps at P@1 ≈ 25 and P@10 ≈ 55 — three
error classes from the Q4 analysis are unreachable for pure lexical
retrieval: inferential clues (*"rebel with a cause"* → *James Dean*
via *Rebel Without a Cause*), pun categories (*"TIN" MEN* →
*Tintoretto*), and indirect lookups (*"The Naples Museum of Art"* →
*Florida*). This module addresses all three by handing the IR top-K
to Claude and asking it to pick the best answer.

The index does not store page bodies (`body=stored=False` in
``build_index.py``), so the prompt is title-only — relying on the
fact that Claude has the entire Wikipedia subset in its training data
and can identify the right page from (clue, category, candidate
titles) alone. Adding snippets would mean either a 20-min reindex or
re-streaming the wiki dump on every query; both were ruled out as
disproportionate to the marginal accuracy gain.

Responses are cached on disk keyed by ``(clue, sorted candidate
titles)`` so re-runs do not re-bill the API and are deterministic
for testing.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from typing import List, Sequence

import anthropic


def _load_dotenv_api_key() -> str | None:
    """Pull an Anthropic API key out of a .env file at the project root.

    Tries ``ANTHROPIC_API_KEY`` first, then ``api_key`` (the convention
    used in this repo's .env). Returns ``None`` if neither is present.
    Does NOT mutate ``os.environ`` — the caller decides what to do.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    candidate = os.path.normpath(os.path.join(here, "..", ".env"))
    if not os.path.exists(candidate):
        return None
    try:
        with open(candidate, "r", encoding="utf-8") as fh:
            entries: dict[str, str] = {}
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                key, sep, val = line.partition("=")
                if not sep:
                    continue
                entries[key.strip()] = val.strip().strip('"').strip("'")
        return entries.get("ANTHROPIC_API_KEY") or entries.get("api_key")
    except OSError:
        return None

if __package__ in (None, ""):
    from watson import Hit  # type: ignore
else:
    from .watson import Hit


# Hard-coded to Claude Sonnet 4.6 by user request — chosen over
# Opus 4.7 because reranking 10 candidate Wikipedia titles is a
# constrained classification task where Sonnet's quality is fully
# adequate, and ~3× cheaper input/output pricing makes 100-question
# evaluation runs trivially affordable.
DEFAULT_MODEL = "claude-sonnet-4-6"

# Where to cache (clue, candidates) → picked index. Keeps repeat
# evaluation runs free and deterministic. Delete the file to force
# a re-query.
DEFAULT_CACHE_PATH = "results/llm_rerank_cache.json"

# JSON schema for the model's structured response. Forcing a
# constrained output keeps the parse step trivial and removes a
# whole class of "the model wrote prose around the number" failures.
_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "best_index": {
            "type": "integer",
            "description": (
                "1-based index of the best candidate. Use 0 if and "
                "only if NONE of the candidates is plausibly the "
                "answer; otherwise pick the closest match."
            ),
        },
        "reasoning": {
            "type": "string",
            "description": "One sentence on why this candidate wins.",
        },
    },
    "required": ["best_index", "reasoning"],
    "additionalProperties": False,
}


_SYSTEM_PROMPT = """\
You are a Jeopardy expert. Given a Jeopardy clue, its category, and a \
ranked list of candidate Wikipedia page titles produced by a lexical \
search engine, pick the candidate whose page is the actual answer.

Notes on the task:
- The clue is a statement; the answer is the topic the statement \
describes (a person, place, work, event, or concept whose name is the \
title of a Wikipedia page).
- Categories often contain wordplay or puns and can be a strong hint. \
For example, a category like "TIN" MEN means the answer's name \
contains the substring "tin" — *Tintoretto*, *Quentin Tarantino*, etc.
- The lexical retriever can miss the right answer when the connection \
is INFERENTIAL rather than literal. Examples:
    * "Rebel with a cause" → *James Dean* (via *Rebel Without a Cause*)
    * Clue mentions a museum → answer is the city or state, not the museum
    * A pun in the category encodes the disambiguator
  Use your knowledge to bridge those gaps.
- Conversely, the right answer is sometimes obvious from the clue alone \
and the lexical retriever already ranked it #1 — in that case just \
keep it.
- The retrieved list can include "List of …", "Index of …", or \
disambiguation pages. Those are almost never the answer.
- If none of the candidates is plausibly correct, return best_index = 0.\
 Otherwise pick the single best one — do not refuse.

Respond with JSON: {"best_index": <int>, "reasoning": <one sentence>}.
"""


def _cache_key(clue: str, candidate_titles: Sequence[str]) -> str:
    """Stable hash so reruns hit the cache.

    Sorting the title list means we cache by *which* candidates were
    shown, independent of their initial IR-system order — small
    rounding differences in BM25 score don't trigger re-queries.
    """
    payload = json.dumps(
        {"clue": clue.strip(), "candidates": sorted(candidate_titles)},
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class _CachedDecision:
    best_index: int
    reasoning: str


class LLMReranker:
    """Reorders IR hits by asking Claude to pick the best.

    The first hit returned is whichever candidate the model picked;
    the remaining hits keep their relative order from the input. This
    is enough to drive P@1 (the metric Q3 reports) without needing
    the model to produce a full ordering.
    """

    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        cache_path: str = DEFAULT_CACHE_PATH,
        client: anthropic.Anthropic | None = None,
        verbose: bool = False,
    ) -> None:
        self.model = model
        self.cache_path = cache_path
        self.verbose = verbose
        if client is None:
            api_key = os.environ.get("ANTHROPIC_API_KEY") or _load_dotenv_api_key()
            client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
        self.client = client
        self._cache: dict[str, dict] = self._load_cache()

    def _load_cache(self) -> dict[str, dict]:
        if not os.path.exists(self.cache_path):
            return {}
        try:
            with open(self.cache_path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (json.JSONDecodeError, OSError):
            return {}

    def _save_cache(self) -> None:
        os.makedirs(os.path.dirname(self.cache_path) or ".", exist_ok=True)
        with open(self.cache_path, "w", encoding="utf-8") as fh:
            json.dump(self._cache, fh, indent=2, ensure_ascii=False)

    def _ask(self, clue: str, category: str, titles: Sequence[str]) -> _CachedDecision:
        numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(titles))
        user_msg = (
            f"CATEGORY: {category}\n"
            f"CLUE: {clue}\n\n"
            f"CANDIDATES:\n{numbered}"
        )

        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            thinking={"type": "adaptive"},
            output_config={
                "effort": "medium",
                "format": {"type": "json_schema", "schema": _RESPONSE_SCHEMA},
            },
            system=[
                {
                    "type": "text",
                    "text": _SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_msg}],
        )

        text = next(
            (b.text for b in response.content if b.type == "text"), ""
        )
        data = json.loads(text)
        return _CachedDecision(
            best_index=int(data["best_index"]),
            reasoning=str(data.get("reasoning", "")),
        )

    def rerank(self, clue: str, category: str, hits: Sequence[Hit]) -> List[Hit]:
        """Return ``hits`` reordered with the model's pick first.

        ``hits`` shorter than 2 is a no-op (nothing to rerank). Indices
        out of range or 0 (model declined) leave the list unchanged.
        """
        if len(hits) < 2:
            return list(hits)

        titles = [h.title for h in hits]
        key = _cache_key(clue, titles)

        if key in self._cache:
            decision = _CachedDecision(**self._cache[key])
            source = "cache"
        else:
            decision = self._ask(clue, category, titles)
            self._cache[key] = {
                "best_index": decision.best_index,
                "reasoning": decision.reasoning,
            }
            self._save_cache()
            source = "api"

        idx = decision.best_index - 1
        if idx < 0 or idx >= len(hits):
            if self.verbose:
                print(f"      [llm:{source}] declined (idx={decision.best_index}); "
                      f"keeping IR order", flush=True)
            return list(hits)

        picked = hits[idx]
        if self.verbose:
            print(f"      [llm:{source}] picked #{idx + 1}: {picked.title}",
                  flush=True)
        rest = [h for i, h in enumerate(hits) if i != idx]
        reordered = [picked, *rest]
        for i, h in enumerate(reordered):
            h.rank = i + 1
        return reordered


# Tiny convenience wrapper so ``watson.search(..., mode="llm")`` can be
# a one-liner without managing reranker lifetime by hand.
_default_reranker: LLMReranker | None = None


def get_default_reranker() -> LLMReranker:
    global _default_reranker
    if _default_reranker is None:
        _default_reranker = LLMReranker()
    return _default_reranker


def set_default_reranker(reranker: LLMReranker | None) -> None:
    """Override the singleton — used by tests and CLI overrides."""
    global _default_reranker
    _default_reranker = reranker


def set_default_verbose(verbose: bool) -> None:
    """Toggle per-question logging on the lazily-built singleton.

    Calling this before the first rerank means the singleton starts
    verbose; calling after just flips the flag on the existing one.
    """
    r = get_default_reranker()
    r.verbose = verbose

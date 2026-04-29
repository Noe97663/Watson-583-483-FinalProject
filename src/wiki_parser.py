"""Parse the wiki-subset .txt files into (title, body) pairs.

Each file holds many pages concatenated together. A page begins with a line
of the form ``[[Title]]`` (the *only* thing on that line) and ends just
before the next such header or the end of file. Pages whose body is just
``#REDIRECT ...`` are skipped, since they carry no retrievable content.

The format also embeds raw wiki markup: ``[tpl]...[/tpl]`` citation blobs,
``[ref]...[/ref]`` references, ``==Section==`` headers, ``[[Link|Text]]``
links, and a ``CATEGORIES: a, b, c`` line near the top. We strip the noisy
template/ref blobs and normalize headers/links so the indexer sees plain
text, but we keep the category list (useful retrieval signal).
"""
from __future__ import annotations

import os
import re
from typing import Iterable, Iterator, Tuple

# Page-title line: starts at column 0, opens with [[, closes with ]] on the
# *same* line (this excludes multi-line [[File:...|...]] image embeds whose
# closing ]] is many lines later).
_TITLE_RE = re.compile(r"^\[\[([^\[\]]+)\]\]\s*$")

# Wiki-namespace prefixes that look like titles but aren't real pages.
_NAMESPACE_PREFIXES = ("File:", "Image:", "Category:", "Wikipedia:", "Template:")

# Markup-stripping patterns applied to the joined body text.
_TPL_RE = re.compile(r"\[tpl\].*?\[/tpl\]", re.DOTALL)
_REF_RE = re.compile(r"\[ref\].*?\[/ref\]", re.DOTALL)
_HEADER_RE = re.compile(r"={2,}\s*([^=\n]+?)\s*={2,}")
_LINK_PIPE_RE = re.compile(r"\[\[([^\[\]|]+)\|([^\[\]]+)\]\]")  # [[A|B]] -> B
_LINK_RE = re.compile(r"\[\[([^\[\]]+)\]\]")                    # [[A]]   -> A
_EXT_LINK_RE = re.compile(r"\[https?://\S+\s+([^\]]+)\]")       # [http://x text] -> text
_BARE_URL_RE = re.compile(r"https?://\S+")
_CATS_RE = re.compile(r"^CATEGORIES:\s*", re.MULTILINE)


def _is_real_title(line_match: re.Match) -> bool:
    title = line_match.group(1).strip()
    if not title:
        return False
    return not any(title.startswith(p) for p in _NAMESPACE_PREFIXES)


def _clean_body(raw: str) -> str:
    """Strip template/ref blobs, headers, links, URLs from the joined body."""
    text = _TPL_RE.sub(" ", raw)
    text = _REF_RE.sub(" ", text)
    text = _LINK_PIPE_RE.sub(r"\2", text)
    text = _LINK_RE.sub(r"\1", text)
    text = _EXT_LINK_RE.sub(r"\1", text)
    text = _BARE_URL_RE.sub(" ", text)
    text = _HEADER_RE.sub(r"\1", text)
    text = _CATS_RE.sub("", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _is_redirect(body_lines: list[str]) -> bool:
    for line in body_lines:
        s = line.strip()
        if not s:
            continue
        return s.upper().startswith("#REDIRECT")
    return True  # empty body counts as junk


def parse_pages(path: str) -> Iterator[Tuple[str, str]]:
    """Yield ``(title, body)`` tuples from a single wiki .txt file.

    Streams the file line by line so the full file never sits in memory.
    """
    title: str | None = None
    buf: list[str] = []

    def flush() -> Iterator[Tuple[str, str]]:
        if title is None:
            return
        if _is_redirect(buf):
            return
        body = _clean_body("\n".join(buf))
        if body:
            yield title, body

    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = _TITLE_RE.match(line)
            if m and _is_real_title(m):
                yield from flush()
                title = m.group(1).strip()
                buf = []
            else:
                if title is not None:
                    buf.append(line.rstrip("\n"))
        yield from flush()


def iter_wiki_files(data_dir: str) -> Iterable[str]:
    """Return wiki file paths in ``data_dir`` (excluding macOS ._ dotfiles)."""
    for name in sorted(os.listdir(data_dir)):
        if name.startswith("._"):
            continue
        if name.startswith("enwiki-") and name.endswith(".txt"):
            yield os.path.join(data_dir, name)


def parse_all(data_dir: str) -> Iterator[Tuple[str, str]]:
    """Yield ``(title, body)`` from every wiki file in ``data_dir`` in order."""
    for path in iter_wiki_files(data_dir):
        yield from parse_pages(path)

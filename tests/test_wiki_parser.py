"""Unit tests for the wiki parser. Runs without any indexed data."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from wiki_parser import parse_pages, _clean_body  # noqa: E402


# A synthetic mini wiki file containing every quirk we need to handle.
SAMPLE = """\
[[BBC]]

CATEGORIES: British Broadcasting, Public broadcasters

The British Broadcasting Corporation (BBC) is a [[public service broadcaster]].
Founded in [tpl]cite web|year=1922|publisher=BBC[/tpl] 1922.

==History==

It was the [[first|world's first]] national broadcaster.[ref]Briggs 1985[/ref]


[[Bell Curve]]

#REDIRECT Bell curve [tpl]R from other capitalisation[/tpl]


[[Building society]]

CATEGORIES: Cooperatives

A building society is a financial institution.

[[File:Foo.svg|thumb|This is a multi-line image
embed that should not start a new page.]]

More content for the building society article.


[[Empty page]]

"""


class ParserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        )
        self.tmp.write(SAMPLE)
        self.tmp.close()

    def tearDown(self) -> None:
        os.unlink(self.tmp.name)

    def test_yields_only_real_pages(self) -> None:
        pages = list(parse_pages(self.tmp.name))
        titles = [t for t, _ in pages]
        self.assertIn("BBC", titles)
        self.assertIn("Building society", titles)
        # Redirects are skipped.
        self.assertNotIn("Bell Curve", titles)
        # Empty pages are skipped.
        self.assertNotIn("Empty page", titles)

    def test_image_embed_does_not_start_page(self) -> None:
        titles = [t for t, _ in parse_pages(self.tmp.name)]
        # The [[File:Foo.svg|...]] line is mid-document and shouldn't
        # appear as a separate page title.
        self.assertNotIn("File:Foo.svg", titles)
        self.assertEqual(len(titles), 2)

    def test_clean_body_strips_markup(self) -> None:
        body = _clean_body(
            "Foo [tpl]cite web|year=1922[/tpl] bar [ref]Briggs[/ref] baz "
            "==Section== qux [[A|B]] [[C]]"
        )
        self.assertNotIn("[tpl]", body)
        self.assertNotIn("[/tpl]", body)
        self.assertNotIn("[ref]", body)
        self.assertNotIn("==", body)
        self.assertIn("Section", body)
        self.assertIn(" B ", " " + body + " ")
        self.assertIn(" C ", " " + body + " ")

    def test_categories_are_kept_as_text(self) -> None:
        pages = dict(parse_pages(self.tmp.name))
        bbc = pages["BBC"]
        # The CATEGORIES: line content should survive (good retrieval signal),
        # but the literal "CATEGORIES:" prefix should be stripped.
        self.assertIn("British Broadcasting", bbc)
        self.assertIn("Public broadcasters", bbc)
        self.assertNotIn("CATEGORIES:", bbc)


if __name__ == "__main__":
    unittest.main()

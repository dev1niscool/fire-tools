"""Exercise the published handbook as a GitHub Pages project site."""

import re
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit
from xml.etree import ElementTree


REPOSITORY = Path(__file__).resolve().parents[2]
SITE_URL = "https://dev1niscool.github.io/fire-tools/"
PAGES = {
    "index.html", "setup.html", "compatibility.html", "google-play.html",
    "ads.html", "apps.html", "tools.html", "resources.html",
}


class Page(HTMLParser):
    def __init__(self, path):
        super().__init__()
        self.labels = {"h1": [], "title": []}
        self.label_tag = None
        self.ids = []
        self.references = []
        self.stylesheets = []
        self.links = []
        self.nav_links = []
        self.nav_depth = 0
        self.feed(path.read_text(encoding="utf-8"))
        self.close()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in self.labels:
            self.label_tag = tag
            self.labels[tag].append("")
        if tag == "nav":
            self.nav_depth += 1
        if "id" in attrs:
            self.ids.append(attrs["id"])
        for attr in ("href", "src", "poster"):
            if attrs.get(attr):
                self.references.append(attrs[attr])
        if tag == "link" and "stylesheet" in attrs.get("rel", "").lower().split():
            self.stylesheets.append(attrs["href"])
        if tag == "a" and attrs.get("href"):
            self.links.append(attrs["href"])
            if self.nav_depth:
                self.nav_links.append(attrs["href"])

    def handle_endtag(self, tag):
        if tag == self.label_tag:
            self.label_tag = None
        if tag == "nav":
            self.nav_depth -= 1

    def handle_data(self, data):
        if self.label_tag:
            self.labels[self.label_tag][-1] += data


class HandbookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(temporary.cleanup)
        cls.site = Path(temporary.name) / "fire-tools"
        build = subprocess.run(
            [sys.executable, "website/build.py", "--output", str(cls.site)],
            cwd=REPOSITORY, capture_output=True, text=True,
        )
        if build.returncode != 0:
            raise AssertionError(build.stderr or build.stdout)
        cls.pages = {
            path.relative_to(cls.site).as_posix(): Page(path)
            for path in cls.site.rglob("*.html")
        }

    def local_target(self, source, reference):
        url = urlsplit(urljoin(urljoin(SITE_URL, source), reference))
        project = urlsplit(SITE_URL)
        if url.scheme not in ("https", "http") or url.netloc != project.netloc:
            return None
        path = unquote(url.path)
        self.assertTrue(path.startswith(project.path), f"{source}: {reference} escapes the project")
        name = path[len(project.path):]
        if (self.site / name).is_dir():
            name = (Path(name) / "index.html").as_posix()
        return name, unquote(url.fragment)

    def test_build_emits_all_handbook_pages(self):
        self.assertFalse(PAGES - self.pages.keys(), f"Missing pages: {PAGES - self.pages.keys()}")

    def test_pages_have_distinct_titles_and_headings(self):
        for tag in ("title", "h1"):
            seen = set()
            for name, page in self.pages.items():
                with self.subTest(page=name, tag=tag):
                    self.assertEqual(len(page.labels[tag]), 1)
                    value = " ".join(page.labels[tag][0].split()).casefold()
                    self.assertTrue(value)
                    self.assertNotIn(value, seen)
                    seen.add(value)

    def test_local_links_assets_and_fragments_resolve(self):
        svg_ids = {}
        for name, page in self.pages.items():
            with self.subTest(page=name):
                duplicate = [anchor for anchor, count in Counter(page.ids).items() if count > 1]
                self.assertFalse(duplicate, f"Duplicate IDs on {name}: {duplicate}")
            for reference in page.references:
                with self.subTest(page=name, reference=reference):
                    target = self.local_target(name, reference)
                    if target is None:
                        continue
                    path, fragment = target
                    self.assertTrue((self.site / path).is_file(), f"Missing file: {path}")
                    if fragment and path in self.pages:
                        self.assertIn(fragment, self.pages[path].ids)
                    if fragment and path.endswith(".svg"):
                        if path not in svg_ids:
                            tree = ElementTree.parse(self.site / path)
                            svg_ids[path] = {element.get("id") for element in tree.iter()}
                        self.assertIn(fragment, svg_ids[path])

    def test_stylesheets_and_their_assets_are_published(self):
        for name, page in self.pages.items():
            with self.subTest(page=name):
                stylesheets = [self.local_target(name, link) for link in page.stylesheets]
                self.assertTrue(any(stylesheets), f"No project stylesheet on {name}")
        for css in self.site.rglob("*.css"):
            name = css.relative_to(self.site).as_posix()
            text = css.read_text(encoding="utf-8")
            self.assertTrue(text.strip(), name)
            for value in re.findall(r"url\(\s*([^)]*?)\s*\)", text, flags=re.I):
                reference = value.strip("'\"")
                with self.subTest(stylesheet=name, reference=reference):
                    target = self.local_target(name, reference)
                    if target:
                        self.assertTrue((self.site / target[0]).is_file(), target[0])

    def test_guides_are_reachable_and_have_return_navigation(self):
        visited = set()
        pending = ["index.html"]
        while pending:
            name = pending.pop()
            if name in visited:
                continue
            visited.add(name)
            for link in self.pages[name].links:
                target = self.local_target(name, link)
                if target and target[0] in self.pages:
                    pending.append(target[0])
        self.assertFalse(PAGES - visited, f"Unreachable guides: {PAGES - visited}")
        for name, page in self.pages.items():
            with self.subTest(page=name):
                destinations = {self.local_target(name, link) for link in page.nav_links}
                self.assertTrue(
                    any(
                        target and target[0] in self.pages and target[0] != name
                        for target in destinations
                    ),
                    f"No navigation link out of {name}",
                )


if __name__ == "__main__":
    unittest.main()

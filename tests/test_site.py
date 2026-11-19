"""The website builds from the docs, and every link inside it lands somewhere."""

import importlib.util
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(importlib.util.find_spec("markdown"), "needs the markdown package")
class SiteTests(unittest.TestCase):
    def test_builds_with_working_links(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import build_site
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            files = build_site.build(out, "Kapistyn/trapyze")
            for name in ("index.html", "guide.html", "changelog.html", "sitemap.xml", "robots.txt", "images/desktop.png"):
                self.assertIn(name, files)
            pages = {p: (out / p).read_text(encoding="utf-8") for p in ("index.html", "guide.html", "changelog.html")}
            ids = {p: set(re.findall(r'id="([^"]+)"', t)) for p, t in pages.items()}
            for page, text in pages.items():
                for link in re.findall(r'(?:href|src)="([^"]+)"', text):
                    if re.match(r"^[a-z]+:|^//", link) or link == "./":
                        continue
                    target, _, anchor = link.partition("#")
                    target = target or page
                    self.assertTrue((out / target).exists(), f"{page}: {link}")
                    if anchor:
                        self.assertIn(anchor, ids[target], f"{page}: {link}")
            self.assertIn("https://kapistyn.github.io/trapyze/sitemap.xml", (out / "robots.txt").read_text())
            self.assertIn('rel="canonical" href="https://kapistyn.github.io/trapyze/"', pages["index.html"])

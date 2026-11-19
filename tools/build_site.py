"""Build traPYze's website from the README, the guide and the changelog.

  python tools/build_site.py [out-dir] [owner/name]

Writes a small static site (default: _site/) for GitHub Pages: the front page from
README.md, guide.html from docs/guide.md, changelog.html, the images, a sitemap and
robots.txt. Needs the "markdown" package. The Pages workflow runs this on every push
to main, so the site follows the docs by itself.

Search engines: set the repository variable GOOGLE_SITE_VERIFICATION (and/or
BING_SITE_VERIFICATION) to the code from Google Search Console (Bing Webmaster Tools)
and the front page carries the matching tag.
"""

from __future__ import annotations

import datetime as dt
import html
import os
import re
import shutil
import sys
import tomllib
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parents[1]
PAGES = {"README.md": "index.html", "docs/guide.md": "guide.html", "CHANGELOG.md": "changelog.html"}


def site_url(repo: str) -> str:
    owner, name = repo.split("/")
    return f"https://{owner.lower()}.github.io/{name}/"


def fix_links(text: str, source: str, repo: str) -> str:
    """Point README/guide links at the site's own pages, and the rest at GitHub."""
    here = Path(source).parent

    def target(link: str) -> str:
        if re.match(r"^[a-z]+:|^#|^//", link):
            return link
        path, _, anchor = link.partition("#")
        full = (here / path).as_posix() if path else source
        full = os.path.normpath(full).replace("\\", "/")
        if full in PAGES:
            return PAGES[full] + (f"#{anchor}" if anchor else "")
        if full.startswith("docs/images/"):
            return "images/" + full.removeprefix("docs/images/")
        return f"https://github.com/{repo}/blob/main/{full}" + (f"#{anchor}" if anchor else "")

    text = re.sub(r'(\]\()([^)\s]+)(\))', lambda m: m[1] + target(m[2]) + m[3], text)
    return re.sub(r'((?:src|href)=")([^"]+)(")', lambda m: m[1] + target(m[2]) + m[3], text)


def slug(value: str, separator: str = "-") -> str:
    """GitHub's heading anchors, so links into the guide work the same on both."""
    value = re.sub(r"[^\w\- ]", "", value.strip().lower())
    return value.replace(" ", separator)


def render(text: str) -> str:
    md = markdown.Markdown(extensions=["tables", "fenced_code", "toc", "sane_lists"],
                           extension_configs={"toc": {"slugify": slug}})
    body = md.convert(text)
    # mermaid diagrams are drawn in the browser
    return re.sub(r'<pre><code class="language-mermaid">(.*?)</code></pre>',
                  lambda m: f'<pre class="mermaid">{m[1]}</pre>', body, flags=re.S)


CSS = """
:root{--bg:#f4f5f7;--panel:#fff;--ink:#1a1f29;--soft:#5b6473;--line:#dfe2e8;--accent:#2a4bd7;--code:#eef0f4}
@media (prefers-color-scheme:dark){:root{--bg:#0f131a;--panel:#171c25;--ink:#e6e9ef;--soft:#9aa3b2;--line:#2a313d;--accent:#7d97ff;--code:#1e2430}}
*{box-sizing:border-box}html{scroll-padding-top:72px}
body{margin:0;background:var(--bg);color:var(--ink);font:17px/1.6 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
a{color:var(--accent)}
header{position:sticky;top:0;z-index:5;background:var(--panel);border-bottom:1px solid var(--line)}
nav{max-width:1080px;margin:0 auto;display:flex;align-items:center;gap:22px;padding:12px 24px;flex-wrap:wrap}
nav .brand{display:flex;align-items:center;gap:10px;font-weight:700;font-size:19px;color:var(--ink);text-decoration:none;margin-right:auto}
nav .brand img{width:30px;height:30px}
nav a{text-decoration:none;font-weight:500}
nav .get{background:var(--accent);color:#fff;padding:8px 16px;border-radius:10px}
main{max-width:1080px;margin:0 auto;padding:32px 24px 64px}
article{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:28px 40px}
h1,h2,h3{line-height:1.25}h2{margin-top:2.2em;padding-top:.4em;border-top:1px solid var(--line)}
img{max-width:100%;height:auto;border-radius:10px}
table{border-collapse:collapse;width:100%;margin:1em 0;display:block;overflow-x:auto}
th,td{border:1px solid var(--line);padding:8px 12px;text-align:left;vertical-align:top}
td img{border:1px solid var(--line)}
code{background:var(--code);padding:.1em .35em;border-radius:5px;font-size:.92em}
pre{background:var(--code);padding:14px 18px;border-radius:10px;overflow-x:auto}pre code{background:none;padding:0}
pre.mermaid{background:none;text-align:center}
footer{max-width:1080px;margin:0 auto;padding:0 24px 40px;color:var(--soft);font-size:15px}
@media (max-width:700px){article{padding:20px}nav{gap:14px}}
"""


def page(title: str, description: str, body: str, url: str, repo: str, extra_head: str = "") -> str:
    image = url + "images/social-preview.png"
    data = ('{"@context":"https://schema.org","@type":"SoftwareApplication","name":"traPYze",'
            '"applicationCategory":"DeveloperApplication","operatingSystem":"Windows, macOS, Linux",'
            '"offers":{"@type":"Offer","price":"0","priceCurrency":"EUR"},'
            f'"license":"https://opensource.org/licenses/MIT","url":"{url}",'
            f'"downloadUrl":"https://github.com/{repo}/releases/latest","image":"{image}",'
            f'"softwareVersion":"{version()}","description":{json_str(description)}}}')
    mermaid = ('<script type="module">import m from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";'
               'm.initialize({startOnLoad:true,theme:matchMedia("(prefers-color-scheme: dark)").matches?"dark":"default"});</script>'
               if 'class="mermaid"' in body else "")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(description)}">
<link rel="canonical" href="{url}">
<link rel="icon" href="images/logo.png">
<meta property="og:type" content="website">
<meta property="og:title" content="{html.escape(title)}">
<meta property="og:description" content="{html.escape(description)}">
<meta property="og:url" content="{url}">
<meta property="og:image" content="{image}">
<meta name="twitter:card" content="summary_large_image">
{extra_head}<script type="application/ld+json">{data}</script>
<style>{CSS}</style>
</head>
<body>
<header><nav>
<a class="brand" href="./"><img src="images/logo.png" alt="">traPYze</a>
<a href="guide.html">Guide</a>
<a href="changelog.html">What's new</a>
<a href="https://github.com/{repo}">GitHub</a>
<a class="get" href="https://github.com/{repo}/releases/latest">Download</a>
</nav></header>
<main><article>
{body}
</article></main>
<footer>traPYze {version()} · free and open source under the MIT licence ·
<a href="https://github.com/{repo}">source on GitHub</a> ·
<a href="https://github.com/{repo}/issues">report a problem</a></footer>
{mermaid}
</body>
</html>
"""


def json_str(s: str) -> str:
    import json
    return json.dumps(s)


def version() -> str:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]


def verification() -> str:
    tags = []
    for env, name in (("GOOGLE_SITE_VERIFICATION", "google-site-verification"), ("BING_SITE_VERIFICATION", "msvalidate.01")):
        code = os.environ.get(env, "").strip()
        if code:
            tags.append(f'<meta name="{name}" content="{html.escape(code)}">\n')
    return "".join(tags)


TITLES = {
    "index.html": ("traPYze: run your Python scripts without a terminal",
                   "traPYze is a free desktop for your Python scripts: tiles, a settings window per script, "
                   "schedules, a key vault and run history. For scripts you, a colleague or an AI wrote. "
                   "Windows, macOS and Linux."),
    "guide.html": ("The traPYze guide: every screen and option",
                   "Step by step: installing traPYze, making a script traPYze-ready, settings, plans, the vault, "
                   "Ask AI, shared prices and the prompt for AI-written tools."),
    "changelog.html": ("What's new in traPYze",
                       "Every traPYze version and what changed in it, newest first."),
}


def build(out: Path, repo: str) -> list[str]:
    url = site_url(repo)
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(ROOT / "docs" / "images", out / "images")
    for source, name in PAGES.items():
        text = (ROOT / source).read_text(encoding="utf-8").replace("YOUR-GITHUB-NAME/trapyze", repo)
        body = render(fix_links(text, source, repo))
        title, description = TITLES[name]
        here = url if name == "index.html" else url + name
        (out / name).write_text(page(title, description, body, here, repo,
                                     verification() if name == "index.html" else ""), encoding="utf-8")
    today = dt.date.today().isoformat()
    urls = "".join(f"<url><loc>{url if n == 'index.html' else url + n}</loc><lastmod>{today}</lastmod></url>"
                   for n in PAGES.values())
    (out / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n'
                                     f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>\n',
                                     encoding="utf-8")
    (out / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {url}sitemap.xml\n", encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    return sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file())


def main(argv: list[str]) -> int:
    out = Path(argv[0]) if argv else ROOT / "_site"
    repo = argv[1] if len(argv) > 1 else os.environ.get("GITHUB_REPOSITORY", "Kapistyn/trapyze")
    files = build(out, repo)
    print(f"Built {len(files)} files in {out} for {site_url(repo)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

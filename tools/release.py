"""Release helpers for the workflow.

  python tools/release.py check v0.13.0   the tag must match the version in pyproject.toml
  python tools/release.py notes v0.13.0   release notes: that version's part of CHANGELOG.md, plus how to install
"""

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def version() -> str:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]


def notes(v: str, repo: str) -> str:
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    m = re.search(rf"^## \[?{re.escape(v)}\]?[^\n]*\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    body = m.group(1).strip() if m else "See CHANGELOG.md."
    return f"""{body}

### Install or update

**Windows:** download **traPYze-Setup.exe** below and open it. Or paste this into PowerShell:
```
irm https://github.com/{repo}/releases/latest/download/install.ps1 | iex
```
**macOS and Linux:** paste this into a terminal:
```
curl -LsSf https://github.com/{repo}/releases/latest/download/install.sh | sh
```
Already have traPYze? It offers the update by itself (Look and feel, Updates), or run `trapyze update`.
"""


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[0] not in ("check", "notes"):
        print(__doc__)
        return 2
    tag = argv[1].removeprefix("v")
    if argv[0] == "check":
        if tag != version():
            print(f"The tag says {tag} but pyproject.toml says {version()}.")
            return 1
        print(f"Version {tag} matches.")
        return 0
    print(notes(tag, argv[2] if len(argv) > 2 else "YOUR-GITHUB-NAME/trapyze"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

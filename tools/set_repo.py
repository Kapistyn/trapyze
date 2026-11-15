"""Fill in where traPYze lives on GitHub: python tools/set_repo.py owner/name

The release workflow runs this with the repository it runs in, so the installers,
the update check and the links always point to the right place.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLACEHOLDER = "YOUR-GITHUB-NAME/trapyze"
FILES = ["src/trapyze/project.py", "installer/install.ps1", "installer/install.sh",
         "installer/windows/trapyze.iss", "README.md", "CONTRIBUTING.md", "SECURITY.md"]


def main(argv: list[str]) -> int:
    if len(argv) != 1 or not re.fullmatch(r"[A-Za-z0-9-]+/[A-Za-z0-9._-]+", argv[0]):
        print("Usage: python tools/set_repo.py owner/name")
        return 2
    repo = argv[0]
    for name in FILES:
        path = ROOT / name
        if path.exists():
            text = path.read_text(encoding="utf-8")
            if PLACEHOLDER in text:
                path.write_text(text.replace(PLACEHOLDER, repo), encoding="utf-8")
                print(f"  {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

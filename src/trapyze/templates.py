"""Ready-to-change starting points for a new tool, one per shelf kind."""

from __future__ import annotations

import json
import re
from pathlib import Path

KINDS = {
    "collect": "Fetches a file from the web into the shared data folder",
    "analyse": "Reads a CSV and writes a summary of its number columns",
    "share": "Turns a CSV into a neat HTML report",
    "maintain": "Clears out old files in traPYze's outputs or data folder",
    "apps": "A small program with its own window",
}
_FILES = {"apps": "app"}
TEMPLATES = Path(__file__).parent / "resources" / "templates"


def make(scripts: Path, name: str, kind: str, description: str = "") -> Path:
    name = " ".join(str(name or "").split())[:60]
    if not name:
        raise ValueError("Give the tool a name.")
    if kind not in KINDS:
        raise ValueError("Choose what the tool should do.")
    description = " ".join(str(description or "").split())[:200] or KINDS[kind] + "."
    stem = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "new_tool"
    path, n = scripts / f"{stem}.py", 2
    while path.exists():
        path, n = scripts / f"{stem}_{n}.py", n + 1
    text = (TEMPLATES / f"{_FILES.get(kind, kind)}.py").read_text(encoding="utf-8")
    # Values go into TOML strings and a docstring: escape quotes and backslashes the TOML way.
    toml = lambda v: json.dumps(v)[1:-1]  # noqa: E731
    text = text.replace('"{name}"', f'"{toml(name)}"').replace('"{description}"', f'"{toml(description)}"')
    text = text.replace("{name}", name.replace('"""', "'''").replace("\\", "/"))
    scripts.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path

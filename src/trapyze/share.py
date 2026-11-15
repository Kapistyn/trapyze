"""Share a tool as one file: a single script as a .py, a program as a .zip.

What goes in: the script(s) with their label, optionally the presets, and for
a program optionally the shared data its tools read or change. What never
goes in: the vault, .env files, the scripts' run history or anyone's
settings. Before saving, every text file is checked for values from your
vault; if one turns up, nothing is shared and you're told where it is.

The file lands in Outputs\\Shared. The other person imports it with Import.
"""

from __future__ import annotations

import io
import json
import re
import time
import zipfile
from pathlib import Path
from typing import Any

from .freshness import _norm
from .home import PROGRAM_FILE, SKIP_DIRS, Home
from .label import Tool

LOOKS_SECRET = re.compile(r"""(?ix)\b(api[_-]?key|apikey|token|secret|passw(or)?d|pwd)\b\s*[:=]\s*["']([^"'\s]{8,})["']""")
MAX_ZIP = 2 * 1024**3


class ShareProblem(ValueError):
    """Why something can't be shared, in plain words."""


def _toml(value: Any) -> str:
    from .importer import _toml as t
    return t(value)


def presets_lines(presets: dict[str, dict[str, Any]]) -> list[str]:
    lines = ["#", "# [tool.trapyze.presets]"]
    for name, values in presets.items():
        lines.append(f"# {json.dumps(name, ensure_ascii=False)} = {_toml(values)}")
    return lines


def with_presets(source: str, presets: dict[str, dict[str, Any]]) -> str:
    """Add the presets to the script's label (before the closing # ///)."""
    if not presets or "[tool.trapyze.presets]" in source:
        return source
    lines = source.splitlines(keepends=True)
    start = next((i for i, x in enumerate(lines) if x.strip() == "# /// script"), None)
    if start is None:
        return source
    end = next(j for j in range(start + 1, len(lines)) if lines[j].strip() == "# ///")
    newline = "\r\n" if lines[end].endswith("\r\n") else "\n"
    lines[end:end] = [x + newline for x in presets_lines(presets)]
    return "".join(lines)


def _check_text(name: str, text: str, secrets: list[str], found: list[str], notes: list[str]) -> None:
    for value in secrets:
        if len(value) >= 6 and value in text:
            found.append(name)
            return
    m = LOOKS_SECRET.search(text)
    if m:
        line = text[: m.start()].count("\n") + 1
        notes.append(f"{name}, line {line}, looks like it holds a {m.group(1).lower()} written into the code. "
                     "Check it before you send the file on.")


def share(home: Home, tool: Tool, tools: list[Tool], presets: dict[str, dict[str, dict[str, Any]]],
          secrets: list[str], include_presets: bool = True, include_data: bool = False) -> dict[str, Any]:
    target = home.outputs / "Shared"
    target.mkdir(parents=True, exist_ok=True)
    found: list[str] = []
    notes: list[str] = []
    stamp = time.strftime("%Y-%m-%d")
    if not tool.group:
        text = tool.path.read_text(encoding="utf-8", errors="replace")
        if include_presets and presets.get(tool.id):
            text = with_presets(text, presets[tool.id])
        _check_text(tool.path.name, text, secrets, found, notes)
        if found:
            raise ShareProblem(f"{tool.path.name} contains a value from your vault (a key or password). "
                               "Nothing was shared. Take it out of the script; tools get keys from Connections.")
        out = target / f"{tool.id}-{stamp}.py"
        out.write_text(text, encoding="utf-8", newline="")
        if tool.path.with_name(tool.path.name + ".lock").exists():
            notes.append("Its pinned package versions aren't in the single file; the other side gets the newest that fit.")
        if tool.connections:
            notes.append(f"It uses {', '.join(tool.connections)}. The other person adds their own under Connections.")
        return {"path": str(out), "name": out.name, "size": out.stat().st_size, "notes": notes}

    folder = home.scripts / tool.group
    members = [t for t in tools if t.group == tool.group]
    buffer = io.BytesIO()
    size = 0
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        for path in sorted(folder.rglob("*")):
            rel = path.relative_to(folder)
            if any(p in SKIP_DIRS or (p.startswith((".", "_")) and p != PROGRAM_FILE) for p in rel.parts):
                continue
            if not path.is_file() or path.suffix in (".pyc", ".log") or ".env" in path.name.lower() and "example" not in path.name.lower():
                continue
            data = path.read_bytes()
            if path.suffix in (".py", ".md", ".txt", ".json", ".toml", ".cfg", ".ini", ".yaml", ".yml", ".lock"):
                _check_text(f"{tool.group}/{rel.as_posix()}", data.decode("utf-8", errors="replace"), secrets, found, notes)
            z.writestr(f"{tool.group}/{rel.as_posix()}", data)
            size += len(data)
        if include_presets:
            mine = {}
            for t in members:
                if presets.get(t.id):
                    mine[t.path.relative_to(folder).as_posix()] = presets[t.id]
            if mine:
                z.writestr(f"{tool.group}/presets.json", json.dumps(mine, indent=1, ensure_ascii=False))
        if include_data:
            shared: set[Path] = set()
            for t in members:
                for raw in list(t.reads) + list(t.writes):
                    p = _norm(home, raw)
                    if p.exists() and p.is_file() and home.data.resolve() in p.parents:
                        shared.add(p)
            for p in sorted(shared):
                size += p.stat().st_size
                if size > MAX_ZIP:
                    raise ShareProblem("With the data it would be over 2 GB. Share it without the data.")
                z.write(p, f"{tool.group}/data/{p.name}")
    if found:
        raise ShareProblem(f"These files contain a value from your vault (a key or password): {', '.join(found)}. "
                           "Nothing was shared. Take the value out; tools get keys from Connections.")
    out = target / f"{tool.group}-{stamp}.zip"
    out.write_bytes(buffer.getvalue())
    used = sorted({c for t in members for c in t.connections})
    if used:
        notes.append(f"It uses {', '.join(used)}. The other person adds their own under Connections.")
    return {"path": str(out), "name": out.name, "size": out.stat().st_size, "notes": notes}

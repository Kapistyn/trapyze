"""The scripts folder, as the user sees it: every program and script, and what each file is.

A file with a traPYze label is a tool (with a tile or hidden); a file without one is a helper that
the program uses. Any file that can run can be given a label, and with it a tile.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .home import Home, _program_files
from .importer import PyInfo, _pretty, add_label, read_options, third_party


class ScriptFileError(Exception):
    pass


def listing(home: Home) -> list[dict[str, Any]]:
    tools, problems = home.tools()
    by_path = {t.path.resolve(): t for t in tools}
    broken = {p.path.resolve(): p.message for p in problems}
    out: list[dict[str, Any]] = []

    def entry(path: Path, base: Path) -> dict[str, Any]:
        rel = path.relative_to(home.scripts).as_posix()
        size = path.stat().st_size
        t = by_path.get(path.resolve())
        if t is not None:
            status, tid, name = ("hidden" if t.hidden else "tile"), t.id, t.name
        elif path.resolve() in broken:
            status, tid, name = "broken", "", ""
        else:
            status, tid, name = "helper", "", ""
        return {"file": path.relative_to(base).as_posix(), "rel": rel, "status": status, "tool": tid, "name": name,
                "bytes": size, "modified": path.stat().st_mtime, "problem": broken.get(path.resolve(), "")}

    if not home.scripts.is_dir():
        return out
    loose = [entry(p, home.scripts) for p in sorted(home.scripts.glob("*.py")) if not p.name.startswith(("_", "."))]
    out.append({"folder": "", "name": "Single scripts", "program": False, "files": loose})
    programs = home.programs()
    for folder in sorted(p for p in home.scripts.iterdir() if p.is_dir() and not p.name.startswith(("_", "."))):
        files = [entry(p, folder) for p in sorted(_program_files(folder))]
        out.append({"folder": folder.name, "name": (programs.get(folder.name) or {}).get("name", folder.name), "program": True, "files": files})
    return out


def make_tool(home: Home, rel: str) -> str:
    """Give a script of a program a label, so it becomes a tool with its own tile."""
    path = (home.scripts / rel).resolve()
    if home.scripts.resolve() not in path.parents or path.suffix != ".py" or not path.is_file():
        raise ScriptFileError("That isn't a script in the scripts folder.")
    source = path.read_text(encoding="utf-8", errors="replace")
    if "[tool.trapyze]" in source:
        raise ScriptFileError("It already has a label.")
    info = PyInfo(rel, source)
    if info.error:
        raise ScriptFileError(f"It can't be read as Python ({info.error}).")
    folder = path.parent
    local = {p.stem for p in folder.rglob("*.py")} | {p.name for p in folder.iterdir() if p.is_dir()}
    settings, _ = read_options(info)
    label = {"name": _pretty(path.stem), "description": (info.docstring.splitlines()[0].strip() if info.docstring else "")[:160],
             "icon": "terminal", "color": "blue", "settings": settings}
    path.write_text(add_label(source, label, third_party(info.imports, local)), encoding="utf-8")
    return label["name"]

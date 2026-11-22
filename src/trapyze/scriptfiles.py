"""The scripts folder, as the user sees it: every program and script, and what each file is.

A file with a traPYze label is a tool (with a tile or hidden); a file without one is a helper that
the program uses. Any file that can run can be given a label, and with it a tile.
"""
from __future__ import annotations

import datetime as dt
import shutil
from pathlib import Path
from typing import Any

from .home import Home, _program_files, program_tool_id
from .label import LabelError, find_block, read_tool
from .importer import PyInfo, _pretty, add_label, imports_through_helpers, read_options, third_party


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
    path.write_text(add_label(source, label, third_party(info.imports | imports_through_helpers(path, source), local)), encoding="utf-8")
    return label["name"]


# Updating a program from outside ------------------------------------------------------
_SKIP_DIRS = {"__pycache__", ".venv", "venv", ".git", "node_modules", ".trapyze"}


def _source_files(source: Path) -> dict[str, Path]:
    """The scripts in a file or folder the user points at, by relative name."""
    if source.is_file():
        return {source.name: source} if source.suffix == ".py" else {}
    out: dict[str, Path] = {}
    for p in sorted(source.rglob("*.py")):
        rel = p.relative_to(source)
        if any(part in _SKIP_DIRS or part.startswith(".") for part in rel.parts[:-1]) or p.name.startswith("."):
            continue
        out[rel.as_posix()] = p
    return out


def _match(folder: Path, rel: str, taken: set[str]) -> str:
    """Where in the program a script from outside belongs: same place, else the one file with that name, else new."""
    if (folder / rel).is_file():
        return rel
    name = Path(rel).name
    same = [p.relative_to(folder).as_posix() for p in folder.rglob(name)
            if p.is_file() and not any(x in _SKIP_DIRS for x in p.relative_to(folder).parts)]
    same = [s for s in same if s not in taken]
    return same[0] if len(same) == 1 else Path(rel).name if "/" not in rel else rel


def _label_of(text: str) -> tuple[dict | None, list[str] | None]:
    try:
        meta = find_block(text)
    except LabelError:
        return None, None
    if not meta:
        return None, None
    return (meta.get("tool") or {}).get("trapyze"), meta.get("dependencies")


def _merged(old: str, new: str) -> tuple[str, str]:
    """The text to write for a script that is replaced by one from outside, and what happens to its label."""
    old_label, old_deps = _label_of(old)
    new_label, new_deps = _label_of(new)
    if new_label:
        return new, "has its own label"
    if old_label:
        try:
            return add_label(new, old_label, old_deps or new_deps), "keeps its tile"
        except (LabelError, StopIteration):
            return new, "label lost"
    return new, "no label"


def update_plan(home: Home, folder_name: str, source: str) -> dict[str, Any]:
    folder = (home.scripts / folder_name).resolve()
    if not folder_name or home.scripts.resolve() not in folder.parents or not folder.is_dir():
        raise ScriptFileError("That program isn't in the scripts folder.")
    src = Path(source.strip().strip('"')).expanduser()
    if not src.exists():
        raise ScriptFileError("traPYze can't find that file or folder.")
    if home.scripts.resolve() in src.resolve().parents or src.resolve() == home.scripts.resolve():
        raise ScriptFileError("That is already inside traPYze's scripts folder.")
    files = _source_files(src)
    if not files:
        raise ScriptFileError("There are no Python scripts there.")
    taken: set[str] = set()
    items = []
    for rel, path in files.items():
        dest_rel = _match(folder, rel, taken)
        taken.add(dest_rel)
        dest = folder / dest_rel
        new = path.read_text(encoding="utf-8", errors="replace")
        if dest.is_file():
            text, label = _merged(dest.read_text(encoding="utf-8", errors="replace"), new)
            state = "same" if text == dest.read_text(encoding="utf-8", errors="replace") else "changed"
        else:
            state, label = "new", ("has its own label" if _label_of(new)[0] else "no label")
        items.append({"from": rel, "to": dest_rel, "state": state, "label": label, "source": str(path)})
    return {"folder": folder_name, "source": str(src), "items": items}


def update_apply(home: Home, folder_name: str, source: str, only: list[str] | None = None) -> dict[str, Any]:
    """Copy scripts from outside into a program. What they replace is kept in scripts/_replaced; the tile survives."""
    plan = update_plan(home, folder_name, source)
    folder = home.scripts / folder_name
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = home.scripts / "_replaced" / f"{folder_name}-update-{stamp}"
    report: dict[str, Any] = {"updated": [], "added": [], "unchanged": [], "tools": [], "notes": []}
    for item in plan["items"]:
        if item["state"] == "same" or (only is not None and item["to"] not in only):
            report["unchanged"].append(item["to"])
            continue
        dest = folder / item["to"]
        new = Path(item["source"]).read_text(encoding="utf-8", errors="replace")
        if dest.is_file():
            new, _ = _merged(dest.read_text(encoding="utf-8", errors="replace"), new)
            (backup / item["to"]).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dest, backup / item["to"])
            report["updated"].append(item["to"])
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            report["added"].append(item["to"])
        dest.write_text(new, encoding="utf-8", newline="")
        if "[tool.trapyze]" in new:
            try:
                read_tool(dest, program_tool_id(folder, dest), folder_name)
                report["tools"].append(item["to"])
            except LabelError as exc:
                report["notes"].append(f"{item['to']}: the label needs a look: {exc}")
    if report["updated"]:
        report["backup"] = f"scripts/_replaced/{backup.name}"
    return report

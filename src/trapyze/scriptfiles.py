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


def update_plan(home: Home, folder_name: str, source: str, remap: dict[str, str] | None = None) -> dict[str, Any]:
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
        chosen = (remap or {}).get(rel)
        dest_rel = chosen if chosen and (folder / chosen).is_file() and (folder / chosen).resolve().parent.is_relative_to(folder.resolve()) \
            else _match(folder, rel, taken)
        taken.add(dest_rel)
        dest = folder / dest_rel
        new = path.read_text(encoding="utf-8", errors="replace")
        extra: dict[str, Any] = {}
        if dest.is_file():
            old = dest.read_text(encoding="utf-8", errors="replace")
            text, label = _merged(old, new)
            state = "same" if text == old else "changed"
            if state == "changed":
                d = compare_texts(old, new)
                extra["diff"] = {"added": d["added"], "removed": d["removed"], "newer": path.stat().st_mtime > dest.stat().st_mtime}
        else:
            state, label = "new", ("has its own label" if _label_of(new)[0] else "no label")
            similar = [f for f in looks_like(home, rel) if f["program"] == folder_name]
            if similar:
                extra["looks_like"] = similar
        items.append({"from": rel, "to": dest_rel, "state": state, "label": label, "source": str(path), **extra})
    return {"folder": folder_name, "source": str(src), "items": items}


def update_apply(home: Home, folder_name: str, source: str, only: list[str] | None = None,
                 remap: dict[str, str] | None = None) -> dict[str, Any]:
    """Copy scripts from outside into a program. What they replace is kept in scripts/_replaced; the tile survives."""
    plan = update_plan(home, folder_name, source, remap)
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


# Organising: move, rename, group, compare -----------------------------------------------
import difflib
import hashlib
import json
import re

from .home import PROGRAM_FILE


def _tool_id(home: Home, path: Path) -> str | None:
    """The id this file has (or would have) as a tool, from where it sits."""
    try:
        rel = path.relative_to(home.scripts)
    except ValueError:
        return None
    if len(rel.parts) == 1:
        return path.stem
    return program_tool_id(home.scripts / rel.parts[0], path)


def _ids_under(home: Home, paths: list[Path]) -> dict[Path, str]:
    return {p: i for p in paths if "[tool.trapyze]" in p.read_text(encoding="utf-8", errors="replace") and (i := _tool_id(home, p))}


def _clean_name(name: str, suffix: str = ".py") -> str:
    name = name.strip().strip('"')
    if suffix and not name.lower().endswith(suffix):
        name += suffix
    stem = name[: -len(suffix)] if suffix else name
    if not stem or re.search(r'[\\/:*?"<>|]', stem) or stem.startswith((".", "_")) or stem != stem.strip():
        raise ScriptFileError("Use letters, digits, spaces, dashes and underscores, and don't start with a dot or an underscore.")
    return name


def _in_scripts(home: Home, rel: str) -> Path:
    path = home.scripts / rel
    if (home.scripts.resolve() not in path.resolve().parents or not path.exists()
            or any(part.startswith("_") or part == ".." for part in Path(rel).parts)):
        raise ScriptFileError("That isn't in the scripts folder.")
    return path


def _program_json(folder: Path) -> dict[str, Any]:
    try:
        return json.loads((folder / PROGRAM_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_program_json(folder: Path, info: dict[str, Any]) -> None:
    (folder / PROGRAM_FILE).write_text(json.dumps(info, indent=1), encoding="utf-8")


def _carry_hidden(old_folder: Path | None, new_folder: Path | None, mapping: dict[str, str]) -> None:
    """Tiles that were hidden stay hidden after they move."""
    if old_folder is not None and old_folder.is_dir():
        info = _program_json(old_folder)
        if info.get("hidden"):
            info["hidden"] = [h for h in info["hidden"] if h not in mapping or new_folder is None]
            _save_program_json(old_folder, info)


def _lock_of(path: Path) -> Path:
    return path.with_name(path.name + ".lock")


def move_file(home: Home, rel: str, to_program: str, vault: Any = None) -> dict[str, Any]:
    """Move one script into a program (or out of one, to the single scripts)."""
    src = _in_scripts(home, rel)
    if not src.is_file() or src.suffix != ".py":
        raise ScriptFileError("Only a script can be moved here.")
    if to_program:
        target = (home.scripts / to_program)
        if not target.is_dir() or to_program.startswith(("_", ".")):
            raise ScriptFileError("That program isn't there.")
    else:
        target = home.scripts
    dest = target / src.name
    if dest.exists():
        raise ScriptFileError(f"“{src.name}” already exists there. Rename one of them first.")
    old_folder = src.parent if src.parent != home.scripts else None
    before = _ids_under(home, [src])
    local_old = {p.stem for p in src.parent.glob("*.py")} - {src.stem} if old_folder is not None else set()
    shutil.move(str(src), str(dest))
    if _lock_of(src).exists():
        shutil.move(str(_lock_of(src)), str(_lock_of(dest)))
    after = _ids_under(home, [dest])
    mapping = {before[src]: after[dest]} if src in before and dest in after else {}
    _carry_hidden(old_folder, target if target != home.scripts else None, mapping)
    from .relocate import retarget
    notes = retarget(home, mapping, vault)
    try:
        imported = PyInfo(dest.name, dest.read_text(encoding="utf-8", errors="replace")).imports
    except Exception:
        imported = set()
    gone = sorted(local_old & imported)
    if gone:
        notes.append(f"It uses {', '.join(g + '.py' for g in gone)} from its old program. Move that file along too, or the tool will not start.")
    return {"to": dest.relative_to(home.scripts).as_posix(), "mapping": mapping, "notes": notes}


def rename_file(home: Home, rel: str, new_name: str, vault: Any = None) -> dict[str, Any]:
    src = _in_scripts(home, rel)
    if not src.is_file() or src.suffix != ".py":
        raise ScriptFileError("Only a script can be renamed here.")
    name = _clean_name(new_name)
    dest = src.with_name(name)
    if dest.exists() and dest != src:
        raise ScriptFileError(f"“{name}” already exists in that folder.")
    before = _ids_under(home, [src])
    src.rename(dest)
    if _lock_of(src).exists():
        _lock_of(src).rename(_lock_of(dest))
    after = _ids_under(home, [dest])
    mapping = {before[src]: after[dest]} if src in before and dest in after else {}
    from .relocate import retarget
    notes = retarget(home, mapping, vault)
    others = [p.name for p in src.parent.glob("*.py") if p != dest and src.stem in p.read_text(encoding="utf-8", errors="replace")]
    if others:
        notes.append(f"{', '.join(others[:3])} mention the old name. If they import it, change that too.")
    return {"to": dest.relative_to(home.scripts).as_posix(), "mapping": mapping, "notes": notes}


def _slug(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", name.strip()).strip("_").lower()
    if not slug:
        raise ScriptFileError("Give the program a name.")
    return slug


def rename_program(home: Home, folder_name: str, new_name: str, vault: Any = None) -> dict[str, Any]:
    folder = _in_scripts(home, folder_name)
    if not folder.is_dir() or folder.parent.resolve() != home.scripts.resolve():
        raise ScriptFileError("That isn't a program.")
    slug = _slug(new_name)
    dest = home.scripts / slug
    files = [p for p in _program_files(folder)]
    before = _ids_under(home, files)
    if slug != folder.name:
        if dest.exists():
            raise ScriptFileError(f"There is already a program called “{slug}”.")
        folder.rename(dest)
    renamed: dict[Path, Path] = {}
    main = dest / f"{folder.name}.py"
    if slug != folder.name and main.is_file() and not (dest / f"{slug}.py").exists():
        renamed[folder / main.name] = dest / f"{slug}.py"
        main.rename(dest / f"{slug}.py")
        if _lock_of(main).exists():
            _lock_of(main).rename(_lock_of(dest / f"{slug}.py"))
    info = _program_json(dest)
    info["name"] = new_name.strip()
    _save_program_json(dest, info)
    mapping = {}
    for p, old in before.items():
        newp = renamed.get(p) or dest / p.relative_to(folder)
        new = program_tool_id(dest, newp)
        mapping[old] = new
    if info.get("hidden"):
        info["hidden"] = [mapping.get(h, h) for h in info["hidden"]]
        _save_program_json(dest, info)
    from .relocate import retarget
    return {"folder": slug, "mapping": mapping, "notes": retarget(home, mapping, vault)}


def new_program(home: Home, name: str, rels: list[str], vault: Any = None) -> dict[str, Any]:
    """Put loose scripts together in a new program folder."""
    slug = _slug(name)
    dest = home.scripts / slug
    if dest.exists():
        raise ScriptFileError(f"There is already a program called “{slug}”.")
    srcs = []
    for rel in rels:
        p = _in_scripts(home, rel)
        if not p.is_file() or p.suffix != ".py" or p.parent.resolve() != home.scripts.resolve():
            raise ScriptFileError("Only single scripts can be put together.")
        srcs.append(p)
    if not srcs:
        raise ScriptFileError("Choose at least one script.")
    before = _ids_under(home, srcs)
    dest.mkdir()
    _save_program_json(dest, {"name": name.strip()})
    mapping, notes = {}, []
    for p in srcs:
        target = dest / p.name
        shutil.move(str(p), str(target))
        if _lock_of(p).exists():
            shutil.move(str(_lock_of(p)), str(_lock_of(target)))
        if p in before:
            mapping[before[p]] = program_tool_id(dest, target)
    from .relocate import retarget
    notes += retarget(home, mapping, vault)
    return {"folder": slug, "mapping": mapping, "notes": notes}


def discard_file(home: Home, rel: str, bin_: Any) -> str:
    """A script nobody wants any more goes to the bin (30 days)."""
    src = _in_scripts(home, rel)
    if not src.is_file() or src.suffix != ".py":
        raise ScriptFileError("Only a script can be removed here.")
    return bin_.put(Path(rel).as_posix(), src.name, "tool")


# Same file, different copy ---------------------------------------------------------------
_BLOCK = re.compile(r"^# /// script\n(?:#.*\n?)*?# ///\n?", re.M)
_TAIL = re.compile(r"(\(\d+\)|[ _\-]*copy|[ _\-]*v\d+|[ _\-]*final|[ _\-]*new|[ _\-]*old|[ _\-]*\d+)$", re.I)


def norm_name(stem: str) -> str:
    s = stem.lower().strip()
    for _ in range(3):
        n = _TAIL.sub("", s).strip(" _-")
        if n == s or not n:
            break
        s = n
    return re.sub(r"[^a-z0-9]+", "", s)


def _body(text: str) -> str:
    return "\n".join(line.rstrip() for line in _BLOCK.sub("", text).replace("\r\n", "\n").splitlines()).strip()


def _all_scripts(home: Home) -> list[Path]:
    out = [p for p in home.scripts.glob("*.py") if not p.name.startswith(("_", "."))]
    for folder in home.scripts.iterdir() if home.scripts.is_dir() else []:
        if folder.is_dir() and not folder.name.startswith(("_", ".")):
            out += list(_program_files(folder))
    return sorted(out)


def _facts(home: Home, p: Path) -> dict[str, Any]:
    st = p.stat()
    return {"rel": p.relative_to(home.scripts).as_posix(), "name": p.name, "bytes": st.st_size, "modified": st.st_mtime,
            "program": p.relative_to(home.scripts).parts[0] if len(p.relative_to(home.scripts).parts) > 1 else ""}


def compare_texts(old: str, new: str) -> dict[str, Any]:
    a, b = _body(old).splitlines(), _body(new).splitlines()
    added = removed = 0
    for line in difflib.unified_diff(a, b, lineterm="", n=0):
        if line.startswith("+") and not line.startswith("+++"):
            added += 1
        elif line.startswith("-") and not line.startswith("---"):
            removed += 1
    return {"added": added, "removed": removed, "same": a == b, "lines_old": len(a), "lines_new": len(b)}


def compare(home: Home, rel: str, other: str) -> dict[str, Any]:
    """How a script differs from another one: another file in traPYze, or one outside it (a full path)."""
    a = _in_scripts(home, rel)
    try:
        b = _in_scripts(home, other)
    except ScriptFileError:
        b = Path(other.strip().strip('"')).expanduser()
        if not b.is_file():
            raise ScriptFileError("traPYze can't find that file.") from None
    out = compare_texts(a.read_text(encoding="utf-8", errors="replace"), b.read_text(encoding="utf-8", errors="replace"))
    out.update(a=_facts(home, a), newer="other" if b.stat().st_mtime > a.stat().st_mtime else "this")
    return out


def duplicates(home: Home, limit: int = 400) -> list[dict[str, Any]]:
    """Scripts that are the same, nearly the same, or share a name across the scripts folder."""
    files = [p for p in _all_scripts(home) if p.stat().st_size <= 400_000][:limit]
    texts = {p: _body(p.read_text(encoding="utf-8", errors="replace")) for p in files}
    hashes = {p: hashlib.sha1(texts[p].encode("utf-8", "replace")).hexdigest() for p in files}
    pairs = []
    for i, p in enumerate(files):
        for q in files[i + 1:]:
            if hashes[p] == hashes[q]:
                kind, ratio = "identical", 1.0
            else:
                same_name = norm_name(p.stem) == norm_name(q.stem)
                size_close = min(len(texts[p]), len(texts[q])) >= 0.8 * max(len(texts[p]), len(texts[q]), 1)
                if not (same_name or size_close):
                    continue
                sm = difflib.SequenceMatcher(None, texts[p], texts[q], autojunk=False)
                if not same_name and (sm.real_quick_ratio() < 0.85 or sm.quick_ratio() < 0.85):
                    continue
                ratio = sm.ratio()
                if ratio >= 0.9:
                    kind = "nearly the same"
                elif same_name:
                    kind = "same name"
                else:
                    continue
            a, b = _facts(home, p), _facts(home, q)
            pairs.append({"kind": kind, "ratio": round(ratio, 3), "a": a, "b": b, "newer": "a" if a["modified"] >= b["modified"] else "b"})
    order = {"identical": 0, "nearly the same": 1, "same name": 2}
    pairs.sort(key=lambda x: (order[x["kind"]], -x["ratio"]))
    return pairs[:100]


def looks_like(home: Home, incoming_name: str, exclude: set[str] | None = None) -> list[dict[str, Any]]:
    """Existing scripts that an incoming file name looks like a new version of."""
    key = norm_name(Path(incoming_name).stem)
    if not key:
        return []
    return [_facts(home, p) for p in _all_scripts(home) if norm_name(p.stem) == key and p.relative_to(home.scripts).as_posix() not in (exclude or set())]

"""The import wizard: bring a folder (or one script) into traPYze.

It reads everything first and proposes where each file goes:

- programs (files you run) become tools, with a label read from their own
  options (argparse), dependencies and description
- helper files (imported by the others) stay with the program, without a tile
- data files go to the shared data folder (or stay with the program)
- a .env file is offered to the vault, never copied as plain text
- notes and read-me files stay with the program
- backups, logs, virtual environments and caches are left out

Where the code looks for a data file next to itself, it proposes a change to
the shared data folder, line by line, for you to approve. The original folder
is never changed; traPYze works on a copy.
"""

from __future__ import annotations

import ast
import datetime as dt
import fnmatch
import json
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Any

from .home import PROGRAM_FILE, SKIP_DIRS, Home, program_tool_id
from .label import LabelError, find_block, read_tool

DATA_EXT = {".sqlite", ".sqlite3", ".db", ".duckdb", ".csv", ".tsv", ".xlsx", ".xls", ".xlsm", ".parquet", ".feather",
            ".h5", ".hdf5", ".pkl", ".pickle"}
DOC_EXT = {".md", ".txt", ".rst", ".pdf", ".html"}
SKIP_FILES = ("*.bak", "*.bak_*", "*.bak.*", "*.log", "*.pyc", "*.pyo", "*.tmp", "~$*", ".DS_Store", "Thumbs.db",
              "*.swp", "desktop.ini")
RUNNERS = ("run_*.bat", "run_*.sh", "run_*.cmd", "run_*.ps1", "start*.bat", "*.command")
MAX_FILES = 2000
# Import names that differ from the package to install.
PACKAGES = {"bs4": "beautifulsoup4", "sklearn": "scikit-learn", "yaml": "pyyaml", "dotenv": "python-dotenv",
            "PIL": "Pillow", "cv2": "opencv-python", "dateutil": "python-dateutil", "win32com": "pywin32",
            "win32api": "pywin32", "Crypto": "pycryptodome", "telegram": "python-telegram-bot", "docx": "python-docx",
            "pptx": "python-pptx", "attr": "attrs", "google.cloud": "google-cloud", "ib_insync": "ib_insync",
            "talib": "TA-Lib", "fitz": "PyMuPDF", "serial": "pyserial", "usb": "pyusb", "magic": "python-magic"}
HELPER_NAME = "_tz_data"
HELPER_CODE = (
    f"def {HELPER_NAME}(name):  # added by traPYze: the shared data folder (next to this file outside traPYze)\n"
    "    import os, pathlib\n"
    "    return pathlib.Path(os.environ.get(\"TRAPYZE_DATA_DIR\") or os.path.dirname(os.path.abspath(__file__)), name)\n\n\n"
)


class ImportProblem(ValueError):
    """Something about the folder that stops the import, in plain words."""


def _skip_file(name: str) -> bool:
    return any(fnmatch.fnmatch(name, pat) for pat in SKIP_FILES)


def _is_env(name: str) -> bool:
    low = name.lower()
    return (low == ".env" or low.endswith(".env") or low.startswith(".env.")) and not any(
        w in low for w in ("example", "sample", "template"))


def _pretty(stem: str) -> str:
    """"price_db" -> "Price db", "MarketEvaluator" -> "Market Evaluator" (capitals in names are kept)."""
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", stem).replace("_", " ").replace("-", " ")
    text = " ".join(text.split())
    return (text[0].upper() + text[1:]) if text else stem


def _safe_folder(name: str) -> str:
    cleaned = re.sub(r"[^\w.-]+", "_", name).strip("._") or "program"
    return cleaned[:60]


# Reading Python files ----------------------------------------------------------
class PyInfo:
    def __init__(self, rel: str, source: str):
        self.rel = rel
        self.source = source
        self.tree: ast.Module | None = None
        self.error = ""
        try:
            self.tree = ast.parse(source)
        except SyntaxError as exc:
            self.error = f"line {exc.lineno}: {exc.msg}"
        self.imports: set[str] = set()
        self.has_main = False
        self.uses_argparse = False
        self.docstring = ""
        if self.tree is None:
            return
        self.docstring = (ast.get_docstring(self.tree) or "").strip()
        self.refs: set[str] = set()  # other scripts it starts itself: "dashboard.py", "-m dashboard"
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and len(node.value) < 300:
                m = re.search(r"([\w.-]+)\.py$", node.value.strip())
                if m:
                    self.refs.add(m.group(1).split(".")[-1] if m.group(1).count(".") else m.group(1))
            elif isinstance(node, ast.List) and len(node.elts) >= 2:
                values = [e.value for e in node.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
                for a, b in zip(values, values[1:]):
                    if a == "-m":
                        self.refs.add(b.split(".")[-1])
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                self.imports.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                self.imports.add(node.module)
            elif isinstance(node, ast.ImportFrom) and node.level:
                self.imports.update(f".{a.name}" for a in node.names)
                if node.module:
                    self.imports.add("." + node.module)
            elif isinstance(node, ast.Attribute) and node.attr == "ArgumentParser":
                self.uses_argparse = True
        for node in self.tree.body:
            if isinstance(node, ast.If) and _is_main_test(node.test):
                self.has_main = True

    @property
    def label(self) -> dict[str, Any] | None:
        try:
            meta = find_block(self.source)
        except LabelError:
            return None
        return meta


MAIN_NAMES = {"main", "app", "run", "cli", "start", "__main__", "launcher", "orchestrator", "manage"}


def find_conductor(py: dict[Path, "PyInfo"], rels: dict[Path, str], folder_name: str,
                   candidates: set[Path] | None = None) -> dict[str, Any]:
    """Which file starts the program, which files it uses, and which other files can also run.

    The conductor is the runnable file that reaches most of the program (through imports,
    also inside functions, and scripts it starts itself), with a bonus for names like main,
    run or app, or the folder's own name. What it reaches are helpers; other runnable
    files are extras (hidden, one click to give them a tile)."""
    by_stem: dict[str, list[Path]] = {}
    for p in py:
        by_stem.setdefault(p.stem, []).append(p)
        if p.name == "__init__.py":
            by_stem.setdefault(p.parent.name, []).append(p)

    def resolve(name: str, near: Path) -> Path | None:
        found = by_stem.get(name) or []
        if not found:
            return None
        same = [f for f in found if f.parent == near.parent]
        return (same or found)[0]

    edges: dict[Path, set[Path]] = {}
    for p, info in py.items():
        targets: set[Path] = set()
        for name in info.imports:
            for part in name.lstrip(".").split("."):
                t = resolve(part, p)
                if t is not None and t != p:
                    targets.add(t)
        for ref in info.refs:
            t = resolve(ref, p)
            if t is not None and t != p:
                targets.add(t)
        edges[p] = targets

    def reach(start: Path) -> set[Path]:
        seen: set[Path] = set()
        todo = list(edges.get(start, ()))
        while todo:
            q = todo.pop()
            if q in seen or q == start:
                continue
            seen.add(q)
            todo += list(edges.get(q, ()))
        return seen

    def runnable(p: Path) -> bool:
        info = py[p]
        if info.error or p.name == "__init__.py" or p.name.startswith("test_") or p.stem.endswith("_test") \
                or "/tests/" in "/" + rels[p] or "/test/" in "/" + rels[p]:
            return False
        has_label = "[tool.trapyze]" in info.source
        return has_label or info.has_main or info.uses_argparse

    pool = [p for p in py if (candidates is None or p in candidates) and runnable(p)]
    if not pool:
        return {"main": None, "helpers": set(), "extras": [], "reach": {}}
    folder_key = re.sub(r"[\W_]+", "", folder_name.lower())

    def score(p: Path) -> tuple:
        stem = p.stem.lower()
        bonus = 0
        if stem in MAIN_NAMES:
            bonus += 1000
        if re.sub(r"[\W_]+", "", stem) == folder_key:
            bonus += 900
        if stem.startswith(("run_", "main_", "start_")):
            bonus += 40
        if py[p].uses_argparse:
            bonus += 5
        depth = rels[p].count("/")
        return (len(reach(p)) + bonus, -depth, -len(p.stem))
    main = max(pool, key=score)
    helpers = reach(main)
    # Files other files import are helpers too (of the extras, say), unless they're the main.
    for p, targets in edges.items():
        helpers |= {t for t in targets if t != main}
    extras = [p for p in pool if p != main and p not in helpers]
    # An extra that the others merely import from (like a library with a test block) stays a helper.
    return {"main": main, "helpers": helpers - {main}, "extras": sorted(extras, key=lambda p: rels[p]),
            "reach": {p: reach(p) for p in pool}}


def _is_main_test(test: ast.AST) -> bool:
    if isinstance(test, ast.Compare) and len(test.ops) == 1 and isinstance(test.ops[0], ast.Eq):
        sides = [test.left, *test.comparators]
        names = [s.id for s in sides if isinstance(s, ast.Name)]
        consts = [s.value for s in sides if isinstance(s, ast.Constant)]
        return names == ["__name__"] and consts == ["__main__"]
    return False


def _literal(node: ast.AST | None) -> Any:
    if node is None:
        return None
    try:
        return ast.literal_eval(node)
    except (ValueError, SyntaxError, TypeError):
        return _NOT_LITERAL


_NOT_LITERAL = object()


def read_options(info: PyInfo) -> tuple[list[dict[str, Any]], list[str]]:
    """Settings from argparse calls, and notes about what couldn't be read."""
    if info.tree is None:
        return [], []
    notes: list[str] = []
    parsers: dict[str, str | None] = {}  # variable -> command name (None for the main parser)
    subparser_holders: set[str] = set()
    commands: list[str] = []
    for node in ast.walk(info.tree):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        var, call = node.targets[0].id, node.value
        if not isinstance(call, ast.Call) or not isinstance(call.func, (ast.Attribute, ast.Name)):
            continue
        fname = call.func.attr if isinstance(call.func, ast.Attribute) else call.func.id
        if fname == "ArgumentParser":
            parsers[var] = None
        elif fname == "add_subparsers":
            subparser_holders.add(var)
        elif fname == "add_parser" and isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name) \
                and call.func.value.id in subparser_holders and call.args and isinstance(call.args[0], ast.Constant):
            parsers[var] = str(call.args[0].value)
            commands.append(parsers[var])
    # Sub-commands created without keeping the parser in a variable still count as commands.
    for node in ast.walk(info.tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "add_parser" \
                and isinstance(node.func.value, ast.Name) and node.func.value.id in subparser_holders \
                and node.args and isinstance(node.args[0], ast.Constant) and str(node.args[0].value) not in commands:
            commands.append(str(node.args[0].value))
    settings: list[dict[str, Any]] = []
    if commands:
        settings.append({"key": "command", "label": "What to do", "type": "choice", "options": commands,
                         "default": commands[0], "positional": True,
                         "help": "The script's own commands."})
    by_key: dict[str, dict[str, Any]] = {}
    for node in ast.walk(info.tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "add_argument"):
            continue
        owner = node.func.value.id if isinstance(node.func.value, ast.Name) else None
        if owner is not None and owner not in parsers:
            continue  # an argument group or something we can't follow
        command = parsers.get(owner) if owner else None
        names = [_literal(a) for a in node.args]
        if not names or any(not isinstance(n, str) for n in names):
            continue
        kw = {k.arg: k.value for k in node.keywords if k.arg}
        flags = [n for n in names if n.startswith("-")]
        if names[0] in ("-h", "--help"):
            continue
        dest = _literal(kw.get("dest")) if "dest" in kw else None
        if not isinstance(dest, str):
            longs = [f for f in flags if f.startswith("--")]
            dest = (longs[0] if longs else flags[0] if flags else names[0]).lstrip("-").replace("-", "_")
        action = _literal(kw.get("action")) if "action" in kw else None
        nargs = _literal(kw.get("nargs")) if "nargs" in kw else None
        if action in ("append", "count", "extend", "version") or nargs in ("+", "*") or isinstance(nargs, int) and nargs > 1:
            notes.append(f"Left out {flags[0] if flags else dest}: traPYze's settings can't give it more than one value yet.")
            continue
        help_text = _literal(kw.get("help")) if "help" in kw else ""
        help_text = help_text if isinstance(help_text, str) else ""
        help_text = re.sub(r"\s+", " ", help_text.replace("%(default)s", "{default}")).strip()
        setting: dict[str, Any] = {"key": re.sub(r"\W", "_", dest), "label": _pretty(dest)}
        if action in ("store_true", "store_false"):
            setting.update(type="bool", default=False, switch=True)
            if action == "store_false":
                setting["label"] = f"Turn off: {_pretty(dest).lower()}"
        else:
            choices = _literal(kw.get("choices")) if "choices" in kw else None
            typ = kw.get("type")
            typ_name = typ.id if isinstance(typ, ast.Name) else typ.attr if isinstance(typ, ast.Attribute) else None
            default = _literal(kw.get("default")) if "default" in kw else None
            if default is _NOT_LITERAL:
                default = None
                notes.append(f"{flags[0] if flags else dest}: its default is worked out by the script, so it starts empty here.")
            if isinstance(choices, (list, tuple)) and choices and all(isinstance(c, (str, int, float)) for c in choices):
                setting.update(type="choice", options=[str(c) for c in choices])
                default = str(default) if default is not None else str(choices[0])
            elif typ_name == "int":
                setting["type"] = "int"
            elif typ_name == "float":
                setting["type"] = "float"
            elif re.search(r"(^|_)(dir|folder|directory)$", dest):
                setting["type"] = "folder"
            elif re.search(r"(^|_)(file|path)$", dest) or typ_name in ("Path", "FileType"):
                setting["type"] = "file"
            else:
                setting["type"] = "text"
            if default is not None:
                if setting["type"] == "int" and isinstance(default, (int, float)) and not isinstance(default, bool):
                    default = int(default)
                elif setting["type"] == "float" and isinstance(default, (int, float)):
                    default = float(default)
                elif setting["type"] in ("text", "file", "folder"):
                    default = str(default)
                setting["default"] = default
            required = _literal(kw.get("required")) if "required" in kw else False
            if required is True or (not flags and default is None and setting["type"] != "choice"):
                setting["required"] = True
        if help_text:
            setting["help"] = help_text.replace("{default}", str(setting.get("default", "")))
        if flags:
            longs = [f for f in flags if f.startswith("--")]
            setting["flag"] = longs[0] if longs else flags[0]
        else:
            setting["positional"] = True
        if command:
            setting["only_for"] = {"command": [command]}
        same = by_key.get(setting["key"])
        if same is not None:
            if command and same.get("only_for") and {k: v for k, v in same.items() if k != "only_for"} == \
                    {k: v for k, v in setting.items() if k != "only_for"}:
                same["only_for"]["command"].append(command)
                continue
            setting["key"] = f"{setting['key']}_{command or len(by_key)}"
        by_key[setting["key"]] = setting
        settings.append(setting)
    # The script expects options before positionals for the main parser, and the command first.
    return settings, notes


def third_party(imports: set[str], local: set[str]) -> list[str]:
    stdlib = set(getattr(sys, "stdlib_module_names", ())) | {"__future__"}
    found = set()
    for name in imports:
        if name.startswith("."):
            continue
        top = name.split(".")[0]
        if top in stdlib or top in local or top in ("trapyze_helper", "trapyze"):
            continue
        found.add(PACKAGES.get(name) or PACKAGES.get(top) or top)
    return sorted(found, key=str.lower)


def read_requirements(folder: Path) -> list[str] | None:
    for name in ("requirements.txt", "requirements.in", "requirements-prod.txt"):
        p = folder / name
        if p.is_file():
            out = []
            for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.split("#")[0].strip()
                if line and not line.startswith(("-", "git+", "http")):
                    out.append(line)
            return out
    pp = folder / "pyproject.toml"
    if pp.is_file():
        try:
            import tomllib

            deps = tomllib.loads(pp.read_text(encoding="utf-8")).get("project", {}).get("dependencies")
            if isinstance(deps, list):
                return [str(d) for d in deps]
        except Exception:
            pass
    return None


# Path changes --------------------------------------------------------------------
def _offsets(source: str):
    """(line, utf-8 column) from ast -> index in the text."""
    starts, total = [0], 0
    lines = source.splitlines(keepends=True)
    for line in lines:
        total += len(line)
        starts.append(total)

    def at(lineno: int, col: int) -> int:
        line = lines[lineno - 1] if lineno - 1 < len(lines) else ""
        return starts[lineno - 1] + len(line.encode("utf-8")[:col].decode("utf-8", errors="ignore"))
    return at


def find_data_uses(info: PyInfo, names: set[str]) -> list[dict[str, Any]]:
    """Places where the code names a data file that moves to the shared data folder."""
    if info.tree is None or not names:
        return []
    parents: dict[int, ast.AST] = {}
    for node in ast.walk(info.tree):
        for child in ast.iter_child_nodes(node):
            parents[id(child)] = node
    at = _offsets(info.source)
    found = []
    for node in ast.walk(info.tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        value = node.value.replace("\\", "/")
        name = next((n for n in names if value == n or value.endswith("/" + n)), None)
        if not name:
            continue
        target: ast.AST = node
        parent = parents.get(id(node))
        if isinstance(parent, (ast.JoinedStr, ast.FormattedValue)):
            continue  # part of an f-string: changing it safely needs a person
        if isinstance(parent, ast.BinOp) and isinstance(parent.op, ast.Div) and parent.right is node:
            target = parent  # BASE / "prices.sqlite"
        elif isinstance(parent, ast.Call) and parent.args and parent.args[-1] is node and \
                ast.unparse(parent.func) in ("os.path.join", "path.join", "join"):
            target = parent  # os.path.join(BASE, "prices.sqlite")
        elif isinstance(parent, ast.Call) and ast.unparse(parent.func) in ("Path", "pathlib.Path") and len(parent.args) == 1:
            target = parent  # Path("prices.sqlite")
        if getattr(target, "end_lineno", None) is None:
            continue
        start, end = at(target.lineno, target.col_offset), at(target.end_lineno, target.end_col_offset)
        line_text = info.source.splitlines()[target.lineno - 1]
        before = info.source[start:end]
        after = f'{HELPER_NAME}("{name}")'
        found.append({"id": f"{info.rel}:{start}", "file": info.rel, "line": target.lineno, "data": name,
                      "start": start, "end": end, "before": before, "after": after,
                      "line_before": line_text.strip(),
                      "line_after": line_text.replace(before, after, 1).strip() if before in line_text else after})
    found.sort(key=lambda c: c["start"])
    # Drop changes nested inside another (keep the outer one).
    kept: list[dict[str, Any]] = []
    for c in found:
        if kept and c["start"] < kept[-1]["end"]:
            continue
        kept.append(c)
    return kept


def apply_changes(source: str, changes: list[dict[str, Any]]) -> str:
    if not changes:
        return source
    for c in sorted(changes, key=lambda c: c["start"], reverse=True):
        source = source[:c["start"]] + c["after"] + source[c["end"]:]
    return _insert_after_header(source, HELPER_CODE)


def _insert_after_header(source: str, code: str) -> str:
    """Put code after the module docstring and `from __future__` imports (which must come first)."""
    tree = ast.parse(source)
    line = 0
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str) and line == 0:
            line = node.end_lineno or 0
        elif isinstance(node, ast.ImportFrom) and node.module == "__future__":
            line = node.end_lineno or line
        else:
            break
    lines = source.splitlines(keepends=True)
    if line == 0:  # after a shebang / coding line / the label, if any
        while line < len(lines) and lines[line].startswith("#"):
            line += 1
    return "".join(lines[:line]) + ("\n" if line and not lines[line - 1].endswith("\n") else "") + \
        ("\n" if line else "") + code + "".join(lines[line:])


# Labels -------------------------------------------------------------------------
def _toml(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_toml(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{_key(k)} = {_toml(v)}" for k, v in value.items()) + " }"
    return json.dumps(str(value), ensure_ascii=False)


def _key(k: str) -> str:
    return k if re.match(r"^[A-Za-z0-9_-]+$", k) else json.dumps(k)


def label_lines(label: dict[str, Any], with_block: bool, dependencies: list[str] | None) -> list[str]:
    lines = []
    if with_block:
        lines.append("# /// script")
        if dependencies:
            lines.append(f"# dependencies = {_toml(dependencies)}")
    lines.append("# [tool.trapyze]")
    for k in ("name", "description", "icon", "color", "writes", "reads", "connections", "warning_codes"):
        if label.get(k) not in (None, "", [], {}):
            lines.append(f"# {k} = {_toml(label[k])}")
    for s in label.get("settings", []):
        lines.append("#")
        lines.append("# [[tool.trapyze.settings]]")
        for k in ("key", "label", "type", "options", "default", "min", "max", "required", "help", "flag", "switch",
                  "positional", "only_for"):
            if k in s and s[k] is not None:
                lines.append(f"# {k} = {_toml(s[k])}")
    if with_block:
        lines.append("# ///")
    return lines


def add_label(source: str, label: dict[str, Any], dependencies: list[str] | None) -> str:
    """Put the traPYze label into a script's text (or add to its existing script block)."""
    if "[tool.trapyze]" in source:
        return source
    lines = source.splitlines(keepends=True)
    try:
        meta = find_block(source)
    except LabelError:
        meta = None
    if meta is not None:
        for i, line in enumerate(lines):
            if line.strip() == "# /// script":
                end = next(j for j in range(i + 1, len(lines)) if lines[j].strip() == "# ///")
                addition = label_lines(label, False, None)
                newline = "\r\n" if lines[end].endswith("\r\n") else "\n"
                lines[end:end] = ["#" + newline] + [x + newline for x in addition]
                return "".join(lines)
    newline = "\r\n" if lines and lines[0].endswith("\r\n") else "\n"
    block = [x + newline for x in label_lines(label, True, dependencies)] + [newline]
    head = 0
    while head < len(lines) and head < 2 and (lines[head].startswith("#!") or re.match(r"^#.*coding[:=]", lines[head])):
        head += 1
    return "".join(lines[:head] + block + lines[head:])


# The scan ------------------------------------------------------------------------
def wsl_distros(platform: str | None = None, run=None, exists=None) -> list[str]:
    """The Linux systems installed in WSL, Ubuntu first (empty when there are none, or not Windows).

    Windows can't list \\\\wsl.localhost itself, so ask wsl.exe; if that fails, try the usual names."""
    import subprocess

    platform = platform or sys.platform
    if not platform.startswith("win"):
        return []
    run = run or (lambda cmd: subprocess.run(cmd, capture_output=True, timeout=15,
                                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)))
    exists = exists or (lambda p: Path(p).exists())
    names: list[str] = []
    try:
        done = run(["wsl.exe", "--list", "--quiet"])
        raw = done.stdout or b""
        text = raw.decode("utf-16-le", errors="ignore") if b"\x00" in raw else raw.decode("utf-8", errors="ignore")
        names = [n.strip().strip("\ufeff") for n in text.splitlines() if n.strip().strip("\ufeff")]
    except (OSError, subprocess.SubprocessError):
        names = []
    if not names:
        names = [n for n in ("Ubuntu", "Ubuntu-24.04", "Ubuntu-22.04", "Ubuntu-20.04", "Debian", "kali-linux", "openSUSE-Leap-15.6")
                 if exists(f"\\\\wsl.localhost\\{n}") or exists(f"\\\\wsl$\\{n}")]
    names = [n for n in names if not n.lower().startswith("docker")]
    return sorted(dict.fromkeys(names), key=lambda d: (not d.lower().startswith("ubuntu"), d.lower()))


def wsl_root(distro: str, exists=None) -> str:
    exists = exists or (lambda p: Path(p).exists())
    for root in ("\\\\wsl.localhost", "\\\\wsl$"):
        if exists(f"{root}\\{distro}"):
            return f"{root}\\{distro}"
    return f"\\\\wsl.localhost\\{distro}"


def windows_path(text: str, platform: str | None = None, distros: list[str] | None = None, exists=None) -> str:
    """On Windows, a Linux path from WSL (/home/alex/x) becomes \\\\wsl.localhost\\<distro>\\home\\alex\\x,
    and /mnt/c/... becomes C:\\..."""
    platform = platform or sys.platform
    if not platform.startswith("win") or not text.startswith("/"):
        return text
    m = re.match(r"^/mnt/([a-zA-Z])(/.*)?$", text)
    if m:
        return f"{m.group(1).upper()}:" + (m.group(2) or "/").replace("/", "\\")
    exists = exists or (lambda p: Path(p).exists())
    found = distros if distros is not None else wsl_distros(platform, exists=exists)
    if not found:
        raise ImportProblem("That looks like a path inside WSL, but Windows can't see WSL right now. Start Ubuntu once, "
                            "or paste the path as \\\\wsl.localhost\\Ubuntu\\home\\…")
    tail = text.replace("/", "\\")
    for distro in found:  # the first one that has this path
        candidate = wsl_root(distro, exists) + tail
        if exists(candidate):
            return candidate
    return wsl_root(found[0], exists) + tail


def _walk(src: Path) -> tuple[list[Path], list[str]]:
    """The program's files, without going into .venv, caches or links (Windows can't follow
    links made inside WSL). Returns the files and the ones that couldn't be read."""
    import os

    files: list[Path] = []
    unreadable: list[str] = []

    def problem(exc: OSError) -> None:
        name = getattr(exc, "filename", None)
        if name:
            unreadable.append(Path(name).relative_to(src).as_posix() if str(name).startswith(str(src)) else str(name))

    for folder, dirs, names in os.walk(src, topdown=True, onerror=problem, followlinks=False):
        here = Path(folder)
        keep = []
        for d in sorted(dirs):
            full = here / d
            if d in SKIP_DIRS or d.startswith(".") or d.endswith(".egg-info"):
                continue
            try:
                if full.is_symlink():
                    continue
            except OSError:
                continue
            keep.append(d)
        dirs[:] = keep
        for name in sorted(names):
            full = here / name
            try:
                if full.is_symlink() or not full.is_file():
                    continue
                full.stat()
            except OSError:
                unreadable.append(full.relative_to(src).as_posix())
                continue
            files.append(full)
            if len(files) > MAX_FILES:
                raise ImportProblem(f"This folder has more than {MAX_FILES} files. Choose the program's own folder.")
    return files, unreadable


def _same_or_inside(path: Path, root: Path) -> bool:
    import os

    a, b = os.path.normcase(os.path.abspath(path)), os.path.normcase(os.path.abspath(root))
    return a == b or a.startswith(b.rstrip("\\/") + os.sep)


def scan(source: str | Path, home: Home) -> dict[str, Any]:
    """Everything the wizard shows before anything is copied."""
    text = str(source).strip().strip('"').strip("'").strip()
    if not text:
        raise ImportProblem("Paste the path of a folder or script, or choose one with the buttons.")
    src = Path(windows_path(text)).expanduser()
    try:
        found = src.exists()
    except OSError as exc:
        raise ImportProblem(f"Windows can't open {src}: {exc}") from None
    if not found:
        raise ImportProblem(f"Can't find {src}. Check the path, or choose the folder with Browse.")
    shared_zip = None
    if src.is_file() and src.suffix.lower() == ".zip":
        shared_zip, src = src, _unpack(src)
    if not str(src).startswith("\\\\"):  # resolving network and WSL paths can mangle them
        try:
            src = src.resolve()
        except OSError:
            pass
    if _same_or_inside(src, home.root):
        raise ImportProblem("That's inside traPYze's own folder already. Choose a folder elsewhere.")
    single = src.is_file()
    if single and src.suffix.lower() != ".py":
        raise ImportProblem("Choose a folder, a single .py file, or a .zip shared from traPYze.")
    root = src.parent if single else src
    unreadable: list[str] = []
    if single:
        files = [src]
    else:
        files, unreadable = _walk(src)
    rels = {p: p.relative_to(root).as_posix() for p in files}
    py: dict[Path, PyInfo] = {}
    for p in files:
        if p.suffix == ".py":
            try:
                py[p] = PyInfo(rels[p], p.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                unreadable.append(rels[p])
    files = [p for p in files if p.suffix != ".py" or p in py]
    if not py:
        raise ImportProblem("There are no Python files (.py) in that folder.")
    local = {p.stem for p in py} | {p.parent.name for p in py if (p.parent / "__init__.py").exists()}
    imported_by_others: set[str] = set()
    for p, info in py.items():
        for name in info.imports:
            top = name.lstrip(".").split(".")[0]
            if top in local and top != p.stem:
                imported_by_others.add(top)
    folder_name = _safe_folder(src.stem if single else src.name)
    deps_from_file = read_requirements(root) if not single else None
    try:
        shared_info = json.loads((root / PROGRAM_FILE).read_text(encoding="utf-8")) if not single else {}
    except (OSError, ValueError):
        shared_info = {}
    conductor = find_conductor(py, rels, folder_name) if not single else {
        "main": next(iter(py), None), "helpers": set(), "extras": [], "reach": {}}
    main_path = conductor["main"]
    main_rel = rels[main_path] if main_path else None
    # A program shared from traPYze says which of its tools had their own tile: keep that.
    shown_extra: set[Path] = set()
    if isinstance(shared_info.get("hidden"), list):
        hidden_before = set(shared_info["hidden"])
        for p in conductor["extras"]:
            if "[tool.trapyze]" in py[p].source and \
                    program_tool_id(Path(folder_name), Path(folder_name) / rels[p]) not in hidden_before:
                shown_extra.add(p)

    data_names = {p.name for p in files if p.suffix.lower() in DATA_EXT and not _skip_file(p.name)}
    items: list[dict[str, Any]] = []
    programs: list[dict[str, Any]] = []
    changes: list[dict[str, Any]] = []
    notes: list[str] = []
    for p in files:
        rel, name, ext = rels[p], p.name, p.suffix.lower()
        size = p.stat().st_size
        item: dict[str, Any] = {"rel": rel, "size": size, "include": True}
        if ext == ".py":
            info = py[p]
            if p == main_path:
                item.update(kind="program", role="main",
                            why="The main file: it starts the program" if not single else "Runs on its own")
            elif p in conductor["extras"]:
                item.update(kind="program", role="extra",
                            why=f"Can run on its own, but {main_rel} doesn't use it. Hidden under the program; "
                                "you can give it its own tile")
            else:
                item["kind"] = "module"
                item["why"] = (f"Used by {main_rel}" if main_path and p in conductor["reach"].get(main_path, set()) else
                               "Used by the other files" if p in conductor["helpers"] else
                               f"Can't be read ({info.error})" if info.error else
                               "A test" if p.name.startswith("test_") else "No starting point of its own")
        elif name == PROGRAM_FILE or (name == "presets.json" and "/" not in rel):
            item.update(kind="skip", include=False, why="traPYze's own notes about the program: read, not copied")
        elif _is_env(name):
            item.update(kind="env", include=True, why="Keys and passwords: offered to the vault, not copied")
        elif _skip_file(name) or (ext in (".sqlite", ".db") and re.search(r"\.bak|backup", name, re.I)):
            item.update(kind="skip", include=False, why="A backup, log or temporary file")
        elif ext in DATA_EXT:
            item.update(kind="data", place="shared", why="Data")
            existing = home.data / name
            if existing.exists():
                item["exists"] = {"size": existing.stat().st_size, "modified": existing.stat().st_mtime,
                                  "newer_here": existing.stat().st_mtime >= p.stat().st_mtime}
                item["keep_existing"] = item["exists"]["newer_here"]
        elif name.lower() in ("requirements.txt", "requirements.in", "pyproject.toml", "setup.py", "setup.cfg"):
            item.update(kind="deps", why="The packages it needs: put in the labels")
        elif any(fnmatch.fnmatch(name.lower(), pat) for pat in RUNNERS):
            item.update(kind="other", include=False, why="A start-up script: in traPYze, a plan does this")
        elif ext in DOC_EXT or name.lower().endswith(".example"):
            item.update(kind="doc", why="Notes and read-me")
        else:
            item.update(kind="other", why="Used by the program")
        items.append(item)

    for p, info in py.items():
        item = next(i for i in items if i["rel"] == rels[p])
        if item["kind"] == "program":
            meta = info.label or {}
            existing_label = (meta.get("tool") or {}).get("trapyze")
            settings, option_notes = read_options(info) if not existing_label else ([], [])
            deps = meta.get("dependencies") if meta.get("dependencies") else (
                deps_from_file if deps_from_file is not None else third_party(info.imports | _helper_imports(py, info, local), local))
            first_line = info.docstring.splitlines()[0].strip() if info.docstring else ""
            tool_id = (p.stem if single else program_tool_id(Path(folder_name), Path(folder_name) / rels[p]))
            programs.append({
                "rel": rels[p], "id": tool_id, "include": p == main_path or p in shown_extra or single,
                "role": "main" if p == main_path else "extra", "has_label": bool(existing_label),
                "uses": len(conductor["reach"].get(p, ())),
                "label": existing_label or {"name": _pretty(src.stem if single else src.name) if p == main_path and p.stem.lower() in MAIN_NAMES
                                            else _pretty(p.stem), "description": first_line[:160], "icon": "terminal",
                                            "color": "blue", "settings": settings},
                "dependencies": list(deps or []), "notes": option_notes,
            })
        changes += find_data_uses(info, data_names)
    if unreadable:
        shown = ", ".join(unreadable[:6]) + (f" and {len(unreadable) - 6} more" if len(unreadable) > 6 else "")
        notes.append(f"Windows couldn't read {len(unreadable)} file(s), so they're left out: {shown}. "
                     "Usually these are links made inside WSL; the program rarely needs them.")
    programs.sort(key=lambda x: (x["role"] != "main", x["rel"]))
    if not programs:
        notes.append("traPYze didn't find a file that runs on its own (with `if __name__ == \"__main__\":`). "
                     "Mark one as a program below.")
    # Which program changes which shared data file (for the locks and freshness checks).
    db_write = re.compile(r"\.commit\(|executemany|\bINSERT\b|\bUPDATE\b|CREATE TABLE|to_sql\(", re.I)
    file_write = {".csv": r"to_csv\(", ".tsv": r"to_csv\(", ".xlsx": r"to_excel\(|\.save\(", ".xls": r"to_excel\(",
                  ".xlsm": r"\.save\(", ".parquet": r"to_parquet\(", ".feather": r"to_feather\(", ".pkl": r"pickle\.dump|to_pickle\(",
                  ".pickle": r"pickle\.dump|to_pickle\(", ".h5": r"to_hdf\(", ".hdf5": r"to_hdf\("}
    for prog in programs:
        text = py[next(p for p in py if rels[p] == prog["rel"])].source
        text += "".join(other.source for other in py.values() if other.rel != prog["rel"] and Path(other.rel).stem in imported_by_others)
        writes = []
        for n in sorted(data_names):
            if n not in text:
                continue
            ext = Path(n).suffix.lower()
            pattern = db_write.pattern if ext in (".sqlite", ".sqlite3", ".db", ".duckdb") else file_write.get(ext)
            if pattern and re.search(pattern, text, re.I):
                writes.append(f"data/{n}")
        if writes and not prog["has_label"]:
            prog["label"]["writes"] = writes
    existing_folder = home.scripts / folder_name
    clashes = []
    for prog in programs:
        top = home.scripts / f"{prog['id']}.py"
        if top.exists():
            clashes.append({"id": prog["id"], "file": top.name})
            try:
                old = (find_block(top.read_text(encoding="utf-8", errors="replace")) or {})
            except LabelError:
                old = {}
            old_label = (old.get("tool") or {}).get("trapyze")
            if old_label and not prog["has_label"]:
                # The tool it replaces has a label made by hand: keep that one.
                prog["label"] = old_label
                prog["kept_label"] = top.name
                if old.get("dependencies"):
                    prog["dependencies"] = sorted(set(prog["dependencies"]) | set(old["dependencies"]), key=str.lower)
    readme = next((rels[p] for p in files if p.name.lower() in ("start_here.md", "readme.md", "readme.txt")), None)
    info: dict[str, Any] = {}
    if not single:
        try:
            info = json.loads((root / PROGRAM_FILE).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            info = {}
    preset_count = sum(len(v) for v in _presets_in(root, py, rels).values())
    if preset_count:
        notes.append(f"It comes with {preset_count} preset{'s' if preset_count != 1 else ''}; they're added too.")
    return {
        "zip": str(shared_zip) if shared_zip else None, "description": info.get("description", ""),
        "source": str(src), "single": single, "folder": folder_name if not single else None,
        "name": info.get("name") or _pretty(src.stem if single else src.name), "programs": programs, "items": items, "changes": changes,
        "notes": notes, "readme": readme, "deps_file": deps_from_file is not None,
        "folder_exists": (not single) and existing_folder.exists(),
        "clashes": clashes,
    }


def _unpack(zip_path: Path) -> Path:
    """Unpack a shared .zip to a scratch folder (the same one each time for the same file)."""
    import hashlib
    import tempfile
    import zipfile

    stat = zip_path.stat()
    key = hashlib.sha256(f"{zip_path}|{stat.st_size}|{stat.st_mtime}".encode()).hexdigest()[:16]
    target = Path(tempfile.gettempdir()) / "trapyze-import" / key
    if not target.exists():
        try:
            with zipfile.ZipFile(zip_path) as z:
                total = sum(i.file_size for i in z.infolist())
                if total > 4 * 1024**3:
                    raise ImportProblem("That .zip unpacks to more than 4 GB. Import its folder instead.")
                staging = target.with_name(key + ".part")
                shutil.rmtree(staging, ignore_errors=True)
                for member in z.infolist():
                    name = member.filename.replace("\\", "/")
                    parts = [x for x in name.split("/") if x not in ("", ".")]
                    if not parts or ".." in parts or ":" in parts[0] or name.startswith("/"):
                        continue  # never write outside the scratch folder
                    dest = staging.joinpath(*parts)
                    if member.is_dir():
                        dest.mkdir(parents=True, exist_ok=True)
                        continue
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with z.open(member) as src, open(dest, "wb") as out:
                        shutil.copyfileobj(src, out)
                staging.rename(target)
        except zipfile.BadZipFile:
            raise ImportProblem("That .zip file is damaged or isn't a zip.") from None
    inside = [p for p in target.iterdir() if not p.name.startswith(".")]
    return inside[0] if len(inside) == 1 and inside[0].is_dir() else target


def _presets_in(root: Path, py: dict[Path, "PyInfo"], rels: dict[Path, str]) -> dict[str, dict[str, Any]]:
    """Presets that came along: in a script's label, or presets.json in a shared program."""
    found: dict[str, dict[str, Any]] = {}
    for p, info in py.items():
        label = ((info.label or {}).get("tool") or {}).get("trapyze") or {}
        if isinstance(label.get("presets"), dict):
            found[rels[p]] = dict(label["presets"])
    try:
        extra = json.loads((root / "presets.json").read_text(encoding="utf-8"))
        for rel, presets in extra.items():
            if isinstance(presets, dict):
                found.setdefault(rel, {}).update(presets)
    except (OSError, ValueError, AttributeError):
        pass
    return found


def _helper_imports(py: dict[Path, PyInfo], info: PyInfo, local: set[str]) -> set[str]:
    """Packages a program needs through its own helper files."""
    out: set[str] = set()
    todo = [n.lstrip(".").split(".")[0] for n in info.imports if n.lstrip(".").split(".")[0] in local]
    seen: set[str] = set()
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        seen.add(name)
        for p, other in py.items():
            if p.stem == name:
                out |= other.imports
                todo += [n.lstrip(".").split(".")[0] for n in other.imports if n.lstrip(".").split(".")[0] in local]
    return out


# Doing it --------------------------------------------------------------------------
def apply(source: str | Path, home: Home, choices: dict[str, Any]) -> dict[str, Any]:
    """Copy and label, as chosen in the wizard. Reads the folder again first."""
    plan = scan(source, home)
    root = Path(plan["source"])
    root = root.parent if plan["single"] else root
    chosen_files = choices.get("files") or {}
    chosen_programs = choices.get("programs") or {}
    chosen_changes = choices.get("changes") or {}
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    replaced = home.scripts / "_replaced"
    report: dict[str, Any] = {"tools": [], "hidden": [], "data": [], "kept_data": [], "env": [], "copied": 0, "skipped": [],
                              "replaced": [], "notes": []}

    if plan["single"]:
        target_dir = home.scripts
        folder = None
    else:
        folder = _safe_folder(str(choices.get("folder") or plan["folder"]))
        target_dir = home.scripts / folder
        if target_dir.exists():
            if not choices.get("replace_folder"):
                raise ImportProblem(f"There's already a program folder called {folder}. Choose another name, or replace it.")
            replaced.mkdir(parents=True, exist_ok=True)
            shutil.move(str(target_dir), str(replaced / f"{folder}-{stamp}"))
            report["replaced"].append(f"scripts/{folder}")
    # Program files that replace an older single-file tool with the same id.
    for clash in plan["clashes"]:
        prog = next(p for p in plan["programs"] if p["id"] == clash["id"])
        if (chosen_programs.get(prog["rel"]) or {}).get("include", True) and choices.get("replace_tools", True):
            replaced.mkdir(parents=True, exist_ok=True)
            old = home.scripts / clash["file"]
            if old.exists():
                shutil.move(str(old), str(replaced / f"{old.stem}-{stamp}.py"))
                report["replaced"].append(f"scripts/{clash['file']}")

    by_rel = {i["rel"]: i for i in plan["items"]}
    program_by_rel = {p["rel"]: p for p in plan["programs"]}
    shared = {i["rel"] for i in plan["items"] if i["kind"] == "data"
              and (chosen_files.get(i["rel"]) or {}).get("place", i.get("place")) == "shared"
              and (chosen_files.get(i["rel"]) or {}).get("include", i["include"])}
    shared_names = {Path(r).name for r in shared}
    for rel, item in by_rel.items():
        pick = chosen_files.get(rel) or {}
        include = pick.get("include", item["include"])
        kind = item["kind"]
        hide = rel in program_by_rel and not (chosen_programs.get(rel) or {}).get("include", program_by_rel[rel]["include"])
        if pick.get("kind") in ("program", "module") and item["kind"] in ("program", "module"):
            kind = pick["kind"]
        src = root / rel
        if kind == "env":
            if include:
                report["env"].append(str(src))
            continue
        if not include or kind == "skip":
            report["skipped"].append(rel)
            continue
        if kind == "data" and rel in shared:
            dest = home.data / Path(rel).name
            if dest.exists():
                keep = pick.get("keep_existing", item.get("keep_existing", True))
                if keep:
                    report["kept_data"].append(dest.name)
                    continue
                shutil.copy2(dest, dest.with_name(f"{dest.stem}.before-import-{stamp}{dest.suffix}"))
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            report["data"].append(dest.name)
            continue
        dest = (target_dir / (Path(rel).name if plan["single"] else rel))
        dest.parent.mkdir(parents=True, exist_ok=True)
        if src.suffix == ".py":
            text = src.read_text(encoding="utf-8", errors="replace")
            mine = [c for c in plan["changes"] if c["file"] == rel and chosen_changes.get(c["id"], True)
                    and c["data"] in shared_names]
            if mine:
                text = apply_changes(text, mine)
            if kind == "program":
                prog = program_by_rel.get(rel) or {"label": {"name": _pretty(src.stem)}, "dependencies": [], "has_label": False}
                override = chosen_programs.get(rel) or {}
                label = dict(prog["label"])
                if override.get("name"):
                    label["name"] = str(override["name"])[:80]
                if override.get("description") is not None:
                    label["description"] = str(override["description"])[:300]
                deps = override.get("dependencies", prog["dependencies"])
                if not prog["has_label"]:
                    text = add_label(text, label, list(deps or []))
                dest.write_text(text, encoding="utf-8", newline="")
                tool_id = src.stem if plan["single"] else program_tool_id(target_dir, dest)
                try:
                    read_tool(dest, tool_id, folder)
                    if hide and folder:
                        report["hidden"].append(tool_id)
                    else:
                        report["tools"].append(tool_id)
                except LabelError as exc:
                    report["notes"].append(f"{rel}: the label needs a look: {exc}")
            else:
                dest.write_text(text, encoding="utf-8", newline="")
        else:
            shutil.copy2(src, dest)
        report["copied"] += 1
    if folder:
        info = {"name": str(choices.get("name") or plan["name"])[:80],
                "description": str(choices.get("description") if choices.get("description") is not None else plan.get("description") or ""),
                "readme": plan["readme"], "source": plan.get("zip") or plan["source"], "imported": time.time(),
                "hidden": report["hidden"]}
        (target_dir / PROGRAM_FILE).write_text(json.dumps(info, indent=1, ensure_ascii=False), encoding="utf-8")
    report["folder"] = folder
    # Presets that came along with a shared tool.
    from .store import Presets, StoreError
    from .label import SettingError

    py_now = {}
    for rel, item in by_rel.items():
        if item["kind"] == "program":
            dest = target_dir / (Path(rel).name if plan["single"] else rel)
            if dest.exists():
                py_now[dest] = PyInfo(rel, dest.read_text(encoding="utf-8", errors="replace"))
    came = _presets_in(root, {d: i for d, i in py_now.items()}, {d: i.rel for d, i in py_now.items()})
    added = 0
    for rel, presets in came.items():
        dest = target_dir / (Path(rel).name if plan["single"] else rel)
        if not dest.exists():
            continue
        tool_id = dest.stem if plan["single"] else program_tool_id(target_dir, dest)
        try:
            tool = read_tool(dest, tool_id, folder)
        except LabelError:
            continue
        for name, values in presets.items():
            try:
                Presets(home.internal).save(tool, str(name), dict(values))
                added += 1
            except (SettingError, StoreError, TypeError, ValueError) as exc:
                report["notes"].append(f"The preset “{name}” for {tool.name} doesn't fit its settings and was left out: {exc}")
    report["presets"] = added
    return report


def tidy(home: Home, folder: str) -> dict[str, Any]:
    """For a program already in traPYze: keep the main file's tile, hide the other scripts."""
    path = home.scripts / folder
    if not path.is_dir():
        raise ImportProblem(f"There's no program folder called {folder}.")
    from .home import _program_files

    files = sorted(_program_files(path))
    rels = {p: p.relative_to(path).as_posix() for p in files}
    py = {p: PyInfo(rels[p], p.read_text(encoding="utf-8", errors="replace")) for p in files}
    labelled = {p for p, info in py.items() if "[tool.trapyze]" in info.source}
    if not labelled:
        raise ImportProblem("This program has no tools yet.")
    found = find_conductor(py, rels, folder, candidates=labelled)
    main = found["main"]
    main_id = program_tool_id(path, main)
    hide = {program_tool_id(path, p) for p in labelled if p != main}
    hidden = home.set_hidden(folder, hide, {main_id})
    return {"main": main_id, "main_file": rels[main], "hidden": hidden,
            "helpers": len(found["reach"].get(main, ()))}

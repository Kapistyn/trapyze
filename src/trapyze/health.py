"""The health check: an offline review of a tool's script, in plain words.

It looks for things that stop a tool from starting (syntax errors, packages it imports
but doesn't list), secrets typed into the code, risky lines, and paths that only exist
on one computer. Each finding says what to do about it. Nothing is sent anywhere.
"""

from __future__ import annotations

import ast
import json
import re
import tomllib
from pathlib import Path
from typing import Any

from .importer import PyInfo, third_party

LEVELS = {"bad": 3, "warn": 2, "info": 1}
# Packages that are normally used through another one (pandas reads Excel with openpyxl …).
INDIRECT = {"openpyxl", "xlrd", "xlsxwriter", "odfpy", "pyarrow", "fastparquet", "lxml", "html5lib", "tabulate",
            "kaleido", "sqlalchemy", "psycopg2", "psycopg2-binary", "pymysql", "tzdata", "pytz", "scipy", "tables",
            "numexpr", "bottleneck", "jinja2", "matplotlib", "pyqt5", "pyqt6", "certifi", "chardet", "charset-normalizer"}
SECRET_PATTERNS = [
    (re.compile(r"AKIA[0-9A-Z]{16}"), "an Amazon key"),
    (re.compile(r"\bsk-(?:ant-|proj-|or-)?[A-Za-z0-9_\-]{20,}"), "an AI service key"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}"), "a GitHub token"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"), "a Slack token"),
    (re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"), "a Google key"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "a private key"),
]
SECRET_NAME = re.compile(r"(?i)\b([a-z_]*(?:api_?key|apikey|secret|token|passw(?:or)?d|pwd|access_key)[a-z_]*)\b\s*[:=]\s*(['\"])([^'\"\s]{6,})\2")
# FMP_KEY = "…", key = "…": only when the value looks random (letters and digits, 16+), so sort_key = "name" passes.
KEY_NAME = re.compile(r"(?i)\b([a-z0-9_]*key)\b\s*[:=]\s*(['\"])((?=[^'\"\s]*\d)(?=[^'\"\s]*[a-z])[A-Za-z0-9_\-]{16,})\2")
PLACEHOLDER = re.compile(r"(?i)^(your|xxx|<|\.\.\.|changeme|example|none|null|dummy|test|placeholder)")
FIXED_PATH = re.compile(r"^(?:[A-Za-z]:[\\/](?:Users|Documents and Settings|Temp|Data)|/(?:home|Users|mnt/[a-z])/)")


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name.strip().lower())


def _dep_name(spec: str) -> str:
    return _norm(re.split(r"[<>=!~\[; @]", spec.strip(), maxsplit=1)[0])


def _local_modules(path: Path) -> set[str]:
    folder = path.parent
    if not folder.exists():
        return set()
    out = {p.stem for p in folder.glob("*.py")}
    out.update(p.name for p in folder.iterdir() if p.is_dir() and (p / "__init__.py").exists())
    return out


def finding(level: str, code: str, title: str, detail: str = "", line: int | None = None, fix: dict | None = None) -> dict:
    return {"level": level, "code": code, "title": title, "detail": detail, "line": line, "fix": fix}


def check(tool: Any, source: str | None = None) -> list[dict[str, Any]]:
    path: Path = tool.path
    if source is None:
        source = path.read_text(encoding="utf-8", errors="replace")
    out: list[dict[str, Any]] = []
    try:
        compile(source, str(path), "exec")
    except SyntaxError as exc:
        out.append(finding("bad", "syntax", "It won't start: Python can't read this script",
                           f"Line {exc.lineno}: {exc.msg}. Open it in your editor and look at that line.", exc.lineno))
        return out

    info = PyInfo(path.name, source)
    used = {_norm(p): p for p in third_party(info.imports, _local_modules(path))}
    listed = {_dep_name(d): d for d in tool.dependencies if d.strip()}
    for key, pkg in used.items():
        if key not in listed:
            out.append(finding("bad", "missing-package", f"It imports {pkg}, which isn't in its package list",
                               "Without it in the list, the tool stops with “No module named …”.",
                               fix={"action": "add-package", "package": pkg, "label": f"Add {pkg}"}))
    for key, spec in listed.items():
        if key not in used and key not in INDIRECT:
            out.append(finding("info", "unused-package", f"{spec} is listed but not imported",
                               "Fine if another package uses it (for example pandas reading Excel). Otherwise it only "
                               "makes the first run slower."))

    lines = source.splitlines()
    for n, text in enumerate(lines, 1):
        hit = next((what for rx, what in SECRET_PATTERNS if rx.search(text)), None)
        m = SECRET_NAME.search(text) or KEY_NAME.search(text)
        if not hit and m and not PLACEHOLDER.match(m.group(3)) and "environ" not in text and "getenv" not in text:
            hit = f"a value for “{m.group(1)}”"
        if hit:
            out.append(finding("bad", "secret", f"Line {n} has {hit} typed into the code",
                               "Anyone who gets the script gets the key too. Put it in the vault (Connections), list the "
                               "connection in the label, and read it with os.environ[...] instead.", n))

    risky: dict[str, tuple[str, str, str, int]] = {}
    tree = info.tree
    for node in ast.walk(tree) if tree else []:
        if isinstance(node, ast.Call):
            name = _call_name(node.func)
            if name in ("eval", "exec"):
                risky.setdefault(name, ("warn", f"It uses {name}(), which runs text as code",
                                        "Risky if that text comes from a file, a website or a setting.", node.lineno))
            elif name in ("os.system", "os.popen"):
                risky.setdefault("shell", ("warn", "It runs shell commands", "Check what the command does; prefer subprocess "
                                           "with a list of arguments.", node.lineno))
            elif name.startswith("subprocess.") and any(k.arg == "shell" and isinstance(k.value, ast.Constant) and k.value.value is True for k in node.keywords):
                risky.setdefault("shell", ("warn", "It runs shell commands (shell=True)", "Check what the command does; a "
                                           "list of arguments without shell=True is safer.", node.lineno))
            elif name == "shutil.rmtree":
                risky.setdefault("rmtree", ("info", "It deletes whole folders", "Make sure it only touches folders it made.", node.lineno))
            elif name in ("os.remove", "os.unlink") or name.endswith(".unlink"):
                risky.setdefault("delete", ("info", "It deletes files", "Make sure it only touches files it made.", node.lineno))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and FIXED_PATH.match(node.value):
            risky.setdefault("path", ("warn", f"It uses a fixed path: {node.value[:60]}",
                                      "That folder may not exist on another computer, or for a plan. Use tz.data_path(...) for "
                                      "shared data and tz.output_path(...) for results.", node.lineno))
    for code, (level, title, detail, line) in risky.items():
        out.append(finding(level, code, title, f"Line {line}. {detail}", line))

    code = re.sub(r"(?ms)^# /// script\s*$.*?^# ///\s*$", "", source)  # the script without its label
    for s in tool.settings:
        names = {s.key, s.key.replace("_", "-"), (s.flag or "").lstrip("-")} - {""}
        if not any(n in code for n in names):
            out.append(finding("info", "unused-setting", f"The setting “{s.label}” isn't used in the code",
                               f"The script never mentions “{s.key}”, so changing it may do nothing."))
    if not tool.description:
        out.append(finding("info", "no-description", "It has no description",
                           "Add description = \"…\" to its label; the tile shows it when you hover."))
    out.sort(key=lambda f: -LEVELS[f["level"]])
    return out


def _call_name(func: ast.AST) -> str:
    parts = []
    while isinstance(func, ast.Attribute):
        parts.append(func.attr)
        func = func.value
    if isinstance(func, ast.Name):
        parts.append(func.id)
    return ".".join(reversed(parts))


def summary(findings: list[dict[str, Any]]) -> dict[str, Any]:
    worst = max((LEVELS[f["level"]] for f in findings), default=0)
    level = "bad" if worst == 3 else "warn" if worst == 2 else "good"
    return {"level": level, "count": sum(1 for f in findings if f["level"] != "info"), "notes": len(findings)}


def add_package(source: str, package: str) -> str:
    """The script with `package` added to the dependencies in its label."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._\-\[\],<>=!~ ]*", package or ""):
        raise ValueError("That doesn't look like a package name.")
    lines = source.splitlines(keepends=True)
    start = next((i for i, l in enumerate(lines) if l.strip() == "# /// script"), None)
    if start is None:
        raise ValueError("This script has no label yet. Import it again to give it one.")
    end = next((i for i in range(start + 1, len(lines)) if lines[i].strip() == "# ///"), None)
    if end is None:
        raise ValueError("The label isn't closed with “# ///”.")
    first = next((i for i in range(start + 1, end) if re.match(r"#\s*dependencies\s*=", lines[i])), None)
    nl = "\r\n" if lines[start].endswith("\r\n") else "\n"
    if first is None:
        current: list[str] = []
        first = last = start + 1
        replace = False
    else:
        last, text = first, ""
        while True:
            text += lines[last].lstrip()[1:].strip() + "\n"
            if text.count("[") <= text.count("]") or last + 1 >= end:
                break
            last += 1
        current = tomllib.loads(text)["dependencies"]
        replace = True
    if _norm(_dep_name(package)) in {_dep_name(d) for d in current}:
        return source
    new = f"# dependencies = [{', '.join(json.dumps(d) for d in [*current, package])}]{nl}"
    return "".join(lines[:first] + [new] + lines[last + 1 if replace else first:])

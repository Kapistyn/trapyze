"""The traPYze home folder: one place for scripts, shared data and results.

    Trapyze/
      scripts/     one .py file per tool; the only code a user sees
      outputs/     results, as outputs/<tool>/<date_time>/
      data/        shared databases and caches, used by every tool
      lib/         shared helper modules, importable by every tool
      .trapyze/    hidden: run history, locks, presets, schedules
"""

from __future__ import annotations

import json

import os
import shutil
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

from .label import LabelError, Tool, read_tool

HOME_ENV = "TRAPYZE_HOME"


def default_root() -> Path:
    env = os.environ.get(HOME_ENV)
    return Path(env).expanduser() if env else Path.home() / "Trapyze"


@dataclass
class Problem:
    """A script that couldn't be read, with the reason in plain words."""

    path: Path
    message: str


class Home:
    def __init__(self, root: str | Path | None = None):
        self.root = Path(root).expanduser() if root else default_root()

    # Folders -----------------------------------------------------------------
    @property
    def scripts(self) -> Path:
        return self.root / "scripts"

    @property
    def outputs(self) -> Path:
        return self.root / "outputs"

    @property
    def data(self) -> Path:
        return self.root / "data"

    @property
    def lib(self) -> Path:
        return self.root / "lib"

    @property
    def internal(self) -> Path:
        return self.root / ".trapyze"

    @property
    def runs(self) -> Path:
        return self.internal / "runs"

    @property
    def locks(self) -> Path:
        return self.internal / "locks"

    def exists(self) -> bool:
        return self.scripts.is_dir() and self.internal.is_dir()

    def init(self, with_examples: bool = True) -> list[Path]:
        """Create the folder layout. Never overwrites a file the user has.

        Returns the files that were added.
        """
        for folder in (self.scripts, self.outputs, self.data, self.lib, self.runs, self.locks):
            folder.mkdir(parents=True, exist_ok=True)
        added: list[Path] = []
        package = resources.files("trapyze") / "resources"
        added += _copy_missing(package / "helper", self.lib, refresh=True)
        if with_examples:
            added += _copy_missing(package / "examples", self.scripts)
        return added

    # Tools -------------------------------------------------------------------
    def tools(self) -> tuple[list[Tool], list[Problem]]:
        """All tools in scripts/, sorted by name, plus scripts that failed to read."""
        tools: list[Tool] = []
        problems: list[Problem] = []
        if not self.scripts.is_dir():
            return tools, problems
        for path in sorted(self.scripts.glob("*.py")):
            if path.name.startswith(("_", ".")):
                continue
            try:
                tools.append(read_tool(path))
            except LabelError as exc:
                problems.append(Problem(path, str(exc)))
        # Programs with several files: scripts/<program>/. Only files with a traPYze
        # label are tools; the rest are the program's own helpers.
        for folder in sorted(p for p in self.scripts.iterdir() if p.is_dir() and not p.name.startswith(("_", "."))):
            hidden = set(self._program_info(folder).get("hidden") or [])
            for path in sorted(_program_files(folder)):
                try:
                    if "[tool.trapyze]" not in path.read_text(encoding="utf-8", errors="replace"):
                        continue
                    tool = read_tool(path, program_tool_id(folder, path), folder.name)
                    tool.hidden = tool.id in hidden
                    tools.append(tool)
                except LabelError as exc:
                    problems.append(Problem(path, str(exc)))
        seen: dict[str, Tool] = {}
        for t in list(tools):
            if t.id in seen:
                tools.remove(t)
                problems.append(Problem(t.path, f"Another tool already has the id '{t.id}' ({seen[t.id].path.name}). Rename one of the files."))
            else:
                seen[t.id] = t
        tools.sort(key=lambda t: t.name.lower())
        return tools, problems

    def programs(self) -> dict[str, dict[str, Any]]:
        """Program folders in scripts/, with their name and read-me (from the import)."""
        out: dict[str, dict[str, Any]] = {}
        if not self.scripts.is_dir():
            return out
        for folder in sorted(p for p in self.scripts.iterdir() if p.is_dir() and not p.name.startswith(("_", "."))):
            info = self._program_info(folder)
            readme = info.get("readme") or next((n for n in ("START_HERE.md", "README.md", "readme.md", "README.txt")
                                                 if (folder / n).exists()), None)
            out[folder.name] = {"name": info.get("name") or folder.name.replace("_", " ").replace("-", " ").strip().capitalize(),
                                "description": info.get("description", ""), "readme": readme,
                                "source": info.get("source"), "imported": info.get("imported"),
                                "hidden": list(info.get("hidden") or [])}
        return out

    @staticmethod
    def _program_info(folder: Path) -> dict[str, Any]:
        try:
            info = json.loads((folder / PROGRAM_FILE).read_text(encoding="utf-8"))
            return info if isinstance(info, dict) else {}
        except (OSError, ValueError):
            return {}

    def set_hidden(self, folder: str, hide: set[str], show: set[str] = frozenset()) -> list[str]:
        """Hide or show a program's scripts on the Tools screen (they stay in the program)."""
        path = self.scripts / folder
        if not path.is_dir() or folder.startswith(("_", ".")) or "/" in folder or "\\" in folder:
            raise LookupError(f"There's no program folder called {folder}.")
        info = self._program_info(path)
        hidden = (set(info.get("hidden") or []) | set(hide)) - set(show)
        info["hidden"] = sorted(hidden)
        (path / PROGRAM_FILE).write_text(json.dumps(info, indent=1, ensure_ascii=False), encoding="utf-8")
        return info["hidden"]

    def find(self, query: str) -> Tool:
        """Find a tool by file name (without .py) or by its display name."""
        tools, problems = self.tools()
        q = query.strip().lower().removesuffix(".py")
        for t in tools:
            if t.id.lower() == q or t.name.lower() == q:
                return t
        for p in problems:
            if p.path.stem.lower() == q:
                raise LabelError(f"{p.path.name} can't be used yet: {p.message}")
        names = ", ".join(t.name for t in tools) or "none yet"
        raise LookupError(f"No tool called '{query}'. Tools you have: {names}.")


PROGRAM_FILE = ".trapyze-program.json"
SKIP_DIRS = {".venv", "venv", "env", "__pycache__", ".git", "node_modules", ".idea", ".vscode", ".pytest_cache",
             ".mypy_cache", "dist", "build", ".ipynb_checkpoints"}


def _program_files(folder: Path):
    for path in folder.rglob("*.py"):
        rel = path.relative_to(folder).parts
        if any(part in SKIP_DIRS or part.startswith((".", "_")) for part in rel[:-1]) or path.name.startswith("."):
            continue
        yield path


def program_tool_id(folder: Path, path: Path) -> str:
    """scripts/price_db/price_db.py is "price_db"; scripts/price_db/fixes/hwm.py is "price_db.fixes.hwm"."""
    rel = path.relative_to(folder).with_suffix("")
    if rel.parts == (folder.name,):
        return folder.name
    return ".".join((folder.name, *rel.parts))


def _copy_missing(source, target: Path, refresh: bool = False) -> list[Path]:
    """Copy files that aren't there yet. With refresh, also replace traPYze's own
    files (the helper) when this version of traPYze has a newer one."""
    added = []
    for item in source.iterdir():
        if not item.name.endswith(".py"):
            continue
        dest = target / item.name
        if dest.exists():
            if not refresh or dest.read_bytes() == item.read_bytes():
                continue
        with resources.as_file(item) as real:
            shutil.copyfile(real, dest)
        added.append(dest)
    return added

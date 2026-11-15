"""Package versions per tool: pin them, check for updates, update after a test, go back.

uv does the work. `uv lock --script tool.py` writes tool.py.lock next to the
script with exact versions, and `uv run --script` then always uses those
versions: a tool keeps working the same until you choose to update.

An update is never made in place. traPYze copies the script to a scratch
folder, lets uv pick the newer versions there, and tests them by installing
them and importing the tool's packages (without running the tool itself, so
no data is touched). Only when that works does the new lock replace the old
one, and the old one is kept so you can go back with one click.
"""

from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

from .home import Home
from .label import Tool
from .runner import find_engine

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10
    tomllib = None  # type: ignore[assignment]

HISTORY_KEEP = 8
CHECK_EVERY = 20 * 3600


class PackageProblem(RuntimeError):
    """An update or lock that didn't work, in plain words."""


def lock_path(tool: Tool) -> Path:
    return tool.path.with_name(tool.path.name + ".lock")


def read_lock(path: Path) -> dict[str, str]:
    """{package: version} from a uv lock file."""
    if not path.exists() or tomllib is None:
        return {}
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {p["name"]: str(p.get("version", "")) for p in data.get("package", []) if "name" in p}


def _stamp() -> str:
    """Sortable and unique, also for two changes within one second."""
    now = time.time_ns()  # one reading of the clock, so seconds and fraction always match
    return time.strftime("%Y%m%d-%H%M%S", time.localtime(now // 1_000_000_000)) + f"-{now % 1_000_000_000:09d}"


def package_name(requirement: str) -> str:
    """"pandas>=2" -> "pandas"; names compare without case, - and _ alike."""
    return re.split(r"[\s<>=!~;\[(@]", requirement.strip(), maxsplit=1)[0].lower().replace("_", "-")


def diff(old: dict[str, str], new: dict[str, str]) -> list[dict[str, str | None]]:
    names = sorted(set(old) | set(new), key=str.lower)
    return [{"name": n, "old": old.get(n), "new": new.get(n)} for n in names if old.get(n) != new.get(n)]


def _script_block(source: str) -> str:
    lines, out, inside = source.splitlines(), [], False
    for line in lines:
        if line.strip() == "# /// script":
            inside = True
        if inside:
            out.append(line)
            if line.strip() == "# ///" and len(out) > 1:
                break
    return "\n".join(out) + "\n" if out else ""


def _imports(tool: Tool) -> list[str]:
    """The tool's own top-level imports of installed packages (also through its helper files)."""
    import sys

    stdlib = set(getattr(sys, "stdlib_module_names", ())) | {"__future__", "trapyze_helper"}
    folder = tool.path.parent
    local = {p.stem for p in folder.glob("*.py")}
    seen_files: set[Path] = set()
    found: list[str] = []

    def visit(path: Path) -> None:
        if path in seen_files or not path.exists():
            return
        seen_files.add(path)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            return
        for node in tree.body:  # module level only: what runs on import
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names = [node.module]
            elif isinstance(node, (ast.Try, ast.If)):
                continue  # optional imports: don't require them
            for name in names:
                top = name.split(".")[0]
                if top in local:
                    visit(folder / f"{top}.py")
                elif top not in stdlib and name not in found:
                    found.append(name)
    visit(tool.path)
    return found


class Packages:
    def __init__(self, home: Home, run: Callable[..., subprocess.CompletedProcess] | None = None,
                 engine: str | None = None):
        self.home = home
        self.state_path = home.internal / "packages.json"
        self.history_root = home.internal / "lock-history"
        self._engine = engine
        self._run = run or (lambda cmd, **kw: subprocess.run(
            cmd, capture_output=True, text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), **kw))

    @property
    def engine(self) -> str:
        uv = self._engine or find_engine()
        if not uv:
            raise PackageProblem("uv (the engine that installs packages) isn't installed, so versions can't be pinned.")
        return uv

    # State ------------------------------------------------------------------
    def _state(self) -> dict[str, Any]:
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save(self, tool_id: str, **changes: Any) -> None:
        data = self._state()
        data.setdefault(tool_id, {}).update(changes)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(data, indent=1), encoding="utf-8")

    def history(self, tool: Tool) -> list[Path]:
        folder = self.history_root / tool.id.replace("/", "_")
        return sorted(folder.glob("*.lock"), reverse=True) if folder.exists() else []

    def status(self, tool: Tool) -> dict[str, Any]:
        lock = lock_path(tool)
        saved = self._state().get(tool.id, {})
        pinned = read_lock(lock)
        wanted = {package_name(d) for d in tool.dependencies}
        return {
            "needs_packages": bool(tool.dependencies),
            "locked": lock.exists(),
            "pinned": [{"name": n, "version": v, "direct": package_name(n) in wanted}
                       for n, v in sorted(pinned.items(), key=lambda x: x[0].lower())],
            "updates": saved.get("updates", []) if lock.exists() else [],
            "checked": saved.get("checked"),
            "error": saved.get("error", ""),
            "last_change": saved.get("last_change"),
            "can_go_back": bool(self.history(tool)),
        }

    def summary(self, tool: Tool) -> dict[str, Any]:
        s = self.status(tool)
        return {"locked": s["locked"], "updates": len(s["updates"]), "error": s["error"], "needs_packages": s["needs_packages"]}

    # Work -------------------------------------------------------------------
    def _uv(self, args: list[str], cwd: Path, timeout: int = 900) -> subprocess.CompletedProcess:
        try:
            done = self._run([self.engine, *args], cwd=str(cwd), timeout=timeout)
        except subprocess.TimeoutExpired:
            raise PackageProblem("uv took too long (more than 15 minutes). Check the internet connection and try again.") from None
        except OSError as exc:
            raise PackageProblem(f"uv couldn't start: {exc}") from None
        return done

    @staticmethod
    def _explain(done: subprocess.CompletedProcess) -> str:
        text = (done.stderr or done.stdout or "").strip()
        lines = [x for x in text.splitlines() if x.strip() and "UV_NATIVE_TLS" not in x]
        low = text.lower()
        if "failed to fetch" in low or "dns" in low or "connect" in low and "error" in low:
            return "uv couldn't reach the package index. Check the internet connection."
        if "no solution found" in low or "unsatisfiable" in low:
            return "uv found no combination of versions that fits the tool's packages: " + " ".join(lines[-3:])
        return " ".join(lines[-4:])[:600] or f"uv stopped with code {done.returncode}."

    def _prepare(self, tool: Tool, upgrade: bool, scratch: Path) -> Path:
        """A new lock in a scratch folder; the tool's own files aren't touched."""
        copy = scratch / tool.path.name
        shutil.copy2(tool.path, copy)
        if lock_path(tool).exists():
            shutil.copy2(lock_path(tool), scratch / (tool.path.name + ".lock"))
        args = ["lock", "--script", copy.name] + (["--upgrade"] if upgrade else [])
        done = self._uv(args, scratch)
        new = scratch / (tool.path.name + ".lock")
        if done.returncode != 0 or not new.exists():
            raise PackageProblem(self._explain(done))
        return new

    def _test(self, tool: Tool, lock: Path, scratch: Path) -> None:
        """Install the locked versions and import the tool's packages. The tool itself doesn't run."""
        imports = _imports(tool)
        block = _script_block(tool.path.read_text(encoding="utf-8", errors="replace"))
        test = scratch / "trapyze_package_test.py"
        body = "".join(f"import {name}\n" for name in imports) + 'print("traPYze package test: ok")\n'
        test.write_text(block + body, encoding="utf-8")
        shutil.copy2(lock, scratch / (test.name + ".lock"))
        done = self._uv(["run", "--frozen", "--script", test.name], scratch)
        if done.returncode != 0 or "traPYze package test: ok" not in (done.stdout or ""):
            raise PackageProblem("The new versions didn't pass the test, so nothing changed. " + self._explain(done))

    def _install(self, tool: Tool, new_lock: Path, reason: str) -> list[dict[str, Any]]:
        current = lock_path(tool)
        before = read_lock(current)
        folder = self.history_root / tool.id.replace("/", "_")
        folder.mkdir(parents=True, exist_ok=True)
        stamp = _stamp()
        if current.exists():
            shutil.copy2(current, folder / f"{stamp}.lock")
        else:
            (folder / f"{stamp}.lock").write_text("# not pinned before\n", encoding="utf-8")
        for old in self.history(tool)[HISTORY_KEEP:]:
            old.unlink(missing_ok=True)
        shutil.copy2(new_lock, current)
        changes = diff(before, read_lock(current))
        self._save(tool.id, updates=[], last_change={"at": time.time(), "what": reason, "changes": changes}, error="")
        return changes

    def lock(self, tool: Tool) -> list[dict[str, Any]]:
        if not tool.dependencies:
            raise PackageProblem(f"{tool.name} doesn't need extra packages, so there's nothing to pin.")
        with tempfile.TemporaryDirectory(prefix="trapyze-lock-") as tmp:
            new = self._prepare(tool, upgrade=False, scratch=Path(tmp))
            self._test(tool, new, Path(tmp))
            return self._install(tool, new, "pinned")

    def check(self, tool: Tool) -> list[dict[str, Any]]:
        """Which newer versions exist (nothing is changed)."""
        if not lock_path(tool).exists():
            return []
        try:
            with tempfile.TemporaryDirectory(prefix="trapyze-check-") as tmp:
                new = self._prepare(tool, upgrade=True, scratch=Path(tmp))
                updates = diff(read_lock(lock_path(tool)), read_lock(new))
        except PackageProblem as exc:
            self._save(tool.id, checked=time.time(), error=str(exc))
            raise
        self._save(tool.id, checked=time.time(), updates=updates, error="")
        return updates

    def update(self, tool: Tool) -> list[dict[str, Any]]:
        if not lock_path(tool).exists():
            return self.lock(tool)
        with tempfile.TemporaryDirectory(prefix="trapyze-update-") as tmp:
            new = self._prepare(tool, upgrade=True, scratch=Path(tmp))
            if read_lock(new) == read_lock(lock_path(tool)):
                self._save(tool.id, updates=[], checked=time.time(), error="")
                return []
            self._test(tool, new, Path(tmp))
            return self._install(tool, new, "updated")

    def go_back(self, tool: Tool) -> list[dict[str, Any]]:
        history = self.history(tool)
        if not history:
            raise PackageProblem("There's no earlier version to go back to.")
        previous = history[0]
        current = lock_path(tool)
        before = read_lock(current)
        if previous.read_text(encoding="utf-8").startswith("# not pinned before"):
            current.unlink(missing_ok=True)
        else:
            shutil.copy2(previous, current)
        previous.unlink()
        changes = diff(before, read_lock(current))
        self._save(tool.id, updates=[], last_change={"at": time.time(), "what": "went back", "changes": changes}, error="")
        return changes

    def unpin(self, tool: Tool) -> None:
        current = lock_path(tool)
        if current.exists():
            folder = self.history_root / tool.id.replace("/", "_")
            folder.mkdir(parents=True, exist_ok=True)
            shutil.move(str(current), str(folder / f"{_stamp()}.lock"))
        self._save(tool.id, updates=[], last_change={"at": time.time(), "what": "unpinned", "changes": []}, error="")

    def check_all(self, tools: list[Tool], force: bool = False) -> None:
        """The daily look for newer versions (only for tools whose versions are pinned)."""
        state = self._state()
        for tool in tools:
            if not lock_path(tool).exists():
                continue
            if not force and time.time() - (state.get(tool.id, {}).get("checked") or 0) < CHECK_EVERY:
                continue
            try:
                self.check(tool)
            except PackageProblem:
                pass

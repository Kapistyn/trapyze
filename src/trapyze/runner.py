"""Run a tool in the background and report what happens, in plain events.

The runner:
  1. checks the chosen settings against the tool's label,
  2. locks any shared data the tool writes,
  3. starts the script through the engine (uv), in its own output folder,
  4. turns `@@trapyze ...` lines into progress events and keeps a full log,
  5. records the run (settings, time, result, files) in the history.

Progress protocol, printed by a script on its own line:
    @@trapyze progress 0.4 Downloading prices
    @@trapyze step Calculating the ranking
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .explain import Explanation, explain
from .home import Home
from .label import Tool
from .locks import Locks
from .vault import mask

MARKER = "@@trapyze"
TAIL_LINES = 40


class EngineMissing(RuntimeError):
    """The tool needs packages, and uv isn't available to install them."""


@dataclass
class Event:
    kind: str  # started | output | progress | step | finished
    message: str = ""
    fraction: float | None = None
    line: str = ""


@dataclass
class RunResult:
    run_id: str
    tool_id: str
    tool_name: str
    tool_version: str
    status: str  # done | warning | failed | stopped
    settings: dict[str, Any]
    started: str
    ended: str
    seconds: float
    exit_code: int | None
    output_dir: str | None
    files: list[str] = field(default_factory=list)
    cause: str = ""
    action: str = ""
    log: str = ""

    @property
    def ok(self) -> bool:
        """The tool finished its job (possibly with warnings worth a look)."""
        return self.status in ("done", "warning")


def official_uv_places() -> list[Path]:
    """Where uv's own installer puts uv (newest first). Other programs sometimes bring a copy
    of uv of their own; those come later on the PATH and are only used when there's no other."""
    name = "uv.exe" if os.name == "nt" else "uv"
    places = [Path.home() / ".local" / "bin" / name]
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        places.append(Path(os.environ["LOCALAPPDATA"]) / "Programs" / "uv" / name)
    places.append(Path.home() / ".cargo" / "bin" / name)
    return places


def find_engine() -> str | None:
    """The uv executable: TRAPYZE_UV, then one bundled next to Python, then the official uv, then PATH."""
    explicit = os.environ.get("TRAPYZE_UV")
    if explicit and Path(explicit).is_file():
        return explicit
    beside = Path(sys.executable).parent / ("uv.exe" if os.name == "nt" else "uv")
    if beside.is_file():
        return str(beside)
    for place in official_uv_places():
        if place.is_file():
            return str(place)
    return shutil.which("uv")


def build_command(tool: Tool, values: dict[str, Any], engine: str | None) -> list[str]:
    """The command line for a run. Arguments follow the order of the label,
    so options that must come before a command (like --db) stay in front."""
    args: list[str] = []
    for s in tool.settings:
        value = values.get(s.key)
        if value is None:
            continue
        if s.switch:
            if value:
                args.append(s.option)
            continue
        if isinstance(value, bool):
            value = "true" if value else "false"
        elif isinstance(value, float) and value.is_integer():
            value = int(value)
        if s.positional:
            args.append(str(value))
        else:
            args += [s.option, str(value)]
    script = str(tool.path.resolve())
    if engine:
        return [engine, "run", "--quiet", "--script", script, *args]
    if tool.dependencies:
        raise EngineMissing(
            f"{tool.name} needs extra packages ({', '.join(tool.dependencies)}), "
            "and the engine that installs them (uv) isn't available."
        )
    return [sys.executable, script, *args]


def _parse(line: str) -> Event:
    text = line.rstrip("\r\n")
    if not text.startswith(MARKER):
        return Event("output", line=text)
    parts = text[len(MARKER):].strip().split(" ", 2)
    kind = parts[0] if parts else ""
    if kind == "progress" and len(parts) >= 2:
        try:
            fraction = max(0.0, min(1.0, float(parts[1])))
        except ValueError:
            return Event("output", line=text)
        return Event("progress", message=parts[2] if len(parts) > 2 else "", fraction=fraction, line=text)
    if kind == "step":
        return Event("step", message=" ".join(parts[1:]), line=text)
    return Event("output", line=text)


class Run:
    """One run of one tool. Start it, watch its events, wait or cancel."""

    def __init__(self, home: Home, tool: Tool, chosen: dict[str, Any] | None = None, engine: str | None = "auto",
                 extra_env: dict[str, str] | None = None, secrets: list[str] | None = None):
        """extra_env: variables from the vault for this run. secrets: values to blank out of all output."""
        self.home = home
        self.tool = tool
        self.extra_env = dict(extra_env or {})
        self.secrets = sorted(set(secrets or []), key=len, reverse=True)
        self.started_at = datetime.now()
        stamp = self.started_at.strftime("%Y-%m-%d_%H-%M-%S")
        # Output folders are for people: readable to the second. Run records are
        # for sorting: precise to the microsecond, so history order is exact.
        self.output_dir = _unique(home.outputs / tool.id / stamp)
        self.run_dir = _unique(home.runs / f"{self.started_at:%Y-%m-%d_%H-%M-%S-%f}_{tool.id}")
        self.run_id = self.run_dir.name
        places = {
            "data": str(home.data.resolve()),
            "output": str(self.output_dir.resolve()),
            "home": str(home.root.resolve()),
            "lib": str(home.lib.resolve()),
            "script_dir": str(tool.path.resolve().parent),
        }
        self.values = tool.resolve(chosen, places)  # raises SettingError before anything starts
        self.engine = find_engine() if engine == "auto" else engine
        self.command = build_command(tool, self.values, self.engine)
        self._proc: subprocess.Popen[str] | None = None
        self._thread: threading.Thread | None = None
        self._cancelled = threading.Event()
        self._done = threading.Event()
        self._tail: deque[str] = deque(maxlen=TAIL_LINES)
        self._locks: list[Path] = []
        self.result: RunResult | None = None
        self.fraction: float | None = None
        self.step: str = ""

    # Public ------------------------------------------------------------------
    def start(self, on_event: Callable[[Event], None] | None = None) -> "Run":
        notify = on_event or (lambda e: None)
        self._locks = Locks(self.home.locks).acquire(self.tool.writes, owner=self.tool.name)
        try:
            self.output_dir.mkdir(parents=True)
            self.run_dir.mkdir(parents=True)
            self._write_record(status="running")
            self._proc = subprocess.Popen(
                self.command,
                cwd=self.output_dir,
                env=self._environment(),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                **_new_group(),
            )
        except BaseException:
            Locks.release(self._locks)
            raise
        notify(Event("started", message=f"{self.tool.name} started"))
        self._thread = threading.Thread(target=self._follow, args=(notify,), daemon=True)
        self._thread.start()
        return self

    def wait(self, timeout: float | None = None) -> RunResult | None:
        self._done.wait(timeout)
        return self.result

    def cancel(self) -> None:
        self._cancelled.set()
        if self._proc and self._proc.poll() is None:
            _stop_tree(self._proc)

    @property
    def running(self) -> bool:
        return not self._done.is_set()

    # Internals ---------------------------------------------------------------
    def _environment(self) -> dict[str, str]:
        env = dict(os.environ)
        lib = str(self.home.lib.resolve())
        env["PYTHONPATH"] = lib + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        env["TRAPYZE_HOME"] = str(self.home.root.resolve())
        env["TRAPYZE_TOOL"] = self.tool.id
        env["TRAPYZE_RUN_ID"] = self.run_id
        env["TRAPYZE_OUTPUT_DIR"] = str(self.output_dir.resolve())
        env["TRAPYZE_DATA_DIR"] = str(self.home.data.resolve())
        env["TRAPYZE_API_DB"] = str((self.home.internal / "api.sqlite").resolve())
        env["TRAPYZE_SETTINGS"] = json.dumps(self.values)
        env.update(self.extra_env)
        return env

    def _follow(self, notify: Callable[[Event], None]) -> None:
        assert self._proc and self._proc.stdout
        log_path = self.run_dir / "log.txt"
        try:
            with log_path.open("w", encoding="utf-8") as log:
                for raw in self._proc.stdout:
                    if self.secrets:
                        raw = mask(raw, self.secrets)
                    log.write(raw)
                    log.flush()
                    event = _parse(raw)
                    if event.kind == "output":
                        self._tail.append(event.line)
                    elif event.kind == "progress":
                        self.fraction = event.fraction
                        if event.message:
                            self.step = event.message
                    elif event.kind == "step":
                        self.step = event.message
                    notify(event)
            code = self._proc.wait()
        finally:
            self._proc.stdout.close()
            Locks.release(self._locks)
        self.result = self._finish(code)
        notify(Event("finished", message=self.result.status))
        self._done.set()

    def _finish(self, code: int | None) -> RunResult:
        ended = datetime.now()
        cancelled = self._cancelled.is_set()
        if cancelled:
            status = "stopped"
        elif code == 0:
            status = "done"
        elif code in self.tool.warning_codes:
            status = "warning"
        else:
            status = "failed"
        files = _list_files(self.output_dir)
        if not files:
            _remove_empty(self.output_dir)
        if status == "done":
            why = Explanation("", "")
        elif status == "warning":
            last = next((line.strip() for line in reversed(self._tail) if line.strip()), "")
            why = Explanation(
                "Finished, with warnings worth a look." + (f" The last message was: {last}" if last else ""),
                "Read the tool's output or log to see what it flagged.",
            )
        else:
            why = explain(code, list(self._tail), cancelled)
        result = RunResult(
            run_id=self.run_id,
            tool_id=self.tool.id,
            tool_name=self.tool.name,
            tool_version=self.tool.version,
            status=status,
            settings=self.values,
            started=self.started_at.isoformat(timespec="seconds"),
            ended=ended.isoformat(timespec="seconds"),
            seconds=round((ended - self.started_at).total_seconds(), 2),
            exit_code=code,
            output_dir=str(self.output_dir) if files else None,
            files=files,
            cause=why.cause,
            action=why.action,
            log=str(self.run_dir / "log.txt"),
        )
        self._write_record(result=result)
        return result

    def _write_record(self, status: str | None = None, result: RunResult | None = None) -> None:
        if result is not None:
            record = asdict(result)
        else:
            record = {
                "run_id": self.run_id,
                "tool_id": self.tool.id,
                "tool_name": self.tool.name,
                "tool_version": self.tool.version,
                "status": status,
                "settings": self.values,
                "started": self.started_at.isoformat(timespec="seconds"),
                "command": self.command,
                "connections": self.tool.connections,
            }
        path = self.run_dir / "record.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(record, indent=2), encoding="utf-8")
        os.replace(tmp, path)


def run_tool(home: Home, tool: Tool, chosen: dict[str, Any] | None = None, on_event=None, engine="auto") -> RunResult:
    """Run a tool and wait for it. Convenience for scripts and tests."""
    run = Run(home, tool, chosen, engine=engine).start(on_event)
    result = run.wait()
    assert result is not None
    return result


def history(home: Home, tool_id: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    """Recent runs, newest first. Runs still going show status 'running'."""
    records = []
    if not home.runs.is_dir():
        return records
    for folder in sorted(home.runs.iterdir(), reverse=True):
        path = folder / "record.json"
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if tool_id and record.get("tool_id") != tool_id:
            continue
        records.append(record)
        if len(records) >= limit:
            break
    return records


# Helpers -------------------------------------------------------------------
def _unique(path: Path) -> Path:
    if not path.exists():
        return path
    n = 2
    while (candidate := path.with_name(f"{path.name}_{n}")).exists():
        n += 1
    return candidate


def _list_files(folder: Path) -> list[str]:
    if not folder.is_dir():
        return []
    return sorted(str(p.relative_to(folder)) for p in folder.rglob("*") if p.is_file())


def _remove_empty(folder: Path) -> None:
    try:
        folder.rmdir()
        folder.parent.rmdir()  # the tool's folder, if this was its only run
    except OSError:
        pass


def _new_group() -> dict[str, Any]:
    if os.name == "nt":  # pragma: no cover - Windows only
        # No console window pops up per run, also when traPYze itself has none (the app).
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW}
    return {"start_new_session": True}


def _stop_tree(proc: subprocess.Popen) -> None:
    """Stop the engine and the script it started, gently first."""
    if os.name == "nt":  # pragma: no cover - Windows only
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True,
                       creationflags=subprocess.CREATE_NO_WINDOW)
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return
        time.sleep(0.1)
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass

"""Small JSON files in .trapyze/: presets, chains and the look of the window.

None of this touches the scripts themselves: a tool's file stays exactly as
its author wrote it.
"""

from __future__ import annotations

import base64
import json
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .label import SettingError

_lock = threading.RLock()
NAME_MAX = 60
THEMES = ("auto", "light", "dark")
ACCENTS = ("blue", "teal", "purple", "orange", "rose", "slate")
COLORS = ACCENTS
ICONS = ("chart", "database", "document", "table", "globe", "photo", "archive", "bell", "mail", "coin", "terminal",
         "rocket", "bolt", "flask", "gauge", "shield", "trend", "target", "calendar", "cloud", "cube", "heart", "star", "link")
IMAGE_TYPES = {b"\x89PNG\r\n\x1a\n": "png", b"\xff\xd8\xff": "jpg", b"RIFF": "webp"}
IMAGE_MAX = 300 * 1024


class StoreError(ValueError):
    """A plain-words problem with a preset, chain or look."""


def _read(path: Path, empty: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return empty


def _write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _clean_name(name: str, what: str) -> str:
    name = " ".join(str(name or "").split())
    if not name:
        raise StoreError(f"Give the {what} a name.")
    if len(name) > NAME_MAX:
        raise StoreError(f"Keep the {what}'s name under {NAME_MAX} characters.")
    return name


# Presets -------------------------------------------------------------------
class Presets:
    """Named settings per tool: {tool_id: {name: settings}}."""

    def __init__(self, internal: Path):
        self.path = internal / "presets.json"

    def all(self) -> dict[str, dict[str, dict[str, Any]]]:
        return _read(self.path, {})

    def for_tool(self, tool_id: str) -> dict[str, dict[str, Any]]:
        return self.all().get(tool_id, {})

    def get(self, tool_id: str, name: str) -> dict[str, Any]:
        found = self.for_tool(tool_id).get(name)
        if found is None:
            raise StoreError(f"There's no preset called '{name}' for this tool.")
        return dict(found)

    def save(self, tool, name: str, settings: dict[str, Any]) -> None:
        name = _clean_name(name, "preset")
        tool.resolve(settings)  # only valid settings are saved; raises SettingError
        with _lock:
            data = self.all()
            data.setdefault(tool.id, {})[name] = settings
            _write(self.path, data)

    def delete(self, tool_id: str, name: str) -> None:
        with _lock:
            data = self.all()
            if data.get(tool_id, {}).pop(name, None) is None:
                raise StoreError(f"There's no preset called '{name}'.")
            if not data[tool_id]:
                del data[tool_id]
            _write(self.path, data)


# Chains --------------------------------------------------------------------
@dataclass
class Step:
    tool: str
    use: str = "last"  # "standard", "last" (what was used last time) or "preset:<name>"

    def describe(self) -> str:
        if self.use == "standard":
            return "standard settings"
        if self.use == "last":
            return "settings used last time"
        if self.use == "custom":
            return "the settings you chose"
        return f"preset “{self.use.removeprefix('preset:')}”"


@dataclass
class Chain:
    id: str
    name: str
    steps: list[Step]
    on_problem: str = "stop"  # or "continue"
    description: str = ""
    icon: str = "link"
    color: str = "purple"

    def to_json(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "description": self.description, "icon": self.icon,
                "color": self.color, "on_problem": self.on_problem,
                "steps": [{"tool": s.tool, "use": s.use} for s in self.steps]}


class Chains:
    def __init__(self, internal: Path):
        self.path = internal / "chains.json"

    def all(self) -> list[Chain]:
        out = []
        for c in _read(self.path, {"chains": []}).get("chains", []):
            try:
                out.append(Chain(c["id"], c["name"], [Step(s["tool"], s.get("use", "last")) for s in c["steps"]],
                                 c.get("on_problem", "stop"), c.get("description", ""), c.get("icon", "link"),
                                 c.get("color", "purple")))
            except (KeyError, TypeError):
                continue
        return out

    def get(self, ref: str) -> Chain:
        q = ref.strip().lower()
        for c in self.all():
            if c.id == ref or c.name.lower() == q:
                return c
        names = ", ".join(c.name for c in self.all()) or "none yet"
        raise StoreError(f"No chain called '{ref}'. Chains you have: {names}.")

    def save(self, body: dict[str, Any], tools: list, presets: Presets) -> Chain:
        name = _clean_name(body.get("name", ""), "chain")
        known = {t.id: t for t in tools}
        steps = []
        for i, raw in enumerate(body.get("steps") or [], 1):
            tool_id, use = str(raw.get("tool", "")), str(raw.get("use") or "last")
            if tool_id not in known:
                raise StoreError(f"Step {i}: choose a tool.")
            if use.startswith("preset:"):
                if use.removeprefix("preset:") not in presets.for_tool(tool_id):
                    raise StoreError(f"Step {i}: {known[tool_id].name} has no preset “{use.removeprefix('preset:')}”.")
            elif use not in ("standard", "last"):
                raise StoreError(f"Step {i}: choose which settings to use.")
            steps.append(Step(tool_id, use))
        if not steps:
            raise StoreError("A chain needs at least one step.")
        if len(steps) > 30:
            raise StoreError("A chain can have at most 30 steps.")
        on_problem = "continue" if body.get("on_problem") == "continue" else "stop"
        icon = body.get("icon") if body.get("icon") in ICONS else "link"
        color = body.get("color") if body.get("color") in COLORS else "purple"
        with _lock:
            chains = self.all()
            chain_id = str(body.get("id") or "")
            if any(c.name.lower() == name.lower() and c.id != chain_id for c in chains):
                raise StoreError(f"There's already a chain called '{name}'.")
            if chain_id and not any(c.id == chain_id for c in chains):
                raise StoreError("That chain doesn't exist any more.")
            chain = Chain(chain_id or uuid.uuid4().hex[:10], name, steps, on_problem,
                          str(body.get("description") or "")[:200], icon, color)
            chains = [chain if c.id == chain.id else c for c in chains] if chain_id else chains + [chain]
            _write(self.path, {"chains": [c.to_json() for c in chains]})
        return chain

    def delete(self, chain_id: str) -> None:
        with _lock:
            chains = self.all()
            kept = [c for c in chains if c.id != chain_id]
            if len(kept) == len(chains):
                raise StoreError("That chain doesn't exist any more.")
            _write(self.path, {"chains": [c.to_json() for c in kept]})


def step_settings(step: Step, presets: Presets, remembered: dict[str, dict]) -> dict[str, Any]:
    if step.use == "standard":
        return {}
    if step.use == "last":
        return dict(remembered.get(step.tool) or {})
    return presets.get(step.tool, step.use.removeprefix("preset:"))


class ChainRun:
    """Runs the steps one after another in the background.

    `start(tool_id, settings)` must start a run and return an object with
    .run_id and .wait() (a runner.Run); it may raise for a step that can't start.
    """

    def __init__(self, chain: Chain, settings: list[dict[str, Any]], names: dict[str, str],
                 start: Callable[[str, dict[str, Any]], Any], busy_wait: float = 1800,
                 on_done: Callable[["ChainRun"], Any] | None = None):
        self.id = uuid.uuid4().hex[:12]
        self.chain = chain
        self.settings = settings
        self.start_fn = start
        self.on_done = on_done
        self.busy_wait = busy_wait
        self.started = time.time()
        self.ended: float | None = None
        self.status = "running"  # running, done, warning, failed, stopped
        self.steps = [{"tool": s.tool, "name": names.get(s.tool, s.tool), "use": s.describe(), "status": "waiting",
                       "run_id": None, "message": ""} for s in chain.steps]
        self.current = 0
        self._stop = threading.Event()
        self._run = None
        self._thread = threading.Thread(target=self._go, name=f"chain-{self.id}", daemon=True)

    def begin(self) -> "ChainRun":
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        run = self._run
        if run is not None:
            run.cancel()

    def wait(self, timeout: float | None = None) -> str:
        self._thread.join(timeout)
        return self.status

    def summary(self) -> dict[str, Any]:
        return {"id": self.id, "chain": self.chain.id, "name": self.chain.name, "status": self.status,
                "started": self.started, "ended": self.ended, "current": self.current, "steps": self.steps,
                "on_problem": self.chain.on_problem}

    def _go(self) -> None:
        from .locks import Busy  # local import: locks imports nothing from here, but keep start-up light

        problem = False
        for i, step in enumerate(self.steps):
            self.current = i
            if self._stop.is_set():
                step["status"] = "skipped"
                continue
            if problem and self.chain.on_problem == "stop":
                step["status"] = "skipped"
                step["message"] = "Skipped because an earlier step had a problem."
                continue
            step["status"] = "running"
            waited = 0.0
            while True:
                try:
                    self._run = self.start_fn(step["tool"], self.settings[i])
                    break
                except Busy as exc:  # shared data in use by another run: wait our turn
                    if waited >= self.busy_wait or self._stop.is_set():
                        step["status"], step["message"] = "failed", str(exc)
                        break
                    step["message"] = f"Waiting: {exc}"
                    time.sleep(2)
                    waited += 2
                except (SettingError, StoreError, LookupError, ValueError, OSError, RuntimeError) as exc:
                    step["status"], step["message"] = "failed", str(exc)
                    break
            if step["status"] == "failed":
                problem = True
                continue
            step["run_id"] = self._run.run_id
            step["message"] = ""
            result = self._run.wait()
            self._run = None
            step["status"] = result.status if result else "failed"
            if result and result.cause:
                step["message"] = result.cause
            if step["status"] in ("failed", "stopped"):
                problem = True
                if step["status"] == "stopped":
                    self._stop.set()
        statuses = [s["status"] for s in self.steps]
        if self._stop.is_set():
            self.status = "stopped"
        elif "failed" in statuses or "skipped" in statuses:
            self.status = "failed"
        elif "warning" in statuses:
            self.status = "warning"
        else:
            self.status = "done"
        self.ended = time.time()
        if self.on_done:
            try:
                self.on_done(self)
            except Exception:
                pass


# Look and feel ------------------------------------------------------------
WINDOW_SIZES = ("maximized", "fullscreen", "normal")


class Looks:
    """{"theme", "accent", "density", "celebrate", "tools": {tool_id: {"icon", "color", "image"}}}"""

    DEFAULT = {"theme": "auto", "accent": "blue", "density": "comfortable", "celebrate": True,
               "window": "app", "window_size": "maximized", "notify": True, "keep_button": False, "editor": "", "tools": {}}

    def __init__(self, internal: Path):
        self.path = internal / "looks.json"
        self.images = internal / "icons"

    def get(self) -> dict[str, Any]:
        data = {**self.DEFAULT, **_read(self.path, {})}
        data["tools"] = dict(data.get("tools") or {})
        return data

    def update(self, body: dict[str, Any]) -> dict[str, Any]:
        with _lock:
            data = self.get()
            if "theme" in body:
                if body["theme"] not in THEMES:
                    raise StoreError("Choose light, dark or match the computer.")
                data["theme"] = body["theme"]
            if "accent" in body:
                if body["accent"] not in ACCENTS:
                    raise StoreError("Unknown accent colour.")
                data["accent"] = body["accent"]
            if "density" in body:
                if body["density"] not in ("comfortable", "compact"):
                    raise StoreError("Choose comfortable or compact.")
                data["density"] = body["density"]
            if "celebrate" in body:
                data["celebrate"] = bool(body["celebrate"])
            if "window" in body:
                if body["window"] not in ("app", "browser"):
                    raise StoreError("Choose its own window or the browser.")
                data["window"] = body["window"]
            if "window_size" in body:
                if body["window_size"] not in WINDOW_SIZES:
                    raise StoreError("Choose filling the screen, full screen or normal size.")
                data["window_size"] = body["window_size"]
            if "notify" in body:
                data["notify"] = bool(body["notify"])
            if "keep_button" in body:
                data["keep_button"] = bool(body["keep_button"])
            if "editor" in body:
                data["editor"] = str(body["editor"] or "")[:40]
            _write(self.path, data)
            return data

    def set_tool(self, tool_id: str, icon: str | None, color: str | None) -> dict[str, Any]:
        if icon is not None and icon not in ICONS:
            raise StoreError("Unknown icon.")
        if color is not None and color not in COLORS:
            raise StoreError("Unknown colour.")
        with _lock:
            data = self.get()
            look = dict(data["tools"].get(tool_id) or {})
            for k, v in (("icon", icon), ("color", color)):
                if v is None:
                    look.pop(k, None)
                else:
                    look[k] = v
            data["tools"][tool_id] = look
            if not look:
                del data["tools"][tool_id]
            _write(self.path, data)
            return data

    def reset_tool(self, tool_id: str) -> dict[str, Any]:
        self.remove_image(tool_id)
        with _lock:
            data = self.get()
            data["tools"].pop(tool_id, None)
            _write(self.path, data)
            return data

    def image_path(self, tool_id: str) -> Path | None:
        if not re.match(r"^[\w.-]+$", tool_id):
            return None
        for ext in ("png", "jpg", "webp"):
            p = self.images / f"{tool_id}.{ext}"
            if p.exists():
                return p
        return None

    def set_image(self, tool_id: str, data_url: str) -> None:
        if not re.match(r"^[\w.-]+$", tool_id):
            raise StoreError("Unknown tool.")
        m = re.match(r"^data:image/[\w+.-]+;base64,(.*)$", data_url or "", re.S)
        if not m:
            raise StoreError("Choose a PNG, JPG or WebP picture.")
        try:
            raw = base64.b64decode(m.group(1), validate=True)
        except ValueError:
            raise StoreError("That picture couldn't be read.") from None
        if len(raw) > IMAGE_MAX:
            raise StoreError(f"Pick a smaller picture (at most {IMAGE_MAX // 1024} KB). A square of 128 pixels is plenty.")
        ext = next((e for magic, e in IMAGE_TYPES.items() if raw.startswith(magic)), None)
        if ext == "webp" and raw[8:12] != b"WEBP":
            ext = None
        if not ext:
            raise StoreError("Choose a PNG, JPG or WebP picture.")
        self.remove_image(tool_id)
        self.images.mkdir(parents=True, exist_ok=True)
        (self.images / f"{tool_id}.{ext}").write_bytes(raw)

    def remove_image(self, tool_id: str) -> None:
        p = self.image_path(tool_id)
        if p:
            p.unlink(missing_ok=True)

"""traPYze's window: a small web server on this computer, opened in the browser.

Built on Python's own http.server, so traPYze keeps zero dependencies.

Safety: the server listens on 127.0.0.1 only, checks the Host header (so a
web page elsewhere can't reach it through a DNS trick), and every API call
must carry the session token that `trapyze open` puts in the address it opens.
"""

from __future__ import annotations

import datetime
import json
import mimetypes
import os
import socket
import secrets
import subprocess
import sys
import threading
import time
import webbrowser
from collections import deque
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from .. import __version__
from ..apis import PRESETS, helper, run_config
from ..freshness import checks, disk_free
from ..schedule import NeedsPassword, Plans, System, check_when, describe, nice_time, next_times, sync as sync_plan
from ..home import Home
from ..editors import available as editors_available, choose, open_in
from ..health import add_package as health_add_package, check as health_check, summary as health_summary
from ..templates import KINDS as TEMPLATE_KINDS, make as make_tool
from ..versions import Versions, diff_lines
from .. import ai as ai_help
from ..ai import AIError, AISettings
from ..updater import UpdateError, Updates, start_update
from ..layout import Layout, item_texts, suggest as suggest_shelf, suggest_chain, topics
from ..store import ICONS, Chain, ChainRun, Chains, Looks, Presets, Step, StoreError, step_settings
from ..label import LabelError, SettingError, Tool
from ..locks import Busy
from ..runner import EngineMissing, Event, Run, find_engine, history
from ..vault import (
    TEMPLATES, Locked, NeedsPermission, NeedsUnlock, Vault, VaultError, WrongPin, default_variable, looks_secret,
    parse_env_file, secrets_for,
)

IDLE_LOCK_SECONDS = 30 * 60

KEEP_LINES = 3000  # output lines kept per run for the live log
MAX_RUNS = 50  # finished runs kept in memory


class LiveRun:
    """A run plus everything a browser needs to follow it, even if it joins late."""

    def __init__(self, run: Run):
        self.run = run
        self.events: deque[dict[str, Any]] = deque(maxlen=KEEP_LINES)
        self.serial = 0  # total events ever added; lets a stream resume where it was
        self.cond = threading.Condition()
        self.started = time.time()
        self.in_chain = False
        self.on_finished: Any = None

    def add(self, event: Event) -> None:
        payload = {"kind": event.kind, "message": event.message, "fraction": event.fraction, "line": event.line}
        if event.kind == "finished" and self.run.result:
            payload["result"] = asdict(self.run.result)
        with self.cond:
            self.serial += 1
            payload["n"] = self.serial
            self.events.append(payload)
            self.cond.notify_all()
        if event.kind == "finished" and self.on_finished:
            try:
                self.on_finished(self)
            except Exception:  # a notification must never break a run
                pass

    def since(self, n: int) -> list[dict[str, Any]]:
        with self.cond:
            return [e for e in self.events if e["n"] > n]

    def wait(self, n: int, timeout: float) -> None:
        with self.cond:
            if self.serial <= n:
                self.cond.wait(timeout)

    def summary(self) -> dict[str, Any]:
        r = self.run
        return {
            "run_id": r.run_id,
            "tool_id": r.tool.id,
            "tool_name": r.tool.name,
            "running": r.running,
            "fraction": r.fraction,
            "step": r.step,
            "started": self.started,
            "result": asdict(r.result) if r.result else None,
        }


class App:
    def __init__(self, home: Home):
        self.home = home
        self.token = secrets.token_urlsafe(24)
        self.runs: dict[str, LiveRun] = {}
        self.lock = threading.Lock()
        self.vault = Vault(home.internal)
        self.vault_lock = threading.Lock()
        self.presets = Presets(home.internal)
        self.chains = Chains(home.internal)
        self.looks = Looks(home.internal)
        self.layout = Layout(home.internal)
        self._suggest_cache: dict[tuple[str, float], str] = {}
        self.versions = Versions(home.internal)
        self.ai = AISettings(home.internal)
        self.updates = Updates(home.internal)
        self.quit_hook = None  # set by whoever runs the server: closes traPYze
        self._update_notice()
        self._health_cache: dict[tuple[str, float], list[dict]] = {}
        self._seen_stamp: dict[str, float] = {}
        self.chain_runs: dict[str, ChainRun] = {}
        self.desktop: Any = None  # the window and tray, when traPYze runs as an app
        self.plans = Plans(home.internal)
        from ..packages import Packages
        self.packages = Packages(home)
        self._package_check_started = 0.0
        self.system = System(home.root)
        self._planner: threading.Thread | None = None

    def check_idle(self) -> None:
        """Lock the vault after half an hour without use."""
        with self.vault_lock:
            if self.vault.unlocked and self.vault.idle_seconds() > IDLE_LOCK_SECONDS:
                self.vault.lock()

    # Tools ---------------------------------------------------------------
    def tools(self) -> dict[str, Any]:
        tools, problems = self.home.tools()
        last: dict[str, dict] = {}
        for record in history(self.home, limit=300):
            last.setdefault(record.get("tool_id"), record)
        remembered = self._remembered()
        with self.lock:
            running = {lr.run.tool.id: lr.run.run_id for lr in self.runs.values() if lr.run.running}
        presets = self.presets.all()
        looks = self.looks.get()
        engine = find_engine() is not None
        free = disk_free(self.home.outputs)
        self.track_versions(tools)
        kinds = self.suggestions(tools)
        out = []
        for t in tools:
            item = self._tool_json(t, last.get(t.id), remembered.get(t.id), running.get(t.id))
            item["presets"] = presets.get(t.id, {})
            item["checks"] = checks(self.home, t, tools, engine, free)
            item["label_look"] = {"icon": t.icon, "color": t.color}
            own = looks["tools"].get(t.id, {})
            item["icon"], item["color"] = own.get("icon", t.icon), own.get("color", t.color)
            item["image"] = f"/api/icons/{t.id}?v={int(p.stat().st_mtime)}" if (p := self.looks.image_path(t.id)) else None
            item["reads"] = t.reads
            item["kind"] = kinds.get(f"tool:{t.id}", "")
            item["health"] = health_summary(self.health(t))
            item["changes"] = self.versions.count(t.id)
            item["path"] = str(t.path)
            item["packages"] = self.packages.summary(t) if t.dependencies or (t.path.with_name(t.path.name + ".lock")).exists() else None
            out.append(item)
        with self.lock:
            active_chains = [c.summary() for c in self.chain_runs.values() if c.status == "running"]
        programs = self.home.programs()
        layout, topic_list = self.desktop_layout(tools, programs)
        return {
            "home": str(self.home.root),
            "tools": out,
            "problems": [{"file": p.path.name, "message": p.message} for p in problems],
            "data": self._data_files(),
            "chains": [c.to_json() for c in self.chains.all()],
            "active_chains": active_chains,
            "looks": {k: v for k, v in looks.items() if k != "tools"},
            "icons": list(ICONS),
            "desktop": self.desktop_info(),
            "schedule": self.plans_json(),
            "programs": programs,
            "layout": layout,
            "topics": topic_list,
            "version": __version__,
            "notice": getattr(self, "notice", ""),
            "update": self.update_info(),
        }

    def suggestions(self, tools: list[Tool] | None = None) -> dict[str, str]:
        """Item key -> the shelf traPYze would put it on (tools with a tile, and chains)."""
        if tools is None:
            tools = self.home.tools()[0]
        out: dict[str, str] = {}
        for t in tools:
            if t.hidden:
                continue
            try:
                stamp = t.path.stat().st_mtime
            except OSError:
                stamp = 0.0
            key = (str(t.path), stamp)
            if key not in self._suggest_cache:
                self._suggest_cache[key] = suggest_shelf(t)
            out[f"tool:{t.id}"] = self._suggest_cache[key]
        for c in self.chains.all():
            out[f"chain:{c.id}"] = suggest_chain(c, out)
        return out

    def health(self, tool: Tool) -> list[dict[str, Any]]:
        try:
            stamp = tool.path.stat().st_mtime
        except OSError:
            return []
        key = (str(tool.path), stamp)
        if key not in self._health_cache:
            try:
                self._health_cache[key] = health_check(tool)
            except (OSError, ValueError) as exc:
                self._health_cache[key] = [{"level": "warn", "code": "unreadable", "title": "The health check couldn't read it",
                                            "detail": str(exc), "line": None, "fix": None}]
        return self._health_cache[key]

    def track_versions(self, tools: list[Tool]) -> None:
        """Keep a copy of every script that is new or changed since traPYze last looked."""
        for t in tools:
            try:
                stamp = t.path.stat().st_mtime
            except OSError:
                continue
            before = self._seen_stamp.get(str(t.path))
            if before == stamp:
                continue
            self._seen_stamp[str(t.path)] = stamp
            self.versions.snapshot(t.path, t.id, "First copy" if before is None and not self.versions.count(t.id) else "Changed")

    def find_tool(self, tool_id: str) -> Tool:
        tool = next((t for t in self.home.tools()[0] if t.id == tool_id), None)
        if tool is None:
            raise StoreError("That tool isn't there any more.")
        return tool

    def edit(self, tool_id: str, editor_id: str | None = None) -> dict[str, Any]:
        tool = self.find_tool(tool_id)
        found = editors_available()
        chosen = choose(found, editor_id or self.looks.get().get("editor", ""))
        if chosen is None:
            raise StoreError("No editor found on this computer. Install Visual Studio Code or Notepad++, or open the "
                             "script from its folder.")
        self.versions.snapshot(tool.path, tool.id, "Before editing")
        open_in(chosen, tool.path)
        return {"editor": chosen["name"], "path": str(tool.path)}

    def fix(self, tool_id: str, action: str, body: dict[str, Any]) -> str:
        tool = self.find_tool(tool_id)
        if action != "add-package":
            raise StoreError("Unknown fix.")
        source = tool.path.read_text(encoding="utf-8")
        new = health_add_package(source, str(body.get("package", "")))
        if new != source:
            self.versions.snapshot(tool.path, tool.id, "Before adding a package")
            tool.path.write_text(new, encoding="utf-8")
        return f"Added {body.get('package')} to its packages. traPYze installs it on the next run."

    def new_tool(self, body: dict[str, Any]) -> dict[str, Any]:
        kind = str(body.get("kind", ""))
        path = make_tool(self.home.scripts, str(body.get("name", "")), kind, str(body.get("description", "")))
        tools = self.home.tools()[0]
        tool = next((t for t in tools if t.path == path), None)
        if tool is None:
            path.unlink(missing_ok=True)
            raise StoreError("The new tool couldn't be read. Please report this.")
        self.track_versions(tools)
        if any(s["id"] == kind for s in self.layout.arrange(self.suggestions(tools))["shelves"]):
            self.layout.move(f"tool:{tool.id}", kind)
        else:
            self.layout.seen(f"tool:{tool.id}", kind)
        opened = None
        if body.get("open"):
            try:
                opened = self.edit(tool.id)["editor"]
            except StoreError:
                opened = None
        return {"id": tool.id, "editor": opened}

    # Updating traPYze itself -------------------------------------------------
    def _quiet_update_check(self) -> None:
        try:
            self.updates.check()
        except UpdateError:
            pass

    def _update_notice(self) -> None:
        """After an update the script left a log: say how it went, once."""
        log = self.updates.log
        try:
            text = log.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return
        if "UPDATED" in text:
            self.notice = f"traPYze is up to date: version {__version__}."
        elif "FAILED" in text:
            self.notice = "The update didn't work, so you still have the version you had. Its log is in .trapyze/update-last.log."
        else:
            return
        try:
            os.replace(log, log.with_name("update-last.log"))
        except OSError:
            pass

    def update_info(self) -> dict[str, Any]:
        st = self.updates.state()
        latest = st.get("latest") or {}
        from ..project import HOME_PAGE
        return {"home_page": HOME_PAGE, "current": st["current"], "online": st["online"], "auto": st["auto"], "available": st["available"],
                "version": latest.get("version"), "page": latest.get("page"), "checked": st.get("checked"),
                "error": st.get("error")}

    def install_update(self) -> dict[str, Any]:
        st = self.updates.state()
        if not st["available"]:
            raise UpdateError("There's no newer version to install.")
        with self.lock:
            busy = [lr.run.tool.name for lr in self.runs.values() if lr.run.running]
        if busy:
            raise UpdateError(f"Wait until {busy[0]} has finished; updating closes traPYze for a moment.")
        if self.quit_hook is None:
            raise UpdateError("This traPYze can't close itself. Close it, and run the installer again.")
        from ..desktop import launcher
        target, args = launcher()
        start_update(self.home.internal, find_engine(), st["latest"]["wheel"], [target, *args])
        threading.Timer(0.8, self.quit_hook).start()
        return {"version": st["latest"]["version"]}

    # AI help -----------------------------------------------------------------
    def ai_info(self) -> dict[str, Any]:
        st = self.ai.get()
        return {"settings": st, "ready": bool(st["provider"] and st["model"] and st["connection"]),
                "providers": {k: {"name": v["name"], "keys": v["keys"], "hint": v["hint"]} for k, v in ai_help.PROVIDERS.items()},
                "chat_sites": {k: {"name": n, "url": u} for k, (n, u) in ai_help.CHAT_SITES.items()},
                "tasks": ai_help.TASKS}

    def _ai_key(self, connection: str) -> str:
        with self.vault_lock:
            if not self.vault.unlocked:
                raise Locked("Unlock the vault so traPYze can use the AI key.")
            values = self.vault.values(connection)
            secret = self.vault.secret_names(connection)
        key = next((values[k] for k in secret if values.get(k)), "") or next(iter(values.values()), "")
        if not key:
            raise AIError("The AI connection has no key. Add it again under Look and feel, AI help.")
        return key

    def ai_key(self, provider: str, key: str) -> dict[str, Any]:
        if provider not in ai_help.PROVIDERS:
            raise AIError("Choose an AI service.")
        key = key.strip()
        if len(key) < 10:
            raise AIError("That key looks too short. Copy the whole key from the service's website.")
        found = ai_help.models(provider, key)  # proves the key works before it's stored
        name = f"ai-{provider}"
        with self.vault_lock:
            if not self.vault.exists():
                raise AIError("Make a vault first, on the Connections screen: it keeps the key safe.")
            if not self.vault.unlocked:
                raise Locked("Unlock the vault to store the key.")
            var = default_variable(name, "API_KEY")
            existing = any(c["name"] == name for c in self.vault.connections())
            self.vault.save_connection(name, "api_key", {var: key}, [var], scheduled=False,
                                       description=f"AI help in traPYze ({ai_help.PROVIDERS[provider]['name']})",
                                       replace_from=name if existing else None)
        model = ai_help.pick_model(provider, found)
        self.ai.update(provider=provider, model=model, connection=name)
        return {"models": found, "model": model}

    def ai_models(self) -> dict[str, Any]:
        st = self.ai.get()
        if not st["connection"]:
            raise AIError("Add a key for an AI service first.")
        found = ai_help.models(st["provider"], self._ai_key(st["connection"]))
        return {"models": found, "model": st["model"] if st["model"] in found else ai_help.pick_model(st["provider"], found)}

    def ai_question(self, body: dict[str, Any]) -> tuple[Tool, dict[str, Any], str]:
        tool = self.find_tool(str(body.get("tool", "")))
        source = tool.path.read_text(encoding="utf-8", errors="replace")
        task = str(body.get("task", ""))
        run, log = None, ""
        if task == "why":
            run_id = str(body.get("run") or "")
            runs = history(self.home, tool.id, limit=30)
            run = next((r for r in runs if r.get("run_id") == run_id), None) if run_id else \
                next((r for r in runs if r.get("status") in ("failed", "warning", "stopped")), None)
            if run:
                log = self.log_tail(run["run_id"], 200)
        secrets, _ = self.vault_secrets()
        return tool, ai_help.build(task, tool, source, str(body.get("request", "")), run, log, secrets), source

    def ai_proposal(self, tool: Tool, answer: str, source: str | None = None) -> dict[str, Any] | None:
        code = ai_help.extract_code(answer)
        if code is None:
            return None
        if source is None:
            source = tool.path.read_text(encoding="utf-8", errors="replace")
        return {"code": code, "lines": diff_lines(source, code),
                "problems": ai_help.check_proposal(code, tool, self.home.internal / "ai-check")}

    def ai_ask(self, body: dict[str, Any]) -> dict[str, Any]:
        st = self.ai.get()
        if not st["connection"]:
            raise AIError("Add a key for an AI service first, under Look and feel, AI help, or use copy and paste.")
        tool, q, source = self.ai_question(body)
        key = self._ai_key(st["connection"])
        with ai_help._busy:
            answer = ai_help.ask(st["provider"], key, st["model"], q["system"], q["user"])
        answer, _ = ai_help.mask(answer, [key])
        proposal = self.ai_proposal(tool, answer, source) if body.get("task") != "explain" else None
        return {"answer": answer, "proposal": proposal, "masked": q["masked"],
                "model": st["model"], "provider": ai_help.PROVIDERS[st["provider"]]["name"]}

    def ai_apply(self, tool_id: str, code: str, task: str) -> None:
        tool = self.find_tool(tool_id)
        if not code.strip():
            raise AIError("There's no script to save.")
        self.versions.snapshot(tool.path, tool.id, "Before the AI change")
        tool.path.write_text(code, encoding="utf-8")
        self.versions.snapshot(tool.path, tool.id, "AI: " + ai_help.TASKS.get(task, "change"))

    def desktop_layout(self, tools: list[Tool], programs: dict[str, dict]) -> tuple[dict[str, Any], list[dict]]:
        suggested = self.suggestions(tools)
        layout = self.layout.arrange(suggested)
        visible = [t for t in tools if not t.hidden]
        texts = item_texts(visible, self.chains.all(), programs)
        return layout, topics(texts)

    def layout_call(self, action: str, body: dict[str, Any]) -> None:
        lay = self.layout
        key = str(body.get("key", ""))
        if action == "move":
            lay.move(key, str(body.get("shelf", "")), body.get("before"))
        elif action == "seen":
            suggested = self.suggestions()
            if key in suggested:
                lay.seen(key, suggested[key])
        elif action == "favourite":
            lay.favourite(key, bool(body.get("on")))
        elif action == "view":
            lay.set_view(str(body.get("view", "")))
        elif action == "topics":
            lay.set_topics(bool(body.get("on")))
        elif action == "shelf-add":
            lay.add_shelf(str(body.get("name", "")))
        elif action == "shelf-rename":
            lay.rename_shelf(str(body.get("shelf", "")), str(body.get("name", "")))
        elif action == "shelf-fold":
            lay.fold_shelf(str(body.get("shelf", "")), bool(body.get("folded")))
        elif action == "shelf-move":
            lay.move_shelf(str(body.get("shelf", "")), int(body.get("step", 0)))
        elif action == "shelf-delete":
            lay.delete_shelf(str(body.get("shelf", "")))
        elif action == "resort":
            lay.resort(self.suggestions())
        else:
            raise StoreError("Unknown desktop change.")

    def desktop_info(self) -> dict[str, Any]:
        from ..desktop import available

        info = available()
        info["mode"] = self.desktop.mode if self.desktop else "browser"
        return info

    @staticmethod
    def _tool_json(t: Tool, last: dict | None, remembered: dict | None, running: str | None) -> dict[str, Any]:
        return {
            "id": t.id,
            "name": t.name,
            "description": t.description,
            "icon": t.icon,
            "color": t.color,
            "version": t.version,
            "file": t.path.name,
            "group": t.group,
            "hidden": t.hidden,
            "dependencies": t.dependencies,
            "connections": t.connections,
            "settings": [
                {
                    "key": s.key, "label": s.label, "type": s.type, "default": s.default, "help": s.help,
                    "options": s.options, "min": s.min, "max": s.max, "required": s.required,
                    "advanced": s.advanced, "only_for": s.only_for,
                }
                for s in t.settings
            ],
            "last": {k: last.get(k) for k in ("run_id", "status", "started", "seconds", "settings")} if last else None,
            "remembered": remembered,
            "running": running,
        }

    def _data_files(self) -> list[dict[str, Any]]:
        out = []
        if self.home.data.is_dir():
            for p in sorted(self.home.data.iterdir()):
                if p.is_file() and not p.name.startswith("."):
                    st = p.stat()
                    out.append({"name": p.name, "modified": st.st_mtime, "bytes": st.st_size})
        return out

    # Remembered settings: what the user chose last time, per tool -----------
    @property
    def _memory_path(self) -> Path:
        return self.home.internal / "last_settings.json"

    def _remembered(self) -> dict[str, dict]:
        try:
            return json.loads(self._memory_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _remember(self, tool_id: str, chosen: dict[str, Any]) -> None:
        data = self._remembered()
        data[tool_id] = chosen
        tmp = self._memory_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
        os.replace(tmp, self._memory_path)

    # Runs ------------------------------------------------------------------
    def start(self, tool_id: str, chosen: dict[str, Any], allow: bool = False, in_chain: bool = False,
              unattended: bool = False) -> LiveRun:
        tool = self.home.find(tool_id)
        tool.resolve(chosen)  # check settings before asking for the PIN or permission
        env: dict[str, str] = {}
        secret: list[str] = []
        if tool.connections:
            with self.vault_lock:
                try:
                    env, secret = secrets_for(self.vault, tool.id, tool.name, tool.connections, unattended=unattended)
                except NeedsPermission as exc:
                    if not allow:
                        raise
                    self.vault.allow(tool.id, exc.names)
                    env, secret = secrets_for(self.vault, tool.id, tool.name, tool.connections)
        run = Run(self.home, tool, chosen, extra_env=env, secrets=secret)  # checks settings; raises SettingError
        live = LiveRun(run)
        live.in_chain = in_chain
        live.on_finished = self._run_finished
        run.start(live.add)  # raises Busy if shared data is in use
        with self.lock:
            self.runs[run.run_id] = live
            finished = [k for k, v in self.runs.items() if not v.run.running]
            for k in finished[:-MAX_RUNS]:
                self.runs.pop(k, None)
        self._remember(tool.id, chosen)
        if self.desktop:
            self.desktop.refresh()
        return live

    def _run_finished(self, live: LiveRun) -> None:
        plan = getattr(live, "plan", None)
        if plan:
            r = live.run.result
            self.plans.update_log(plan[0], plan[1], status=r.status if r else "failed",
                                  note=(r.cause or "") if r else "", ended=time.time())
        if not self.desktop:
            return
        if live.in_chain:
            self.desktop.refresh()
            return
        r, name = live.run.result, live.run.tool.name
        status = r.status if r else "failed"
        title, message = {
            "done": ("Bingo!", f"{name} is done."),
            "warning": ("Done, with warnings", f"{name} finished, but flagged things worth a look."),
            "stopped": ("Stopped", f"{name} was stopped."),
        }.get(status, (f"{name} couldn't finish", (r.cause if r and r.cause else "Open traPYze to see why.")))
        self.desktop.finished(title, message)

    def _chain_finished(self, chain: ChainRun) -> None:
        plan = getattr(chain, "plan", None)
        if plan:
            problems = [f"{s['name']}: {s['message']}" for s in chain.steps if s["status"] == "failed" and s["message"]]
            self.plans.update_log(plan[0], plan[1], status=chain.status, note="; ".join(problems), ended=time.time())
        if not self.desktop:
            return
        title, message = {
            "done": ("Bingo!", f"The chain “{chain.chain.name}” is done."),
            "warning": ("Done, with warnings", f"“{chain.chain.name}” finished, with warnings."),
            "stopped": ("Stopped", f"“{chain.chain.name}” was stopped."),
        }.get(chain.status, (f"“{chain.chain.name}” had a problem", "Open traPYze to see which step."))
        self.desktop.finished(title, message)

    def start_chain(self, chain: Chain, settings: list[dict[str, Any]], allow: bool = False,
                    unattended: bool = False) -> ChainRun:
        """Check everything a chain needs before its first step starts, then run it."""
        tools = {t.id: t for t in self.home.tools()[0]}
        problems: list[str] = []
        for i, step in enumerate(chain.steps):
            tool = tools.get(step.tool)
            if tool is None:
                problems.append(f"Step {i + 1}: the tool '{step.tool}' isn't in the scripts folder any more.")
                continue
            try:
                tool.resolve(settings[i])
            except SettingError as exc:
                problems += [f"Step {i + 1} ({tool.name}): {line}" for line in str(exc).splitlines()]
        if problems:
            raise SettingError("\n".join(problems))
        wanted: dict[str, list[str]] = {}
        for step in chain.steps:
            for c in tools[step.tool].connections:
                wanted.setdefault(step.tool, []).append(c)
        if wanted:
            with self.vault_lock:
                need: list[str] = []
                for tool_id, names in wanted.items():
                    try:
                        secrets_for(self.vault, tool_id, tools[tool_id].name, names, unattended=unattended)
                    except NeedsPermission as exc:
                        if allow:
                            self.vault.allow(tool_id, exc.names)
                        else:
                            need += [n for n in exc.names if n not in need]
                if need:
                    raise NeedsPermission(f"“{chain.name}”", need)
        names = {t.id: t.name for t in tools.values()}
        run = ChainRun(chain, settings, names,
                       lambda tool_id, chosen: self.start(tool_id, chosen, in_chain=True, unattended=unattended).run,
                       on_done=self._chain_finished)
        with self.lock:
            self.chain_runs[run.id] = run
            done = [k for k, v in self.chain_runs.items() if v.status != "running"]
            for k in done[:-MAX_RUNS]:
                self.chain_runs.pop(k, None)
        return run.begin()

    # Plans --------------------------------------------------------------------
    def fire_plan(self, plan_id: str, force: bool = False) -> dict[str, Any]:
        """A plan is due (or "Run now"): decide once, then run it here where it can be watched."""
        plan = self.plans.get(plan_id)
        now = datetime.datetime.now()
        if force:
            verdict, at = "run", now.replace(second=0, microsecond=0)
        else:
            verdict, at = self.plans.claim(plan, now)
        if verdict != "run" or at is None:
            return {"started": False, "verdict": verdict}
        occurrence = at.isoformat(timespec="minutes")
        entry = {"plan": plan["id"], "name": plan["name"], "occurrence": occurrence, "status": "running",
                 "at": time.time(), "how": "now" if force else "window"}
        self.plans.log(entry)
        try:
            if plan["target_kind"] == "tool":
                from ..schedule import plan_settings

                live = self.start(plan["target"], plan_settings(self.home, plan), unattended=True)
                live.plan = (plan["id"], occurrence)
                self.plans.update_log(plan["id"], occurrence, run_id=live.run.run_id)
                return {"started": True, "run_id": live.run.run_id}
            chain = self.chains.get(plan["target"])
            cr = self.start_chain(chain, self.chain_settings(chain), unattended=True)
            cr.plan = (plan["id"], occurrence)
            return {"started": True, "chain_run": cr.summary()}
        except Exception as exc:  # anything that stops it starting: logged in plain words
            message = str(exc) or exc.__class__.__name__
            self.plans.update_log(plan["id"], occurrence, status="failed", note=message, ended=time.time())
            if self.desktop:
                self.desktop.finished(f"“{plan['name']}” couldn't start", message)
            return {"started": False, "verdict": "failed", "message": message}

    def start_planner(self, every: float = 20) -> None:
        """While traPYze is open it checks the plans itself too (the computer's scheduler may be off)."""
        if self._planner:
            return

        def loop() -> None:
            while True:
                if time.time() - self._package_check_started > 6 * 3600:  # the daily look for newer packages
                    self._package_check_started = time.time()
                    threading.Thread(target=lambda: self.packages.check_all(self.home.tools()[0]),
                                     name="trapyze-packages", daemon=True).start()
                if self.updates.due():
                    threading.Thread(target=self._quiet_update_check, name="trapyze-update-check", daemon=True).start()
                for plan in self.plans.all():
                    if plan.get("enabled", True):
                        try:
                            self.fire_plan(plan["id"])
                        except Exception:
                            pass
                time.sleep(every)
        self._planner = threading.Thread(target=loop, name="trapyze-planner", daemon=True)
        self._planner.start()

    def plans_json(self) -> dict[str, Any]:
        now = datetime.datetime.now()
        tools = {t.id: t for t in self.home.tools()[0]}
        chains = {c.id: c for c in self.chains.all()}
        looks = self.looks.get()["tools"]
        out = []
        for p in self.plans.all():
            if p["target_kind"] == "tool":
                t = tools.get(p["target"])
                own = looks.get(p["target"], {})
                target = {"name": t.name, "icon": own.get("icon", t.icon), "color": own.get("color", t.color)} if t else None
            else:
                c = chains.get(p["target"])
                target = {"name": c.name, "icon": c.icon, "color": c.color} if c else None
            upcoming = next_times(p["when"], now, 1) if p.get("enabled", True) else []
            history = self.plans.history(p["id"], 5)
            out.append({**p, "sentence": describe(p["when"]), "target_info": target,
                        "next": upcoming[0].isoformat(timespec="minutes") if upcoming else None,
                        "next_words": nice_time(upcoming[0], now) if upcoming else None,
                        "history": history})
        out.sort(key=lambda x: (x["next"] is None, x["next"] or "", x["name"].lower()))
        return {"plans": out, "system": {"name": self.system.name, **self.system.abilities()}}

    def save_plan(self, body: dict[str, Any]) -> dict[str, Any]:
        tools = self.home.tools()[0]
        warnings: list[str] = []
        # Permission for connections is given now, while someone is here.
        if body.get("target_kind") == "tool":
            wanted = [t for t in tools if t.id == body.get("target")]
        else:
            try:
                chain = self.chains.get(str(body.get("target") or ""))
                ids = {s.tool for s in chain.steps}
                wanted = [t for t in tools if t.id in ids]
            except StoreError:
                wanted = []
        needing = [t for t in wanted if t.connections]
        if needing:
            with self.vault_lock:
                need: list[str] = []
                for t in needing:
                    try:
                        secrets_for(self.vault, t.id, t.name, t.connections)
                    except NeedsPermission as exc:
                        if body.get("allow"):
                            self.vault.allow(t.id, exc.names)
                        else:
                            need += [n for n in exc.names if n not in need]
                if need:
                    raise NeedsPermission("This plan", need)
                away = {c["name"] for c in self.vault.connections() if c.get("scheduled")}
                for t in needing:
                    for n in t.connections:
                        if n not in away:
                            warnings.append(f"{t.name} uses “{n}”, which isn't available to scheduled plans. "
                                            "It will only work while traPYze is open and the vault unlocked. "
                                            "Change that under Connections.")
        plan = self.plans.save(body, tools, self.chains.all(), self.presets)
        sync_plan(self.plans, self.system, plan, password=body.get("password") or None)
        state = self.plans_json()
        state["warnings"] = sorted(set(warnings))
        state["saved"] = plan["id"]
        return state

    def vault_secrets(self) -> tuple[list[str], bool]:
        """All secret values (to keep them out of shared files), and whether the vault could be read."""
        with self.vault_lock:
            if not self.vault.unlocked:
                return [], False
            out: list[str] = []
            for c in self.vault.connections():
                values = self.vault.values(c["name"])
                out += [values[k] for k in self.vault.secret_names(c["name"]) if values.get(k)]
            return out, True

    def chain_settings(self, chain: Chain) -> list[dict[str, Any]]:
        remembered = self._remembered()
        return [step_settings(s, self.presets, remembered) for s in chain.steps]

    def get(self, run_id: str) -> LiveRun | None:
        with self.lock:
            return self.runs.get(run_id)

    def active(self) -> list[dict[str, Any]]:
        with self.lock:
            return [lr.summary() for lr in self.runs.values() if lr.run.running]

    # Vault -------------------------------------------------------------------
    def vault_state(self) -> dict[str, Any]:
        with self.vault_lock:
            v = self.vault
            state: dict[str, Any] = {"exists": v.exists(), "unlocked": v.unlocked, "idle_lock_minutes": IDLE_LOCK_SECONDS // 60}
            state["templates"] = {
                k: {**t, "variables": [dict(x) for x in t["variables"]]} for k, t in TEMPLATES.items()
            }
            state["api_presets"] = PRESETS
            if v.unlocked:
                state["connections"] = v.connections()
                try:
                    state["usage"] = helper().usage(self.api_db)
                except Exception:  # usage is a nicety; never block the screen on it
                    state["usage"] = {}
            return state

    @property
    def api_db(self) -> Path:
        return self.home.internal / "api.sqlite"

    def clear_cache(self, name: str) -> dict[str, Any]:
        n = helper().clear_cache(name, self.api_db)
        return {"cleared": n, **self.vault_state()}

    def vault_call(self, action: str, body: dict[str, Any]) -> dict[str, Any]:
        with self.vault_lock:
            v = self.vault
            if action == "create":
                v.create(str(body.get("pin", "")))
                v.touch()
            elif action == "unlock":
                v.unlock(str(body.get("pin", "")))
            elif action == "lock":
                v.lock()
            elif action == "change-pin":
                v.change_pin(str(body.get("old", "")), str(body.get("new", "")))
            elif action == "reset":
                if body.get("confirm") != "RESET":
                    raise VaultError("Type RESET to confirm.")
                v.reset()
            else:
                raise LookupError("Not found.")
        return self.vault_state()

    def save_connection(self, body: dict[str, Any]) -> dict[str, Any]:
        values: dict[str, Any] = dict(body.get("values") or {})
        source = body.get("import_path")
        if source:
            from_file = parse_env_file(str(source))
            for var, value in list(values.items()):
                if value is None and not body.get("replace_from"):
                    if var not in from_file:
                        raise VaultError(f"{var} isn't in that file.")
                    values[var] = from_file[var]
        with self.vault_lock:
            self.vault.save_connection(
                str(body.get("name", "")), str(body.get("kind", "custom")), values,
                [str(x) for x in body.get("secret") or []], bool(body.get("scheduled")),
                str(body.get("description") or ""), body.get("replace_from") or None,
                api=body.get("api") or None,
            )
        return self.vault_state()

    def delete_connection(self, name: str) -> dict[str, Any]:
        with self.vault_lock:
            self.vault.delete_connection(name)
        return self.vault_state()

    def disallow(self, tool_id: str, name: str) -> dict[str, Any]:
        with self.vault_lock:
            self.vault.disallow(tool_id, name)
        return self.vault_state()

    def test_connection(self, name: str) -> dict[str, Any]:
        with self.vault_lock:
            values = self.vault.values(name)
            kind = next(c["kind"] for c in self.vault.connections() if c["name"] == name)
            api_cfg = self.vault.api_config(name)
        if kind == "email":
            ok, message = test_email(values)
        elif api_cfg and api_cfg.get("test"):
            ok, message = test_api(name, api_cfg, values, self.api_db)
        else:
            raise VaultError("There's no test for this one. Run a tool that uses it to check it.")
        with self.vault_lock:
            self.vault.record_test(name, ok)
        return {"ok": ok, "message": message, **self.vault_state()}

    # Files -----------------------------------------------------------------
    def resolve_inside_home(self, raw: str) -> Path:
        path = Path(raw)
        if not path.is_absolute():
            path = self.home.root / path
        path = path.resolve()
        root = self.home.root.resolve()
        if path != root and root not in path.parents:
            raise PermissionError("traPYze only opens files inside its own folder.")
        if not path.exists():
            raise FileNotFoundError(f"{path.name} isn't there any more.")
        return path

    def log_tail(self, run_id: str, lines: int = 80) -> str:
        folder = (self.home.runs / run_id).resolve()
        if self.home.runs.resolve() not in folder.parents:
            raise PermissionError("No such run.")
        try:
            text = (folder / "log.txt").read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
        return "\n".join(text.splitlines()[-lines:])


def wsl_home() -> str | None:
    """\\\\wsl.localhost\\<distro>\\home\\<you>, when this is Windows with WSL."""
    if os.name != "nt":
        return None
    from ..importer import wsl_distros, wsl_root

    for distro in wsl_distros():
        home = wsl_root(distro) + "\\home"
        try:
            users = [u for u in os.listdir(home) if not u.startswith(".")]
        except OSError:
            continue
        return f"{home}\\{users[0]}" if len(users) == 1 else home
    return None


def test_api(name: str, cfg: dict[str, Any], values: dict[str, str], db: Path) -> tuple[bool, str]:
    """One real call to the service's test address, through the shared gateway (it counts)."""
    gw = helper()
    key = values.get(cfg.get("key_var") or "", "") if cfg.get("key_in") != "none" else ""
    try:
        r = gw.call(name, run_config(cfg), key, cfg["test"], cache=False, retries=0, timeout=20, db=db)
    except gw.ApiError as exc:
        return False, str(exc)
    return True, f"{name} answered (status {r.status}). The key works."


def test_email(values: dict[str, str]) -> tuple[bool, str]:
    """Log in to the mail server without sending anything."""
    import smtplib
    import ssl

    host = values.get("SMTP_HOST", "")
    if not host:
        return False, "The mail server is missing."
    port = int(values.get("SMTP_PORT") or 587)
    try:
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=15, context=ssl.create_default_context())
        else:
            server = smtplib.SMTP(host, port, timeout=15)
            server.starttls(context=ssl.create_default_context())
        with server:
            if values.get("SMTP_USER"):
                server.login(values["SMTP_USER"], values.get("SMTP_PASS", ""))
        return True, "It works: the mail server accepted the login."
    except smtplib.SMTPAuthenticationError:
        return False, "The mail server said the user name or password is wrong. For Gmail, use an app password."
    except (OSError, smtplib.SMTPException) as exc:
        return False, f"Couldn't reach the mail server: {exc}"


def open_with_system(path: Path, reveal: bool = False) -> None:
    """Open a file in its usual program, or show it in the file browser."""
    if sys.platform == "win32":  # pragma: no cover - Windows only
        if reveal and path.is_file():
            subprocess.Popen(["explorer", "/select,", str(path)])
        else:
            os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":  # pragma: no cover - macOS only
        subprocess.Popen(["open", "-R", str(path)] if reveal else ["open", str(path)])
    else:
        target = path.parent if reveal and path.is_file() else path
        subprocess.Popen(["xdg-open", str(target)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


_PICKER = r"""
import json, sys, tkinter
from tkinter import filedialog
root = tkinter.Tk(); root.withdraw(); root.attributes("-topmost", True)
kind, start = sys.argv[1], sys.argv[2]
path = filedialog.askdirectory(initialdir=start) if kind == "folder" else filedialog.askopenfilename(initialdir=start)
print(json.dumps(path or ""))
"""


def pick_path(kind: str, start: str) -> str:
    """Show the computer's own file or folder picker; return the chosen path or ''."""
    done = subprocess.run(
        [sys.executable, "-c", _PICKER, kind, start], capture_output=True, text=True, timeout=600,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if done.returncode != 0:
        raise RuntimeError("The file picker isn't available here. Type the path instead.")
    return json.loads(done.stdout.strip() or '""')


def _static(name: str) -> bytes:
    return (resources.files("trapyze") / "web" / "static" / name).read_bytes()


class Handler(BaseHTTPRequestHandler):
    app: App  # set on the subclass made by make_server
    port: int
    server_version = "traPYze"

    def log_message(self, fmt: str, *args: Any) -> None:  # keep the terminal quiet
        pass

    # Plumbing --------------------------------------------------------------
    def _send(self, status: int, body: bytes, ctype: str, extra: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, data: Any) -> None:
        self._send(status, json.dumps(data, default=str).encode("utf-8"), "application/json; charset=utf-8")

    def _error(self, status: int, message: str, **more: Any) -> None:
        self._json(status, {"error": message, **more})

    def _host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").lower()
        return host in (f"127.0.0.1:{self.port}", f"localhost:{self.port}")

    def _token_ok(self, query: dict[str, list[str]]) -> bool:
        given = self.headers.get("X-Trapyze-Token") or (query.get("t") or [""])[0]
        return secrets.compare_digest(given, self.app.token)

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length > 1_000_000:
            raise ValueError("Request too large.")
        raw = self.rfile.read(length) if length else b"{}"
        data = json.loads(raw.decode("utf-8") or "{}")
        if not isinstance(data, dict):
            raise ValueError("Expected a JSON object.")
        return data

    # Routing ---------------------------------------------------------------
    def do_GET(self) -> None:
        self._route("GET")

    def do_POST(self) -> None:
        self._route("POST")

    def _route(self, method: str) -> None:
        if not self._host_ok():
            return self._error(HTTPStatus.FORBIDDEN, "Wrong address.")
        url = urlparse(self.path)
        query = parse_qs(url.query)
        parts = [unquote(p) for p in url.path.strip("/").split("/") if p]

        if method == "GET" and not parts:
            return self._index(query)
        if method == "GET" and len(parts) == 2 and parts[0] == "static":
            return self._static_file(parts[1])
        if not parts or parts[0] != "api":
            return self._error(HTTPStatus.NOT_FOUND, "Not found.")
        if not self._token_ok(query):
            return self._error(HTTPStatus.FORBIDDEN, "This page needs a fresh address. Start traPYze with: trapyze open")
        try:
            self._api(method, parts[1:], query)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _index(self, query: dict[str, list[str]]) -> None:
        if not self._token_ok(query):
            page = (
                "<!doctype html><meta charset=utf-8><title>traPYze</title>"
                "<body style='font-family:system-ui;padding:48px;color:#151A23'>"
                "<h1>traPYze</h1><p>This window has expired. Start traPYze again with "
                "<code>trapyze open</code>.</p>"
            ).encode("utf-8")
            return self._send(HTTPStatus.FORBIDDEN, page, "text/html; charset=utf-8")
        html = _static("index.html").decode("utf-8").replace("__TRAPYZE_TOKEN__", self.app.token)
        csp = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"
        )
        self._send(HTTPStatus.OK, html.encode("utf-8"), "text/html; charset=utf-8", {"Content-Security-Policy": csp})

    def _static_file(self, name: str) -> None:
        if name not in ("app.js", "app.css", "favicon.svg", "favicon.png", "icon.png"):
            return self._error(HTTPStatus.NOT_FOUND, "Not found.")
        ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or name.endswith(".js"):
            ctype = ("text/javascript" if name.endswith(".js") else ctype) + "; charset=utf-8"
        self._send(HTTPStatus.OK, _static(name), ctype)

    def _api(self, method: str, parts: list[str], query: dict[str, list[str]]) -> None:
        app = self.app
        route = (method, parts[0] if parts else "")

        app.check_idle()

        if route == ("GET", "vault"):
            return self._json(HTTPStatus.OK, app.vault_state())

        if method == "POST" and parts[0] == "vault" and len(parts) == 2:
            try:
                return self._json(HTTPStatus.OK, app.vault_call(parts[1], self._body()))
            except WrongPin as exc:
                return self._error(HTTPStatus.FORBIDDEN, str(exc), wrong_pin=True)
            except (VaultError, ValueError, LookupError) as exc:
                return self._error(HTTPStatus.BAD_REQUEST, str(exc))

        if method == "POST" and parts[0] == "connections" and len(parts) == 2:
            try:
                body = self._body()
                if parts[1] == "save":
                    return self._json(HTTPStatus.OK, app.save_connection(body))
                if parts[1] == "delete":
                    return self._json(HTTPStatus.OK, app.delete_connection(str(body.get("name", ""))))
                if parts[1] == "test":
                    return self._json(HTTPStatus.OK, app.test_connection(str(body.get("name", ""))))
                if parts[1] == "clear-cache":
                    return self._json(HTTPStatus.OK, app.clear_cache(str(body.get("name", ""))))
                if parts[1] == "disallow":
                    return self._json(HTTPStatus.OK, app.disallow(str(body.get("tool", "")), str(body.get("name", ""))))
                if parts[1] == "preview-env":
                    found = parse_env_file(str(body.get("path", "")))
                    return self._json(HTTPStatus.OK, {"variables": [{"name": k, "secret": looks_secret(k), "set": bool(v)} for k, v in found.items()]})
            except (NeedsUnlock, Locked) as exc:
                return self._error(HTTPStatus.LOCKED, str(exc), need="unlock")
            except (VaultError, ValueError, OSError) as exc:
                return self._error(HTTPStatus.BAD_REQUEST, str(exc))
            return self._error(HTTPStatus.NOT_FOUND, "Not found.")

        if route == ("GET", "tools"):
            return self._json(HTTPStatus.OK, app.tools())
        if route == ("GET", "ping"):
            busy = sum(1 for live in list(app.runs.values()) if live.run.running) + \
                sum(1 for c in list(app.chain_runs.values()) if c.status == "running")
            return self._json(HTTPStatus.OK, {"app": "trapyze", "version": __version__, "busy": busy,
                                              "window": bool(app.desktop and app.desktop.window is not None)})
        if method == "POST" and parts == ["desktop", "notice"]:
            app.notice = str(self._body().get("text", ""))[:500]
            return self._json(HTTPStatus.OK, {"ok": True})
        if method == "POST" and parts == ["desktop", "quit"]:
            if not app.desktop:
                return self._error(HTTPStatus.CONFLICT, "This traPYze was started without a window or tray.")
            threading.Timer(0.3, app.desktop.quit).start()
            return self._json(HTTPStatus.OK, {"quitting": True})
        if method == "POST" and parts == ["desktop", "show"]:
            shown = bool(app.desktop and app.desktop.show())
            return self._json(HTTPStatus.OK, {"shown": shown})
        if method == "POST" and parts == ["desktop", "shortcut"]:
            from ..desktop import make_shortcuts
            try:
                made = make_shortcuts(app.home)
            except (OSError, subprocess.SubprocessError) as exc:
                return self._error(HTTPStatus.BAD_REQUEST, f"The shortcut couldn't be made: {exc}")
            return self._json(HTTPStatus.OK, {"made": made})

        if method == "GET" and parts[0] == "icons" and len(parts) == 2:
            path = app.looks.image_path(parts[1])
            if not path:
                return self._error(HTTPStatus.NOT_FOUND, "No picture.")
            ctype = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp"}[path.suffix[1:]]
            return self._send(HTTPStatus.OK, path.read_bytes(), ctype, {"Cache-Control": "max-age=86400"})

        if method == "POST" and parts[0] in ("presets", "looks", "chains") and len(parts) == 2 and parts[1] != "runs":
            try:
                body = self._body()
                kind, action = parts
                if kind == "presets":
                    tool = app.home.find(str(body.get("tool", "")))
                    if action == "save":
                        app.presets.save(tool, str(body.get("name", "")), dict(body.get("settings") or {}))
                    elif action == "delete":
                        app.presets.delete(tool.id, str(body.get("name", "")))
                    else:
                        return self._error(HTTPStatus.NOT_FOUND, "Not found.")
                elif kind == "looks":
                    if action == "window":
                        app.looks.update(body)
                    elif action == "tool":
                        tool = app.home.find(str(body.get("tool", "")))
                        app.looks.set_tool(tool.id, body.get("icon"), body.get("color"))
                    elif action == "image":
                        tool = app.home.find(str(body.get("tool", "")))
                        app.looks.set_image(tool.id, str(body.get("data", "")))
                    elif action == "reset":
                        tool = app.home.find(str(body.get("tool", "")))
                        app.looks.reset_tool(tool.id)
                    else:
                        return self._error(HTTPStatus.NOT_FOUND, "Not found.")
                elif kind == "chains":
                    if action == "save":
                        app.chains.save(body, app.home.tools()[0], app.presets)
                    elif action == "delete":
                        app.chains.delete(str(body.get("id", "")))
                    elif action == "run":
                        allow = bool(body.get("allow"))
                        if body.get("update_first"):  # "Update it first": the data's maker, then this tool
                            tool = app.home.find(str(body.get("tool", "")))
                            writer = app.home.find(str(body.get("update_first")))
                            chain = Chain("adhoc", f"Update and run {tool.name}",
                                          [Step(writer.id, "last"), Step(tool.id, "custom")])
                            settings = [app._remembered().get(writer.id) or {}, dict(body.get("settings") or {})]
                        else:
                            chain = app.chains.get(str(body.get("chain", "")))
                            settings = app.chain_settings(chain)
                        run = app.start_chain(chain, settings, allow=allow)
                        return self._json(HTTPStatus.CREATED, run.summary())
                    else:
                        return self._error(HTTPStatus.NOT_FOUND, "Not found.")
            except SettingError as exc:
                return self._error(HTTPStatus.BAD_REQUEST, "Some settings need a look.", problems=str(exc).splitlines())
            except NeedsUnlock as exc:
                return self._error(HTTPStatus.LOCKED, str(exc), need="unlock")
            except NeedsPermission as exc:
                return self._error(HTTPStatus.PRECONDITION_REQUIRED, str(exc), need="allow", connections=exc.names)
            except (StoreError, VaultError, LookupError, LabelError, ValueError) as exc:
                return self._error(HTTPStatus.BAD_REQUEST, str(exc))
            return self._json(HTTPStatus.OK, app.tools())

        if route == ("GET", "import") and parts == ["import", "wsl"]:
            return self._json(HTTPStatus.OK, {"path": wsl_home()})
        if method == "POST" and parts == ["share"]:
            from ..share import ShareProblem, share
            try:
                body = self._body()
                tool = app.home.find(str(body.get("tool", "")))
                known_secrets, checked = app.vault_secrets()
                result = share(app.home, tool, app.home.tools()[0], app.presets.all(), known_secrets,
                               include_presets=bool(body.get("presets", True)), include_data=bool(body.get("data", False)))
                if not checked:
                    result["notes"].insert(0, "The vault was locked, so traPYze could only look for things that resemble keys, "
                                              "not compare with your real keys. Unlock it first to be sure.")
                return self._json(HTTPStatus.OK, result)
            except (ShareProblem, LookupError, OSError) as exc:
                return self._error(HTTPStatus.BAD_REQUEST, str(exc))
        if method == "POST" and parts[0] == "packages" and len(parts) == 2:
            from ..packages import PackageProblem
            try:
                tool = app.home.find(str(self._body().get("tool", "")))
                action = parts[1]
                changes: Any = []
                if action == "lock":
                    changes = app.packages.lock(tool)
                elif action == "check":
                    changes = app.packages.check(tool)
                elif action == "update":
                    changes = app.packages.update(tool)
                elif action == "go-back":
                    changes = app.packages.go_back(tool)
                elif action == "unpin":
                    app.packages.unpin(tool)
                elif action != "status":
                    return self._error(HTTPStatus.NOT_FOUND, "Not found.")
                return self._json(HTTPStatus.OK, {"changes": changes, "status": app.packages.status(tool),
                                                  "summary": app.packages.summary(tool)})
            except (PackageProblem, LookupError, OSError) as exc:
                return self._error(HTTPStatus.BAD_REQUEST, str(exc))
        if method == "GET" and parts == ["update"]:
            st = app.updates.state()
            return self._json(HTTPStatus.OK, {**app.update_info(), "notes": (st.get("latest") or {}).get("notes", "")})
        if method == "POST" and parts[0] == "update" and len(parts) == 2:
            try:
                body = self._body()
                if parts[1] == "check":
                    app.updates.check()
                elif parts[1] == "auto":
                    app.updates.set_auto(bool(body.get("on")))
                elif parts[1] == "install":
                    return self._json(HTTPStatus.OK, app.install_update())
                else:
                    return self._error(HTTPStatus.NOT_FOUND, "Unknown address.")
                st = app.updates.state()
                return self._json(HTTPStatus.OK, {**app.update_info(), "notes": (st.get("latest") or {}).get("notes", "")})
            except UpdateError as exc:
                return self._error(HTTPStatus.BAD_REQUEST, str(exc))
        if method == "GET" and parts == ["ai"]:
            return self._json(HTTPStatus.OK, app.ai_info())
        if method == "POST" and parts[0] == "ai" and len(parts) == 2:
            try:
                body = self._body()
                if parts[1] == "settings":
                    app.ai.update(**{k: body[k] for k in ("chat_site", "model") if k in body})
                    return self._json(HTTPStatus.OK, app.ai_info())
                if parts[1] == "key":
                    return self._json(HTTPStatus.OK, {**app.ai_key(str(body.get("provider", "")), str(body.get("key", ""))), **app.ai_info()})
                if parts[1] == "forget":
                    app.ai.update(provider="", model="", connection="")
                    return self._json(HTTPStatus.OK, app.ai_info())
                if parts[1] == "models":
                    return self._json(HTTPStatus.OK, app.ai_models())
                if parts[1] == "prompt":
                    _, q, _ = app.ai_question(body)
                    return self._json(HTTPStatus.OK, {"prompt": q["text"], "masked": q["masked"]})
                if parts[1] == "ask":
                    return self._json(HTTPStatus.OK, app.ai_ask(body))
                if parts[1] == "proposal":
                    tool = app.find_tool(str(body.get("tool", "")))
                    proposal = app.ai_proposal(tool, str(body.get("answer", "")))
                    if proposal is None:
                        return self._error(HTTPStatus.BAD_REQUEST, "There's no complete script in that answer. Paste the whole "
                                           "answer, including the part between ```python and ```.")
                    return self._json(HTTPStatus.OK, {"proposal": proposal})
                if parts[1] == "apply":
                    app.ai_apply(str(body.get("tool", "")), str(body.get("code", "")), str(body.get("task", "")))
                    return self._json(HTTPStatus.OK, app.tools())
                return self._error(HTTPStatus.NOT_FOUND, "Unknown address.")
            except (NeedsUnlock, Locked) as exc:
                return self._error(HTTPStatus.LOCKED, str(exc), need="unlock")
            except (AIError, StoreError, VaultError, ValueError, OSError) as exc:
                return self._error(HTTPStatus.BAD_REQUEST, str(exc))
        if method == "GET" and parts == ["editors"]:
            found = editors_available()
            return self._json(HTTPStatus.OK, {"editors": [{"id": e["id"], "name": e["name"]} for e in found],
                                              "chosen": (choose(found, app.looks.get().get("editor", "")) or {}).get("id")})
        if method == "GET" and parts == ["templates"]:
            return self._json(HTTPStatus.OK, {"kinds": TEMPLATE_KINDS})
        if method == "GET" and parts[0] == "health" and len(parts) == 2:
            try:
                tool = app.find_tool(parts[1])
            except StoreError as exc:
                return self._error(HTTPStatus.NOT_FOUND, str(exc))
            found = app.health(tool)
            return self._json(HTTPStatus.OK, {"findings": found, "summary": health_summary(found)})
        if method == "GET" and parts[0] == "versions" and len(parts) == 2:
            try:
                tool = app.find_tool(parts[1])
            except StoreError as exc:
                return self._error(HTTPStatus.NOT_FOUND, str(exc))
            return self._json(HTTPStatus.OK, app.versions.list(tool.path, tool.id))
        if method == "POST" and parts[0] in ("edit", "health", "versions", "new-tool"):
            try:
                body = self._body()
                if parts == ["edit"]:
                    return self._json(HTTPStatus.OK, app.edit(str(body.get("tool", "")), body.get("editor")))
                if parts == ["health", "fix"]:
                    message = app.fix(str(body.get("tool", "")), str(body.get("action", "")), body)
                    return self._json(HTTPStatus.OK, {**app.tools(), "message": message})
                if parts == ["versions", "diff"]:
                    tool = app.find_tool(str(body.get("tool", "")))
                    return self._json(HTTPStatus.OK, {"lines": app.versions.diff(tool.path, tool.id, str(body.get("version", "")))})
                if parts == ["versions", "restore"]:
                    tool = app.find_tool(str(body.get("tool", "")))
                    app.versions.restore(tool.path, tool.id, str(body.get("version", "")))
                    return self._json(HTTPStatus.OK, app.tools())
                if parts == ["new-tool"]:
                    result = app.new_tool(body)
                    return self._json(HTTPStatus.OK, {**app.tools(), "result": result})
                return self._error(HTTPStatus.NOT_FOUND, "Unknown address.")
            except (StoreError, ValueError, OSError) as exc:
                return self._error(HTTPStatus.BAD_REQUEST, str(exc))
        if method == "POST" and parts[0] == "layout" and len(parts) == 2:
            try:
                app.layout_call(parts[1], self._body())
                return self._json(HTTPStatus.OK, app.tools())
            except (StoreError, ValueError, TypeError) as exc:
                return self._error(HTTPStatus.BAD_REQUEST, str(exc))
        if method == "POST" and parts[0] == "programs" and len(parts) == 2 and parts[1] in ("tidy", "visibility"):
            from ..importer import ImportProblem, tidy
            try:
                body = self._body()
                if parts[1] == "tidy":
                    result = tidy(app.home, str(body.get("folder", "")))
                else:
                    tool = app.home.find(str(body.get("tool", "")))
                    if not tool.group:
                        raise ImportProblem("Only the scripts of a program can be hidden.")
                    hide = bool(body.get("hidden"))
                    app.home.set_hidden(tool.group, {tool.id} if hide else set(), set() if hide else {tool.id})
                    result = {}
                return self._json(HTTPStatus.OK, {"result": result, **app.tools()})
            except (ImportProblem, LookupError, OSError) as exc:
                return self._error(HTTPStatus.BAD_REQUEST, str(exc))
        if method == "POST" and parts[0] == "import" and len(parts) == 2 and parts[1] in ("scan", "apply"):
            from ..importer import ImportProblem, apply as do_import, scan as scan_import
            try:
                body = self._body()
                if parts[1] == "scan":
                    return self._json(HTTPStatus.OK, scan_import(str(body.get("path", "")), app.home))
                report = do_import(str(body.get("path", "")), app.home, dict(body.get("choices") or {}))
                return self._json(HTTPStatus.OK, {"report": report, **app.tools()})
            except (ImportProblem, OSError, ValueError) as exc:
                return self._error(HTTPStatus.BAD_REQUEST, str(exc))

        if method == "POST" and parts[0] == "schedules" and len(parts) == 2:
            try:
                body = self._body()
                action = parts[1]
                if action == "preview":
                    when = check_when(dict(body.get("when") or {}))
                    now = datetime.datetime.now()
                    upcoming = next_times(when, now, 3)
                    return self._json(HTTPStatus.OK, {"sentence": describe(when),
                                                      "next": [nice_time(t, now) for t in upcoming]})
                if action == "save":
                    return self._json(HTTPStatus.OK, app.save_plan(body))
                if action == "delete":
                    gone = app.plans.delete(str(body.get("id", "")))
                    try:
                        sync_plan(app.plans, app.system, removed=gone)
                    except (OSError, subprocess.SubprocessError):
                        pass  # a leftover task finds no plan and does nothing
                    return self._json(HTTPStatus.OK, app.plans_json())
                if action == "toggle":
                    plan = app.plans.update(str(body.get("id", "")), enabled=bool(body.get("enabled")))
                    sync_plan(app.plans, app.system, plan, password=body.get("password") or None)
                    return self._json(HTTPStatus.OK, app.plans_json())
                if action in ("run-now", "fire"):
                    result = app.fire_plan(str(body.get("id", "")), force=action == "run-now" or bool(body.get("force")))
                    return self._json(HTTPStatus.OK, {**result, **app.plans_json()})
                return self._error(HTTPStatus.NOT_FOUND, "Not found.")
            except NeedsPassword as exc:
                return self._error(HTTPStatus.PRECONDITION_REQUIRED, str(exc), need="password")
            except NeedsUnlock as exc:
                return self._error(HTTPStatus.LOCKED, str(exc), need="unlock")
            except NeedsPermission as exc:
                return self._error(HTTPStatus.PRECONDITION_REQUIRED, str(exc), need="allow", connections=exc.names)
            except (StoreError, VaultError, LookupError, ValueError) as exc:
                return self._error(HTTPStatus.BAD_REQUEST, str(exc))

        if parts[0] == "chains" and len(parts) >= 3 and parts[1] == "runs":
            with app.lock:
                chain_run = app.chain_runs.get(parts[2])
            if chain_run is None:
                return self._error(HTTPStatus.NOT_FOUND, "That chain run isn't known in this session.")
            if method == "GET" and len(parts) == 3:
                return self._json(HTTPStatus.OK, chain_run.summary())
            if method == "POST" and parts[3:] == ["stop"]:
                chain_run.stop()
                return self._json(HTTPStatus.OK, {"stopping": True})

        if route == ("GET", "history"):
            tool = (query.get("tool") or [None])[0]
            limit = min(int((query.get("limit") or ["100"])[0]), 500)
            return self._json(HTTPStatus.OK, {"runs": history(app.home, tool, limit=limit)})

        if route == ("GET", "active"):
            return self._json(HTTPStatus.OK, {"runs": app.active()})

        if route == ("POST", "runs") and len(parts) == 1:
            try:
                body = self._body()
                live = app.start(str(body.get("tool", "")), dict(body.get("settings") or {}), allow=bool(body.get("allow")))
            except SettingError as exc:
                return self._error(HTTPStatus.BAD_REQUEST, "Some settings need a look.", problems=str(exc).splitlines())
            except NeedsUnlock as exc:
                return self._error(HTTPStatus.LOCKED, str(exc), need="unlock")
            except NeedsPermission as exc:
                return self._error(HTTPStatus.PRECONDITION_REQUIRED, str(exc), need="allow", connections=exc.names)
            except VaultError as exc:
                return self._error(HTTPStatus.BAD_REQUEST, str(exc))
            except Busy as exc:
                return self._error(HTTPStatus.CONFLICT, str(exc))
            except (LookupError, LabelError, EngineMissing, ValueError) as exc:
                return self._error(HTTPStatus.BAD_REQUEST, str(exc))
            return self._json(HTTPStatus.CREATED, live.summary())

        if parts[0] == "runs" and len(parts) >= 2:
            live = app.get(parts[1])
            if method == "GET" and len(parts) == 3 and parts[2] == "log":
                try:
                    return self._json(HTTPStatus.OK, {"log": app.log_tail(parts[1])})
                except PermissionError as exc:
                    return self._error(HTTPStatus.NOT_FOUND, str(exc))
            if live is None:
                return self._error(HTTPStatus.NOT_FOUND, "That run isn't known in this session.")
            if method == "GET" and len(parts) == 2:
                return self._json(HTTPStatus.OK, live.summary())
            if method == "GET" and parts[2:] == ["events"]:
                return self._stream(live, int((query.get("after") or ["0"])[0]))
            if method == "POST" and parts[2:] == ["stop"]:
                live.run.cancel()
                return self._json(HTTPStatus.OK, {"stopping": True})

        if route == ("POST", "open-url"):
            body = self._body()
            url = str(body.get("url", ""))
            allowed = {u for _, u in ai_help.CHAT_SITES.values()} | {p["keys"] for p in ai_help.PROVIDERS.values()}
            from ..project import HOME_PAGE, configured
            if url not in allowed and not (configured() and (url == HOME_PAGE or url.startswith(HOME_PAGE + "/"))):
                return self._error(HTTPStatus.BAD_REQUEST, "traPYze only opens its own known web addresses.")
            import webbrowser
            webbrowser.open(url)
            return self._json(HTTPStatus.OK, {"opened": url})
        if route == ("POST", "open"):
            try:
                body = self._body()
                path = app.resolve_inside_home(str(body.get("path", "")))
                open_with_system(path, reveal=bool(body.get("reveal")))
            except (PermissionError, FileNotFoundError, ValueError) as exc:
                return self._error(HTTPStatus.BAD_REQUEST, str(exc))
            except OSError as exc:
                return self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"Couldn't open it: {exc}")
            return self._json(HTTPStatus.OK, {"opened": True})

        if route == ("POST", "pick"):
            try:
                body = self._body()
                kind = "folder" if body.get("kind") == "folder" else "file"
                start = str(body.get("start") or app.home.data)
                return self._json(HTTPStatus.OK, {"path": pick_path(kind, start)})
            except (RuntimeError, subprocess.TimeoutExpired, ValueError) as exc:
                return self._error(HTTPStatus.SERVICE_UNAVAILABLE, str(exc) or "The file picker isn't available.")

        return self._error(HTTPStatus.NOT_FOUND, "Not found.")

    def _stream(self, live: LiveRun, after: int) -> None:
        """Server-sent events: replay what the browser missed, then follow live."""
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        last = after
        quiet_since = time.monotonic()
        while True:
            batch = live.since(last)
            for event in batch:
                self.wfile.write(f"id: {event['n']}\ndata: {json.dumps(event, default=str)}\n\n".encode("utf-8"))
                last = event["n"]
            if batch:
                self.wfile.flush()
                quiet_since = time.monotonic()
                if batch[-1]["kind"] == "finished":
                    return
            elif not live.run.running and live.run.result is not None and live.serial <= last:
                return
            elif time.monotonic() - quiet_since > 15:
                self.wfile.write(b": still here\n\n")
                self.wfile.flush()
                quiet_since = time.monotonic()
            live.wait(last, timeout=1.0)


class TrapyzeServer(ThreadingHTTPServer):
    """The web server, bound to 127.0.0.1. On Windows, SO_REUSEADDR would let a second
    program (or a second traPYze) listen on the same port and receive our requests;
    there the port is taken exclusively instead."""

    allow_reuse_address = os.name != "nt"

    def server_bind(self) -> None:
        if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def make_server(home: Home, port: int = 0) -> tuple[ThreadingHTTPServer, App]:
    """A ready server bound to 127.0.0.1. Port 0 picks a free one."""
    app = App(home)
    handler = type("TrapyzeHandler", (Handler,), {"app": app})
    candidates = [port] if port else list(range(8765, 8786)) + [0]
    last_error: OSError | None = None
    for p in candidates:
        try:
            server = TrapyzeServer(("127.0.0.1", p), handler)
            break
        except OSError as exc:
            last_error = exc
    else:  # pragma: no cover
        raise last_error or OSError("No free port.")
    server.daemon_threads = True
    handler.port = server.server_address[1]
    return server, app


def serve(home: Home, port: int = 0, open_browser: bool = True) -> int:
    server, app = make_server(home, port)
    url = f"http://127.0.0.1:{server.server_address[1]}/?t={app.token}"
    print("traPYze is open in your browser.")
    print(f"If it didn't open, paste this address into it:\n  {url}")
    print("Keep this window open while you use traPYze. Press Ctrl+C here to close it.")
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()

    def close() -> None:
        for live in list(app.runs.values()):
            if live.run.running:
                live.run.cancel()
        server.shutdown()
    app.quit_hook = close
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        while thread.is_alive():
            thread.join(0.3)  # short waits so Ctrl+C works on Windows too
    except KeyboardInterrupt:
        print("Closing traPYze…")
        for live in list(app.runs.values()):
            if live.run.running:
                live.run.cancel()
        server.shutdown()
    return 0

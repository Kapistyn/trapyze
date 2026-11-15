"""The Tools desktop: shelves, favourites, topics and the first sorting.

The arrangement lives in traPYze's own folder (internal/layout.json); the
user's scripts are never changed. Items are keyed "tool:<id>" or
"chain:<id>". The first time, traPYze sorts every item onto a shelf by what
it does. After that, new items wait on the "New" shelf until the user opens
them or drags them somewhere; then they go to the suggested shelf.
"""

from __future__ import annotations

import re
import threading
from pathlib import Path
from typing import Any, Iterable

from .store import StoreError, _read, _write

_lock = threading.RLock()

# Universal shelves, named after what a script does (not what it is about).
DEFAULT_SHELVES = [
    {"id": "collect", "name": "Collect", "hint": "Fetching and updating data"},
    {"id": "analyse", "name": "Analyse", "hint": "Turning data into results"},
    {"id": "share", "name": "Share", "hint": "Reports, mail and alerts"},
    {"id": "maintain", "name": "Maintain", "hint": "Cleanup, backups and small tools"},
    {"id": "apps", "name": "Apps", "hint": "Programs with their own window"},
]
# Imports that mean the script opens its own window (a game, a small program, a dashboard).
APP_IMPORT = re.compile(r"^\s*(?:import|from)\s+(tkinter|customtkinter|pygame|pyglet|arcade|kivy|PyQt[56]|PySide[26]|wx|"
                        r"dash|flet|nicegui|gradio|dearpygui|toga|webview|ursina|panda3d)\b", re.M)
VIEWS = ("desktop", "cards", "list")

_WORDS = {
    "collect": ("fetch", "download", "update", "updater", "scrape", "scraper", "collect", "collector", "import",
                "harvest", "load", "loader", "sync", "pull", "get", "prices", "quotes", "feed", "ingest", "build"),
    "analyse": ("rank", "ranker", "ranking", "score", "scoring", "scan", "scanner", "screen", "screener", "analyse",
                "analyze", "analysis", "signal", "signals", "backtest", "chart", "study", "model", "evaluate",
                "evaluator", "forecast", "predict", "classify", "select", "selection", "indicator", "stats", "compare"),
    "share": ("mail", "email", "gmail", "smtp", "send", "sender", "notify", "notification", "alert", "alerts",
              "report", "reporter", "telegram", "slack", "discord", "pdf", "newsletter", "digest", "summary", "publish"),
    "maintain": ("clean", "cleanup", "backup", "tidy", "rename", "move", "convert", "archive", "delete", "purge",
                 "compress", "zip", "copy", "organise", "organize", "fix", "check", "test", "setup"),
}
_PACKAGES = {
    "collect": ("requests", "httpx", "aiohttp", "yfinance", "ccxt", "ib_insync", "ib-insync", "ib_async", "alpaca",
                "polygon", "beautifulsoup4", "bs4", "selenium", "playwright", "scrapy", "feedparser", "eodhd"),
    "analyse": ("pandas", "numpy", "scipy", "scikit-learn", "sklearn", "statsmodels", "matplotlib", "plotly",
                "ta", "ta-lib", "pandas-ta", "polars", "seaborn", "vectorbt", "backtrader"),
    "share": ("yagmail", "reportlab", "fpdf", "fpdf2", "python-telegram-bot", "slack-sdk", "jinja2", "weasyprint"),
}
_SOURCE = {
    "share": ("smtplib", "yagmail", "send_message", "sendmail", "reportlab", "fpdf", "telegram", "webhook"),
    "collect": ("requests.get", "urlopen", "httpx.", "download(", ".history(", "yf.download"),
    "maintain": ("shutil.rmtree", "shutil.move", "os.remove", "unlink(", "make_archive", "zipfile"),
}
_STOP = {
    "the", "and", "for", "with", "from", "into", "your", "this", "that", "tool", "tools", "script", "scripts",
    "main", "run", "runner", "app", "program", "data", "file", "files", "new", "old", "test", "daily", "weekly",
    "py", "v1", "v2", "v3", "all", "my", "of", "to", "in", "on", "by", "a", "an",
    # Everyday words that say little about what a group of tools is about.
    "market", "markets", "stock", "stocks", "price", "prices", "morning", "evening", "night", "day", "days",
    "week", "month", "year", "today", "index", "list", "values", "value", "result", "results", "info", "helper",
    "helpers", "utils", "util", "engine", "core", "simple", "quick", "big", "small", "top", "best", "auto",
}
_STOP.update(w for words in _WORDS.values() for w in words)


def _tokens(text: str) -> list[str]:
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text or "")
    return [t for t in re.split(r"[^A-Za-z0-9]+", text) if t]


def _words(text: str) -> set[str]:
    return {t.lower() for t in _tokens(text)}


def suggest(tool: Any, source: str | None = None) -> str:
    """Which shelf a tool most likely belongs on, from what it does."""
    if source is None:
        try:
            source = tool.path.read_text(encoding="utf-8", errors="replace")[:200_000]
        except OSError:
            source = ""
    if APP_IMPORT.search(source):
        return "apps"
    score = {k: 0.0 for k in ("collect", "analyse", "share", "maintain")}
    name = _words(f"{tool.name} {tool.id} {tool.path.stem}")
    desc = _words(tool.description)
    for shelf, words in _WORDS.items():
        for w in words:
            if w in name:
                score[shelf] += 3
            if w in desc:
                score[shelf] += 1
    for c in tool.connections:
        cw = _words(c)
        if cw & {"mail", "gmail", "smtp", "email", "telegram", "slack", "discord", "outlook"}:
            score["share"] += 4
        else:
            score["collect"] += 1
    deps = {re.split(r"[<>=!~\[; ]", d.strip(), maxsplit=1)[0].lower() for d in tool.dependencies}
    for shelf, pkgs in _PACKAGES.items():
        score[shelf] += sum(1 for p in pkgs if p in deps)
    if tool.writes:
        score["collect"] += 3
    if tool.reads:
        score["analyse"] += 2
    for shelf, bits in _SOURCE.items():
        score[shelf] += sum(2 for b in bits if b in source)
    best = max(score, key=lambda k: (score[k], -list(score).index(k)))
    return best if score[best] > 0 else "maintain"


def suggest_chain(chain: Any, suggested: dict[str, str]) -> str:
    """A chain sits where its last step's tool sits (usually what it ends with: a mail, a ranking)."""
    for step in reversed(chain.steps):
        if f"tool:{step.tool}" in suggested:
            return suggested[f"tool:{step.tool}"]
    return "maintain"


def topics(items: dict[str, str], minimum: int = 2, limit: int = 8) -> list[dict[str, Any]]:
    """Recurring words in item names (AEX, NDX100, Crypto…), offered as filter chips.

    `items` maps an item key to the text to look in (name, file, program folder).
    A word counts when it appears in at least `minimum` items but not in all of them.
    """
    seen: dict[str, set[str]] = {}
    shown: dict[str, str] = {}
    for key, text in items.items():
        for tok in _tokens(text):
            low = tok.lower()
            if low in _STOP or len(low) < 2 or low.isdigit():
                continue
            seen.setdefault(low, set()).add(key)
            if low not in shown or (tok.isupper() and not shown[low].isupper()):
                shown[low] = tok
    total = len(items)
    def code_like(low: str) -> bool:
        return shown[low].isupper() or any(ch.isdigit() for ch in low)
    found = [(low, keys) for low, keys in seen.items()
             if len(keys) >= (minimum if code_like(low) else minimum + 1) and len(keys) < total]
    # Drop a word whose items are exactly those of a longer word ("ndx" next to "ndx100").
    found.sort(key=lambda x: (-len(x[1]), -len(x[0]), x[0]))
    out: list[dict[str, Any]] = []
    for low, keys in found:
        if any(set(o["items"]) == keys and (low in o["key"] or o["key"] in low) for o in out):
            continue
        label = shown[low]
        if not label.isupper():
            label = label.upper() if len(label) <= 4 else label[0].upper() + label[1:]
        out.append({"key": low, "name": label, "items": sorted(keys)})
        if len(out) >= limit:
            break
    return out


class Layout:
    """{"view", "shelves": [{"id", "name", "folded", "items": [...]}], "favourites": [...], "new": [...],
        "topics": bool}"""

    def __init__(self, internal: Path):
        self.path = internal / "layout.json"

    def _raw(self) -> dict[str, Any]:
        data = _read(self.path, {})
        return data if isinstance(data, dict) else {}

    def arrange(self, suggested: dict[str, str]) -> dict[str, Any]:
        """The arrangement for these items (key -> suggested shelf), placing any that are new."""
        with _lock:
            data = self._raw()
            first = not data.get("shelves")
            changed = first
            if first:
                data = {"view": data.get("view", "desktop"), "favourites": [], "new": [], "topics": True, "added": ["apps"],
                        "shelves": [{"id": s["id"], "name": s["name"], "folded": False, "items": []} for s in DEFAULT_SHELVES]}
            if not first and "apps" not in data.get("added", []):
                data.setdefault("added", []).append("apps")
                if not any(s["id"] == "apps" for s in data["shelves"]):
                    data["shelves"].append({"id": "apps", "name": "Apps", "folded": False, "items": []})
                changed = True
            shelves = data["shelves"]
            placed = {k for s in shelves for k in s.get("items", [])} | set(data.get("new", []))
            for key in suggested:
                if key in placed:
                    continue
                changed = True
                if first:
                    self._shelf(data, suggested[key]).setdefault("items", []).append(key)
                else:
                    data.setdefault("new", []).append(key)
            if changed:
                _write(self.path, data)
            return self._view(data, suggested)

    @staticmethod
    def _shelf(data: dict[str, Any], shelf_id: str) -> dict[str, Any]:
        for s in data["shelves"]:
            if s["id"] == shelf_id:
                return s
        default = next((d for d in DEFAULT_SHELVES if d["id"] == shelf_id), None)
        if default is None:
            if not data["shelves"]:
                data["shelves"].append({"id": "maintain", "name": "Maintain", "folded": False, "items": []})
            return data["shelves"][-1]
        s = {"id": default["id"], "name": default["name"], "folded": False, "items": []}
        data["shelves"].append(s)
        return s

    @staticmethod
    def _view(data: dict[str, Any], suggested: dict[str, str]) -> dict[str, Any]:
        hints = {d["id"]: d["hint"] for d in DEFAULT_SHELVES}
        return {
            "view": data.get("view", "desktop") if data.get("view") in VIEWS else "desktop",
            "topics": data.get("topics", True),
            "favourites": [k for k in data.get("favourites", []) if k in suggested],
            "new": [k for k in data.get("new", []) if k in suggested],
            "shelves": [{"id": s["id"], "name": s["name"], "folded": bool(s.get("folded")),
                         "hint": hints.get(s["id"], ""),
                         "items": [k for k in s.get("items", []) if k in suggested]} for s in data["shelves"]],
            "suggested": suggested,
        }

    def _change(self, fn) -> None:
        with _lock:
            data = self._raw()
            if not data.get("shelves"):
                raise StoreError("The desktop isn't set up yet. Open the Tools screen first.")
            fn(data)
            _write(self.path, data)

    @staticmethod
    def _take(data: dict[str, Any], key: str) -> None:
        for s in data["shelves"]:
            if key in s.get("items", []):
                s["items"].remove(key)
        if key in data.get("new", []):
            data["new"].remove(key)

    def move(self, key: str, shelf: str, before: str | None = None) -> None:
        def fn(data):
            target = next((s for s in data["shelves"] if s["id"] == shelf), None)
            if target is None:
                raise StoreError("That shelf doesn't exist any more.")
            self._take(data, key)
            items = target.setdefault("items", [])
            items.insert(items.index(before) if before in items else len(items), key)
        self._change(fn)

    def seen(self, key: str, suggested_shelf: str) -> None:
        """A new item was opened: move it from New to its suggested shelf."""
        def fn(data):
            if key in data.get("new", []):
                data["new"].remove(key)
                self._shelf(data, suggested_shelf).setdefault("items", []).append(key)
        self._change(fn)

    def favourite(self, key: str, on: bool) -> None:
        def fn(data):
            fav = data.setdefault("favourites", [])
            if on and key not in fav:
                fav.append(key)
            if not on and key in fav:
                fav.remove(key)
        self._change(fn)

    def set_view(self, view: str) -> None:
        if view not in VIEWS:
            raise StoreError("Choose desktop, cards or list.")
        with _lock:
            data = self._raw()
            data["view"] = view
            _write(self.path, data)

    def set_topics(self, on: bool) -> None:
        self._change(lambda data: data.__setitem__("topics", bool(on)))

    def add_shelf(self, name: str) -> str:
        name = _clean_name(name)
        new_id = ""

        def fn(data):
            nonlocal new_id
            if any(s["name"].lower() == name.lower() for s in data["shelves"]):
                raise StoreError(f"There is already a shelf called “{name}”.")
            base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "shelf"
            new_id, n = base, 2
            while any(s["id"] == new_id for s in data["shelves"]) or new_id == "new":
                new_id, n = f"{base}-{n}", n + 1
            data["shelves"].append({"id": new_id, "name": name, "folded": False, "items": []})
        self._change(fn)
        return new_id

    def rename_shelf(self, shelf: str, name: str) -> None:
        name = _clean_name(name)

        def fn(data):
            s = next((s for s in data["shelves"] if s["id"] == shelf), None)
            if s is None:
                raise StoreError("That shelf doesn't exist any more.")
            if any(o is not s and o["name"].lower() == name.lower() for o in data["shelves"]):
                raise StoreError(f"There is already a shelf called “{name}”.")
            s["name"] = name
        self._change(fn)

    def fold_shelf(self, shelf: str, folded: bool) -> None:
        def fn(data):
            for s in data["shelves"]:
                if s["id"] == shelf:
                    s["folded"] = bool(folded)
        self._change(fn)

    def move_shelf(self, shelf: str, step: int) -> None:
        def fn(data):
            ids = [s["id"] for s in data["shelves"]]
            if shelf not in ids:
                raise StoreError("That shelf doesn't exist any more.")
            i = ids.index(shelf)
            j = max(0, min(len(ids) - 1, i + step))
            data["shelves"].insert(j, data["shelves"].pop(i))
        self._change(fn)

    def delete_shelf(self, shelf: str) -> None:
        """Remove a shelf; its tiles move to the first remaining shelf."""
        def fn(data):
            s = next((s for s in data["shelves"] if s["id"] == shelf), None)
            if s is None:
                return
            if len(data["shelves"]) == 1:
                raise StoreError("Keep at least one shelf.")
            data["shelves"].remove(s)
            data["shelves"][0].setdefault("items", []).extend(s.get("items", []))
        self._change(fn)

    def resort(self, suggested: dict[str, str]) -> None:
        """Sort everything again by suggestion. Own shelves stay (emptied); favourites stay."""
        def fn(data):
            for s in data["shelves"]:
                s["items"] = []
            data["new"] = []
            for key, shelf in suggested.items():
                self._shelf(data, shelf).setdefault("items", []).append(key)
        self._change(fn)


def _clean_name(name: str) -> str:
    name = " ".join(str(name or "").split())[:40]
    if not name:
        raise StoreError("Give the shelf a name.")
    return name


def item_texts(tools: Iterable[Any], chains: Iterable[Any], programs: dict[str, dict]) -> dict[str, str]:
    """The text topics are looked for in, per item."""
    out = {}
    for t in tools:
        prog = programs.get(t.group or "", {}).get("name", "") if t.group else ""
        out[f"tool:{t.id}"] = f"{t.name} {t.path.stem} {t.group or ''} {prog}"
    for c in chains:
        out[f"chain:{c.id}"] = c.name
    return out

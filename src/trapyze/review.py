"""A look before the first run, for tools you didn't write yourself.

A tool is a program: it can do anything you can do on this computer, and traPYze has no
sandbox. So a tool that was imported or written by an AI waits for one look: what it
wants to do (the internet, keys from the vault, deleting files, starting other programs)
and what the health check found. After "I've looked, run it" it runs like any other tool.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from .importer import PyInfo
from .store import _read, _write

_lock = threading.RLock()
ORIGINS = {"imported": "It was imported", "ai": "An AI wrote it"}
NET = {"requests", "httpx", "aiohttp", "urllib", "urllib3", "socket", "http", "ftplib", "smtplib", "imaplib", "poplib",
       "websocket", "websockets", "paramiko", "yfinance", "selenium", "playwright", "telegram", "discord", "boto3"}
PROGRAMS = {"subprocess", "ctypes", "winreg", "pty", "multiprocessing"}


class NeedsReview(Exception):
    def __init__(self, tool_id: str, name: str):
        super().__init__(f"Have a look at {name} before its first run.")
        self.tool_id = tool_id


class Reviews:
    """internal/review.json: {tool id: origin} for tools that still wait for their first look."""

    def __init__(self, internal: Path):
        self.path = internal / "review.json"

    def _all(self) -> dict[str, str]:
        data = _read(self.path, {})
        return data if isinstance(data, dict) else {}

    def pending(self, tool_id: str) -> str | None:
        return self._all().get(tool_id)

    def all(self) -> dict[str, str]:
        return self._all()

    def mark(self, tool_ids: list[str], origin: str) -> None:
        with _lock:
            data = self._all()
            data.update({t: origin for t in tool_ids})
            _write(self.path, data)

    def accept(self, tool_id: str) -> None:
        with _lock:
            data = self._all()
            if data.pop(tool_id, None) is not None:
                _write(self.path, data)

    def tidy(self, existing: set[str]) -> None:
        with _lock:
            data = self._all()
            kept = {k: v for k, v in data.items() if k in existing}
            if kept != data:
                _write(self.path, kept)


def wants(tool: Any, source: str, findings: list[dict[str, Any]]) -> list[str]:
    """What this tool can do beyond reading and writing its own files, in plain words."""
    out = []
    try:
        imports = {i.split(".")[0] for i in PyInfo(tool.path.name, source).imports}
    except (SyntaxError, ValueError):
        imports = set()
    codes = {f["code"] for f in findings}
    if tool.connections:
        out.append("Use these keys from your vault: " + ", ".join(tool.connections) + " (you're asked again before it gets them)")
    net = sorted(imports & NET)
    if net or "trapyze_helper" in imports and "tz.api(" in source:
        out.append("Use the internet" + (f" (through {', '.join(net[:4])})" if net else ""))
    if codes & {"rmtree", "delete"}:
        out.append("Delete files or folders")
    if codes & {"shell", "eval"} or imports & PROGRAMS:
        out.append("Start other programs or run commands")
    if "path" in codes:
        out.append("Use a fixed folder outside traPYze")
    if tool.writes:
        out.append("Change shared data: " + ", ".join(tool.writes))
    return out

"""Versions of each tool's script: a copy whenever it changes, with going back in one click.

Copies live in traPYze's own folder (.trapyze/versions/<tool>/), never next to the script.
A copy is only made when the content differs from the newest one, so nothing piles up.
"""

from __future__ import annotations

import difflib
import re
import threading
import time
from pathlib import Path
from typing import Any

from .store import StoreError, _read, _write

MAX_VERSIONS = 40
_lock = threading.RLock()


def _safe(tool_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", tool_id).strip("._") or "tool"


class Versions:
    def __init__(self, internal: Path):
        self.root = internal / "versions"

    def _dir(self, tool_id: str) -> Path:
        return self.root / _safe(tool_id)

    def _index(self, tool_id: str) -> list[dict[str, Any]]:
        data = _read(self._dir(tool_id) / "index.json", [])
        return data if isinstance(data, list) else []

    def _text(self, tool_id: str, vid: str) -> str:
        if not re.fullmatch(r"\d+", vid or ""):
            raise StoreError("Unknown version.")
        f = self._dir(tool_id) / f"{vid}.py"
        if not f.exists():
            raise StoreError("That version isn't there any more.")
        return f.read_text(encoding="utf-8", errors="replace")

    def snapshot(self, path: Path, tool_id: str, reason: str) -> dict[str, Any] | None:
        """Keep a copy of the script as it is now, unless the newest copy is the same."""
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
        with _lock:
            index = self._index(tool_id)
            if index and self._same(tool_id, index[0]["id"], text):
                return None
            folder = self._dir(tool_id)
            folder.mkdir(parents=True, exist_ok=True)
            vid = str(time.time_ns())
            if index and int(vid) <= int(index[0]["id"]):
                vid = str(int(index[0]["id"]) + 1)
            (folder / f"{vid}.py").write_text(text, encoding="utf-8")
            entry = {"id": vid, "time": int(vid) / 1e9, "reason": reason, "lines": text.count("\n") + 1}
            index.insert(0, entry)
            for old in index[MAX_VERSIONS:]:
                (folder / f"{old['id']}.py").unlink(missing_ok=True)
            _write(folder / "index.json", index[:MAX_VERSIONS])
            return entry

    def _same(self, tool_id: str, vid: str, text: str) -> bool:
        try:
            return self._text(tool_id, vid) == text
        except StoreError:
            return False

    def count(self, tool_id: str) -> int:
        return len(self._index(tool_id))

    def list(self, path: Path, tool_id: str) -> dict[str, Any]:
        index = self._index(tool_id)
        try:
            current = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            current = ""
        return {"versions": index, "changed": bool(index) and not self._same(tool_id, index[0]["id"], current)}

    def diff(self, path: Path, tool_id: str, vid: str) -> list[dict[str, str]]:
        """What changed from that version to the script as it is now, line by line."""
        return diff_lines(self._text(tool_id, vid), path.read_text(encoding="utf-8", errors="replace"))

    def restore(self, path: Path, tool_id: str, vid: str) -> None:
        text = self._text(tool_id, vid)
        with _lock:
            self.snapshot(path, tool_id, "Before going back")
            path.write_text(text, encoding="utf-8")
            self.snapshot(path, tool_id, "Went back to an earlier version")


def diff_lines(old_text: str, new_text: str) -> list[dict[str, str]]:
    out = []
    for line in difflib.unified_diff(old_text.splitlines(), new_text.splitlines(), "then", "now", n=2, lineterm=""):
        if line.startswith(("---", "+++")):
            continue
        kind = "hunk" if line.startswith("@@") else "add" if line.startswith("+") else "del" if line.startswith("-") else "same"
        out.append({"kind": kind, "text": line if kind == "hunk" else line[1:]})
    return out

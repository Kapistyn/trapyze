"""A bin for removed tools: nothing is deleted at once. Items stay 30 days, and can be put back."""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any

KEEP_DAYS = 30


class BinError(Exception):
    pass


class Bin:
    def __init__(self, home) -> None:
        self.home = home
        self.root = home.internal / "bin"

    def _entries(self) -> list[Path]:
        return sorted((p for p in self.root.iterdir() if p.is_dir() and (p / "info.json").exists()), reverse=True) if self.root.is_dir() else []

    def put(self, rel: str, label: str, kind: str) -> str:
        """Move scripts/<rel> (a file, plus its .lock, or a whole program folder) into the bin."""
        src = (self.home.scripts / rel)
        if not src.exists():
            raise BinError("That file isn't there any more.")
        stamp = time.strftime("%Y%m%d-%H%M%S")
        slot = self.root / f"{stamp}-{Path(rel).stem}"
        slot.mkdir(parents=True, exist_ok=True)
        moved = [rel]
        shutil.move(str(src), str(slot / Path(rel).name))
        lock = src.with_name(src.name + ".lock")
        if kind == "tool" and lock.exists():
            shutil.move(str(lock), str(slot / lock.name))
            moved.append(rel + ".lock")
        (slot / "info.json").write_text(json.dumps({"name": label, "kind": kind, "rel": rel, "moved": moved, "removed": time.time()}), encoding="utf-8")
        return slot.name

    def items(self) -> list[dict[str, Any]]:
        self.purge()
        out = []
        for slot in self._entries():
            info = json.loads((slot / "info.json").read_text(encoding="utf-8"))
            left = KEEP_DAYS - int((time.time() - info["removed"]) // 86400)
            out.append({"id": slot.name, "name": info["name"], "kind": info["kind"], "removed": info["removed"], "days_left": max(left, 0)})
        return out

    def restore(self, slot_id: str) -> str:
        slot = self.root / Path(slot_id).name
        if not (slot / "info.json").exists():
            raise BinError("That item isn't in the bin any more.")
        info = json.loads((slot / "info.json").read_text(encoding="utf-8"))
        target = self.home.scripts / info["rel"]
        if target.exists():
            raise BinError(f"There is already something called {target.name} in the scripts folder. Rename or remove it first.")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(slot / target.name), str(target))
        lock = slot / (target.name + ".lock")
        if lock.exists():
            shutil.move(str(lock), str(target.with_name(target.name + ".lock")))
        shutil.rmtree(slot, ignore_errors=True)
        return info["name"]

    def purge(self) -> None:
        limit = time.time() - KEEP_DAYS * 86400
        for slot in self._entries():
            try:
                if json.loads((slot / "info.json").read_text(encoding="utf-8"))["removed"] < limit:
                    shutil.rmtree(slot, ignore_errors=True)
            except (OSError, ValueError, KeyError):
                continue

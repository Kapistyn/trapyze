"""When a script moves or is renamed its tool id changes. This carries everything that was tied to the old id along:
presets, remembered settings, plans, chains, the tile's look and place, saved versions, and the key permissions."""
from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Any

from .home import Home

_lock = threading.RLock()


def _read(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _write(path: Path, data: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
    tmp.replace(path)


def _rekey(data: Any, mapping: dict[str, str]) -> bool:
    changed = False
    if isinstance(data, dict):
        for old, new in mapping.items():
            if old in data and new not in data:
                data[new] = data.pop(old)
                changed = True
    return changed


def _safe(tool_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", tool_id).strip("._") or "tool"


def retarget(home: Home, mapping: dict[str, str], vault: Any = None) -> list[str]:
    """Rewrite every place that names a tool. Returns notes for the person (things that could not be carried over)."""
    mapping = {a: b for a, b in mapping.items() if a != b}
    notes: list[str] = []
    if not mapping:
        return notes
    inner = home.internal
    with _lock:
        for name in ("presets.json", "last_settings.json"):
            path = inner / name
            data = _read(path, None)
            if isinstance(data, dict) and _rekey(data, mapping):
                _write(path, data)
        path = inner / "looks.json"
        data = _read(path, None)
        if isinstance(data, dict) and isinstance(data.get("tools"), dict):
            if _rekey(data["tools"], mapping):
                _write(path, data)
            for old, new in mapping.items():
                for img in (inner / "icons").glob(f"{old}.*") if (inner / "icons").is_dir() else []:
                    img.replace(img.with_name(f"{new}{img.suffix}"))
        path = inner / "layout.json"
        data = _read(path, None)
        if isinstance(data, dict):
            changed = False
            lists = [s.get("items", []) for s in data.get("shelves", []) if isinstance(s, dict)] + [data.get("favourites", []), data.get("new", [])]
            for items in lists:
                for i, key in enumerate(items):
                    if key in mapping:
                        items[i] = mapping[key]
                        changed = True
            if changed:
                _write(path, data)
        path = inner / "chains.json"
        data = _read(path, None)
        if isinstance(data, dict):
            changed = False
            for chain in data.get("chains", []):
                for step in chain.get("steps", []):
                    if step.get("tool") in mapping:
                        step["tool"] = mapping[step["tool"]]
                        changed = True
            if changed:
                _write(path, data)
        path = inner / "schedules.json"
        data = _read(path, None)
        if isinstance(data, dict):
            changed = False
            for plan in data.get("plans", []):
                if plan.get("target_kind") == "tool" and plan.get("target") in mapping:
                    plan["target"] = mapping[plan["target"]]
                    changed = True
            if changed:
                _write(path, data)
        for old, new in mapping.items():
            src, dst = inner / "versions" / _safe(old), inner / "versions" / _safe(new)
            if src.is_dir() and not dst.exists():
                src.replace(dst)
    if vault is not None:
        try:
            if vault.unlocked():
                vault.rename_tools(mapping)
            elif vault.path.exists():
                notes.append("Your vault is locked, so permissions for keys could not move along. Open a moved tool once and allow its keys again.")
        except Exception:
            notes.append("Permissions for keys could not move along. Allow them again when the tool asks.")
    return notes

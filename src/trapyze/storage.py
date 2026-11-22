"""Keeping traPYze light: what takes room, and an automatic tidy-up of old results and run logs.

A run leaves two things behind: its results (outputs/<tool>/<date>) and a record with a log
(.trapyze/runs/<run>). Old ones go to the bin, where they stay 30 days and can be put back.
Data (data/) is yours: it is measured and shown, never tidied.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from .bin import Bin
from .home import Home

DEFAULTS: dict[str, Any] = {"auto": True, "days": 30, "keep_last": 5, "per_tool": {}, "pins": [], "last_tidy": None, "last_freed": 0}
TIDY_EVERY = 20 * 3600


def _path(home: Home) -> Path:
    return home.internal / "storage.json"


def read(home: Home) -> dict[str, Any]:
    try:
        data = json.loads(_path(home).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    out = {**DEFAULTS, **{k: v for k, v in data.items() if k in DEFAULTS}}
    out["per_tool"] = dict(out.get("per_tool") or {})
    out["pins"] = list(out.get("pins") or [])
    return out


def write(home: Home, settings: dict[str, Any]) -> None:
    _path(home).parent.mkdir(parents=True, exist_ok=True)
    _path(home).write_text(json.dumps({k: settings[k] for k in DEFAULTS}, indent=1), encoding="utf-8")


def change(home: Home, body: dict[str, Any]) -> dict[str, Any]:
    s = read(home)
    if "auto" in body:
        s["auto"] = bool(body["auto"])
    for key, low, high in (("days", 1, 3650), ("keep_last", 1, 500)):
        if key in body:
            try:
                value = int(body[key])
            except (TypeError, ValueError):
                raise ValueError("Use whole numbers.") from None
            if not low <= value <= high:
                raise ValueError(f"{key.replace('_', ' ').capitalize()}: a number from {low} to {high}.")
            s[key] = value
    if "tool" in body:
        tool, days = str(body["tool"]), body.get("tool_days")
        if days in (None, ""):
            s["per_tool"].pop(tool, None)
        else:
            if not 1 <= int(days) <= 3650:
                raise ValueError("Days: a number from 1 to 3650.")
            s["per_tool"][tool] = int(days)
    if "pin" in body:
        run_id = str(body["pin"])
        pins = set(s["pins"])
        (pins.add if body.get("pinned") else pins.discard)(run_id)
        s["pins"] = sorted(pins)
    write(home, s)
    return s


# Measuring -----------------------------------------------------------------------
def dir_size(path: Path) -> int:
    total = 0
    stack = [path]
    while stack:
        try:
            with os.scandir(stack.pop()) as it:
                for e in it:
                    try:
                        if e.is_dir(follow_symlinks=False):
                            stack.append(Path(e.path))
                        elif e.is_file(follow_symlinks=False):
                            total += e.stat(follow_symlinks=False).st_size
                    except OSError:
                        continue
        except OSError:
            continue
    return total


def runs(home: Home) -> list[dict[str, Any]]:
    """Every finished run with the folders it owns, oldest first."""
    out = []
    if not home.runs.is_dir():
        return out
    for folder in sorted(home.runs.iterdir()):
        try:
            rec = json.loads((folder / "record.json").read_text(encoding="utf-8"))
            started = datetime.fromisoformat(rec["started"])
        except (OSError, ValueError, KeyError):
            continue
        out.append({"run_id": folder.name, "tool_id": rec.get("tool_id", ""), "tool_name": rec.get("tool_name", ""),
                    "status": rec.get("status", ""), "started": started, "run_dir": folder,
                    "output_dir": Path(rec["output_dir"]) if rec.get("output_dir") else None})
    return out


def candidates(home: Home, settings: dict[str, Any] | None = None, now: float | None = None) -> list[dict[str, Any]]:
    """Runs old enough to put away: older than the days, not among the newest few of their tool, not pinned, not running."""
    s = settings or read(home)
    now = now or time.time()
    by_tool: dict[str, list[dict[str, Any]]] = {}
    for r in runs(home):
        by_tool.setdefault(r["tool_id"], []).append(r)
    pins = set(s["pins"])
    out = []
    for tool_id, items in by_tool.items():
        days = int(s["per_tool"].get(tool_id, s["days"]))
        for r in items[: max(len(items) - int(s["keep_last"]), 0)]:  # all but the newest keep_last
            if r["status"] == "running" or r["run_id"] in pins:
                continue
            if now - r["started"].timestamp() >= days * 86400:
                out.append(r)
    return out


def scan(home: Home, bin_: Bin, engine: str | None = None) -> dict[str, Any]:
    """Sizes of everything, per area and per tool. Can take a while on a big data folder."""
    s = read(home)
    cand = {c["run_id"] for c in candidates(home, s)}
    per_tool: dict[str, dict[str, Any]] = {}
    for r in runs(home):
        t = per_tool.setdefault(r["tool_id"], {"id": r["tool_id"], "name": r["tool_name"] or r["tool_id"], "runs": [], "bytes": 0})
        size = (dir_size(r["output_dir"]) if r["output_dir"] and r["output_dir"].exists() else 0) + dir_size(r["run_dir"])
        t["bytes"] += size
        t["runs"].append({"id": r["run_id"], "when": r["started"].isoformat(timespec="minutes"), "bytes": size, "status": r["status"],
                          "pinned": r["run_id"] in s["pins"], "old": r["run_id"] in cand})
    for t in per_tool.values():
        t["runs"].sort(key=lambda x: x["when"], reverse=True)
        t["days"] = s["per_tool"].get(t["id"])
        t["last"] = t["runs"][0]["when"] if t["runs"] else None
    data = []
    if home.data.is_dir():
        for e in sorted(home.data.iterdir()):
            data.append({"name": e.name, "bytes": dir_size(e) if e.is_dir() else e.stat().st_size, "dir": e.is_dir()})
    data.sort(key=lambda x: -x["bytes"])
    areas = {"results": dir_size(home.outputs), "logs": dir_size(home.runs), "bin": bin_.size(),
             "history": dir_size(home.internal / "lock-history") + dir_size(home.internal / "versions"),
             "data": sum(d["bytes"] for d in data)}
    cache = uv_cache(engine)
    return {"at": time.time(), "areas": areas, "tools": sorted(per_tool.values(), key=lambda t: -t["bytes"]), "data": data[:12],
            "uv_cache": {"path": str(cache), "bytes": dir_size(cache)} if cache else None,
            "tidy": {"runs": len(cand), "bytes": sum((dir_size(c["output_dir"]) if c["output_dir"] and c["output_dir"].exists() else 0)
                                                     + dir_size(c["run_dir"]) for c in [x for x in runs(home) if x["run_id"] in cand])}}


def uv_cache(engine: str | None) -> Path | None:
    if not engine:
        return None
    try:
        done = subprocess.run([engine, "cache", "dir"], capture_output=True, text=True, timeout=30,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        text = (done.stdout or "").strip()
        return Path(text) if done.returncode == 0 and text else None
    except (OSError, subprocess.TimeoutExpired):
        return None


# Doing it ------------------------------------------------------------------------
def remove_runs(home: Home, bin_: Bin, run_ids: list[str], busy: set[str] | None = None) -> list[str]:
    """Put chosen runs (results and log) in the bin, for when the person decides they are not wanted. Returns the bin ids."""
    wanted, busy = set(run_ids), busy or set()
    ids = []
    for r in runs(home):
        if r["run_id"] not in wanted or r["status"] == "running" or r["run_id"] in busy:
            continue
        paths = [p for p in (r["output_dir"], r["run_dir"]) if p and p.exists()]
        label = f"{r['tool_name'] or r['tool_id']}, run of {r['started']:%Y-%m-%d %H:%M}"
        ids.append(bin_.put_paths(label, "results", paths, r["run_id"][:40]))
        try:
            if r["output_dir"]:
                r["output_dir"].parent.rmdir()
        except OSError:
            pass
    s = read(home)
    if wanted & set(s["pins"]):
        s["pins"] = [x for x in s["pins"] if x not in wanted]
        write(home, s)
    return ids


def tidy(home: Home, bin_: Bin, settings: dict[str, Any] | None = None) -> dict[str, Any]:
    """Put old results and logs in the bin, one item per run. Returns what moved."""
    s = settings or read(home)
    moved, freed = 0, 0
    for r in candidates(home, s):
        paths = [p for p in (r["output_dir"], r["run_dir"]) if p and p.exists()]
        size = sum(dir_size(p) for p in paths)
        label = f"{r['tool_name'] or r['tool_id']}, run of {r['started']:%Y-%m-%d %H:%M}"
        bin_.put_paths(label, "results", paths, r["run_id"][:40])
        moved += 1
        freed += size
        try:  # an empty tool folder under outputs/ goes too
            if r["output_dir"]:
                r["output_dir"].parent.rmdir()
        except OSError:
            pass
    s["last_tidy"], s["last_freed"] = time.time(), freed
    write(home, s)
    return {"moved": moved, "bytes": freed}


def due(home: Home) -> bool:
    s = read(home)
    return bool(s["auto"]) and time.time() - (s.get("last_tidy") or 0) > TIDY_EVERY

"""Is the shared data a tool reads recent enough? And other checks before a run.

Ages are written like "30m", "12h", "2d", "1w" or "1td". "td" means trading
days: weekends don't count, so Friday's prices are still fresh on Monday
morning with "1td". (Market holidays aren't known; a holiday may make data
look one day old.)
"""

from __future__ import annotations

import datetime as dt
import re
import shutil
import time
from pathlib import Path
from typing import Any

from .label import Tool, expand

_AGE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(m|min|h|d|w|td)\s*$", re.I)
_UNITS = {"m": 60, "min": 60, "h": 3600, "d": 86400, "w": 7 * 86400}
LOW_DISK_BYTES = 1024**3


def parse_age(text: str) -> tuple[float, str]:
    m = _AGE.match(text or "")
    if not m:
        raise ValueError(f"'{text}' isn't an age traPYze knows. Use for example 30m, 12h, 2d, 1w or 1td (trading days).")
    return float(m.group(1)), m.group(2).lower()


def weekdays_between(earlier: dt.date, later: dt.date) -> int:
    """Weekdays strictly after `earlier` and strictly before `later`."""
    count, day = 0, earlier + dt.timedelta(days=1)
    while day < later:
        if day.weekday() < 5:
            count += 1
        day += dt.timedelta(days=1)
    return count


def too_old(modified: float, age: str, now: float | None = None) -> bool:
    amount, unit = parse_age(age)
    now = time.time() if now is None else now
    if unit == "td":
        missed = weekdays_between(dt.date.fromtimestamp(modified), dt.date.fromtimestamp(now))
        return missed >= amount
    return now - modified > amount * _UNITS[unit]


def ago_words(seconds: float) -> str:
    if seconds < 90:
        return "just now"
    minutes = seconds / 60
    if minutes < 90:
        return f"{minutes:.0f} minutes ago"
    hours = minutes / 60
    if hours < 36:
        return f"{hours:.0f} hours ago"
    return f"{hours / 24:.0f} days ago"


def _norm(home, raw: str) -> Path:
    places = {"data": str(home.data), "home": str(home.root), "lib": str(home.lib), "output": str(home.outputs)}
    text = expand(raw, places) if "{" in raw else raw
    path = Path(text)
    return (path if path.is_absolute() else home.root / path).resolve()


def checks(home, tool: Tool, tools: list[Tool], engine_found: bool, disk_free: int | None = None) -> list[dict[str, Any]]:
    """Plain notices to show before a run. Each has level ("warn" or "info"), text and maybe an action."""
    notices: list[dict[str, Any]] = []
    writers: dict[Path, Tool] = {}
    for other in tools:
        for w in other.writes:
            writers.setdefault(_norm(home, w), other)
    now = time.time()
    for raw, age in tool.reads.items():
        path = _norm(home, raw)
        writer = writers.get(path)
        action = {"kind": "update", "tool": writer.id, "name": writer.name} if writer and writer.id != tool.id else None
        if not path.exists():
            notices.append({"level": "warn", "code": "missing", "file": path.name, "action": action,
                            "text": f"{path.name} doesn't exist yet" + (f". {writer.name} makes it." if action else ".")})
            continue
        modified = path.stat().st_mtime
        if age and too_old(modified, age, now):
            notices.append({"level": "warn", "code": "old", "file": path.name, "action": action, "modified": modified,
                            "text": f"{path.name} was last updated {ago_words(now - modified)}"
                                    + (f", by {writer.name}." if writer else ".")})
    if tool.dependencies and not engine_found:
        notices.append({"level": "warn", "code": "engine",
                        "text": "This tool needs extra packages, and uv (the engine that installs them) isn't installed."})
    if disk_free is not None and disk_free < LOW_DISK_BYTES:
        notices.append({"level": "warn", "code": "disk",
                        "text": f"Only {disk_free / 1024**2:.0f} MB of disk space is left for results."})
    return notices


def disk_free(path: Path) -> int | None:
    try:
        return shutil.disk_usage(path).free
    except OSError:
        return None

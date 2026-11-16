"""Ready-made tools that come with traPYze, in packs you add with one click.

Every tool here works without the internet and uses only what comes with Python, so
there is nothing to install and nothing outside traPYze that can change under it.
A pack is copied into the scripts folder as a program; from then on its tools are
ordinary scripts you can read, change or remove.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from .home import PROGRAM_FILE
from .label import LabelError, read_tool

ROOT = Path(__file__).parent / "resources" / "packs"
PACKS: list[dict[str, Any]] = [
    {"id": "everyday_files", "name": "Everyday files", "icon": "archive",
     "description": "Tidy a folder, find duplicates and set them aside, make and restore backups, rename files and see what "
                    "takes the space. "
                    "The tools that change files show a list first and never delete or overwrite anything of yours."},
    {"id": "home_finance", "name": "Home finance", "icon": "coin",
     "description": "Turn the CSV export from your bank into a monthly overview by category, and find the "
                    "subscriptions you pay for. Your statement never leaves your computer."},
    {"id": "tables_and_data", "name": "Tables and data", "icon": "table",
     "description": "Check a downloaded CSV file, merge several into one, put a CSV into a database, and get a "
                    "database table back out for Excel."},
]


# Which shelf each pack tool belongs on (traPYze's own guess can't know these as well as their maker).
SHELVES = {
    "everyday_files": {"find_duplicates": "analyse", "biggest_files": "analyse"},
    "home_finance": {"bank_overview": "analyse", "find_subscriptions": "analyse"},
    "tables_and_data": {"check_download": "analyse", "merge_csv": "collect", "csv_to_database": "collect",
                        "export_table": "share"},
}


def shelf_for(group: str | None, stem: str) -> str | None:
    return SHELVES.get(group or "", {}).get(stem)


class PackProblem(Exception):
    """A plain-English problem with adding a pack."""


def _files(pack_id: str) -> list[Path]:
    return sorted(p for p in (ROOT / pack_id).glob("*.py"))


def overview(scripts: Path) -> list[dict[str, Any]]:
    """Every pack with its tools and whether it's in the scripts folder already."""
    out = []
    for pack in PACKS:
        tools, present = [], 0
        for path in _files(pack["id"]):
            there = (scripts / pack["id"] / path.name).exists()
            present += there
            if "# [tool.trapyze]" not in path.read_text(encoding="utf-8"):
                continue  # a helper module, not a tool
            try:
                tool = read_tool(path)
            except LabelError:
                continue
            tools.append({"name": tool.name, "description": tool.description, "icon": tool.icon, "color": tool.color})
        total = len(_files(pack["id"]))
        out.append({**pack, "tools": tools, "installed": present == total, "partly": 0 < present < total})
    return out


def install(scripts: Path, pack_id: str) -> list[str]:
    """Copy a pack's files that aren't there yet; files you already have (and may have changed) are left alone."""
    pack = next((p for p in PACKS if p["id"] == pack_id), None)
    if pack is None:
        raise PackProblem("That pack doesn't exist.")
    folder = scripts / pack_id
    folder.mkdir(parents=True, exist_ok=True)
    added = []
    for path in _files(pack_id):
        target = folder / path.name
        if not target.exists():
            shutil.copyfile(path, target)
            added.append(path.name)
    info = folder / PROGRAM_FILE
    if not info.exists():
        info.write_text(json.dumps({"name": pack["name"], "description": pack["description"], "hidden": []}, indent=1),
                        encoding="utf-8")
    return added

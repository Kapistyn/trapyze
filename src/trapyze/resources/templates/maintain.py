# /// script
# requires-python = ">=3.11"
# dependencies = []
#
# [tool.trapyze]
# name = "{name}"
# description = "{description}"
# icon = "archive"
# color = "slate"
# version = "0.1.0"
#
# [[tool.trapyze.settings]]
# key = "folder"
# label = "Folder inside traPYze"
# type = "choice"
# options = ["outputs", "data"]
# default = "outputs"
#
# [[tool.trapyze.settings]]
# key = "days"
# label = "Older than (days)"
# type = "int"
# default = 90
# min = 1
#
# [[tool.trapyze.settings]]
# key = "really_delete"
# label = "Really delete them"
# type = "bool"
# default = false
# help = "Off: only list what would be deleted."
# ///
"""{name}: clears out old files in one of traPYze's own folders.

A starting point made by traPYze. It only ever looks inside the traPYze home
folder, and by default only lists what it would delete.
"""

import os
import time
from pathlib import Path

import trapyze_helper as tz

s = tz.settings()
home = Path(os.environ.get("TRAPYZE_HOME", "."))
folder = (home / s.get("folder", "outputs")).resolve()
if home.resolve() not in folder.parents:
    raise SystemExit("Only folders inside traPYze can be cleaned.")
cutoff = time.time() - int(s.get("days", 90)) * 86400
really = str(s.get("really_delete", False)).lower() in ("true", "1", "yes")

old = [p for p in folder.rglob("*") if p.is_file() and p.stat().st_mtime < cutoff] if folder.exists() else []
size = sum(p.stat().st_size for p in old)
for i, p in enumerate(old):
    tz.progress(i / max(len(old), 1), p.name)
    if really:
        p.unlink()
    else:
        print("Would delete:", p.relative_to(home))
tz.progress(1, "Done")
print(f"{'Deleted' if really else 'Found'} {len(old)} files, {size // 1024} KB, older than {s.get('days', 90)} days.")

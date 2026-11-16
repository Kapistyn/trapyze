# /// script
# requires-python = ">=3.11"
# dependencies = []
#
# [tool.trapyze]
# name = "Set duplicates aside"
# description = "Keeps one of each set of identical files and moves the extra copies to a folder you can check."
# icon = "archive"
# color = "purple"
# version = "1.0.0"
#
# [[tool.trapyze.settings]]
# key = "folder"
# label = "Folder to look in"
# type = "folder"
# required = true
# help = "Subfolders are included."
#
# [[tool.trapyze.settings]]
# key = "min_kb"
# label = "Skip files smaller than (KB)"
# type = "int"
# default = 10
# min = 0
#
# [[tool.trapyze.settings]]
# key = "really_move"
# label = "Really move the extra copies"
# type = "bool"
# default = false
# help = "Off: only make a list of what would move, so you can check first."
# ///
"""Set duplicates aside: nothing is deleted. The extra copies go to 'Duplicates set aside' inside the
folder, in the same subfolders they came from, so putting one back is a matter of dragging it."""

import csv
import hashlib
from collections import defaultdict
from pathlib import Path

import trapyze_helper as tz

ASIDE = "Duplicates set aside"

s = tz.settings()
folder = Path(s["folder"])
if not folder.is_dir():
    raise SystemExit(f"The folder {folder} doesn't exist.")
smallest = int(s.get("min_kb", 10)) * 1024
really = bool(s.get("really_move"))

tz.step("Listing files")
by_size = defaultdict(list)
for p in folder.rglob("*"):
    try:
        if p.is_file() and not p.is_symlink() and ASIDE not in p.relative_to(folder).parts and p.stat().st_size >= smallest:
            by_size[p.stat().st_size].append(p)
    except OSError:
        pass

candidates = [p for group in by_size.values() if len(group) > 1 for p in group]
by_content = defaultdict(list)
for i, p in enumerate(candidates):
    tz.progress(i / max(len(candidates), 1) * 0.9, f"Comparing {p.name}")
    digest = hashlib.sha256()
    try:
        with p.open("rb") as f:
            while chunk := f.read(1024 * 1024):
                digest.update(chunk)
    except OSError:
        continue
    by_content[(p.stat().st_size, digest.hexdigest())].append(p)

moved = freed = 0
with tz.output_path("set-aside-list.csv").open("w", newline="", encoding="utf-8") as f:
    out = csv.writer(f)
    out.writerow(["kept", "extra copy", "done"])
    for group in by_content.values():
        if len(group) < 2:
            continue
        # Keep the copy closest to the top of the folder; with a tie, the first by name.
        group.sort(key=lambda p: (len(p.relative_to(folder).parts), str(p).lower()))
        keep = group[0]
        for extra in group[1:]:
            rel = extra.relative_to(folder)
            target = folder / ASIDE / rel
            n = 2
            while target.exists():  # never overwrite
                target = folder / ASIDE / rel.with_name(f"{rel.stem} ({n}){rel.suffix}")
                n += 1
            size = extra.stat().st_size
            if really:
                target.parent.mkdir(parents=True, exist_ok=True)
                extra.rename(target)
            moved += 1
            freed += size
            out.writerow([str(keep.relative_to(folder)), str(rel), "moved" if really else "not yet"])

tz.progress(1, "Done")
mb = freed / 1024 / 1024
if really:
    print(f"Moved {moved} extra copies ({mb:.1f} MB) to '{ASIDE}' in {folder.name}. Nothing was deleted.")
    print("Look through that folder; delete it yourself when you're sure.")
else:
    print(f"{moved} extra copies ({mb:.1f} MB) would move. Check set-aside-list.csv, then switch on 'Really move the extra copies'.")

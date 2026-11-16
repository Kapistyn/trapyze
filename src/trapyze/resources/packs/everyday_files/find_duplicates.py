# /// script
# requires-python = ">=3.11"
# dependencies = []
#
# [tool.trapyze]
# name = "Find duplicate files"
# description = "Lists files that are exactly the same, and how much space the copies take."
# icon = "document"
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
# ///
"""Find duplicate files: compares the contents, not the names. It only makes a list; you decide what to remove."""

import csv
import hashlib
from collections import defaultdict
from pathlib import Path

import trapyze_helper as tz

s = tz.settings()
folder = Path(s["folder"])
if not folder.is_dir():
    raise SystemExit(f"The folder {folder} doesn't exist.")
smallest = int(s.get("min_kb", 10)) * 1024

tz.step("Listing files")
by_size = defaultdict(list)
for p in folder.rglob("*"):
    try:
        if p.is_file() and not p.is_symlink() and p.stat().st_size >= smallest:
            by_size[p.stat().st_size].append(p)
    except OSError:
        pass  # a file that can't be read is skipped

candidates = [p for group in by_size.values() if len(group) > 1 for p in group]
by_content = defaultdict(list)
for i, p in enumerate(candidates):
    tz.progress(i / max(len(candidates), 1), f"Comparing {p.name}")
    digest = hashlib.sha256()
    try:
        with p.open("rb") as f:
            while chunk := f.read(1024 * 1024):
                digest.update(chunk)
    except OSError:
        continue
    by_content[(p.stat().st_size, digest.hexdigest())].append(p)

groups = sorted((g for g in by_content.values() if len(g) > 1), key=lambda g: -g[0].stat().st_size * (len(g) - 1))
wasted = 0
with tz.output_path("duplicates.csv").open("w", newline="", encoding="utf-8") as f:
    out = csv.writer(f)
    out.writerow(["group", "size (KB)", "file"])
    for n, group in enumerate(groups, 1):
        size = group[0].stat().st_size
        wasted += size * (len(group) - 1)
        for p in sorted(group):
            out.writerow([n, round(size / 1024), str(p.relative_to(folder))])

tz.progress(1, "Done")
print(f"Found {len(groups)} sets of identical files; the extra copies take {wasted / 1024 / 1024:.1f} MB.")
print("Nothing was removed. The list is in duplicates.csv.")

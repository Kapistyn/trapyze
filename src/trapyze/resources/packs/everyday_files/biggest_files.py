# /// script
# requires-python = ">=3.11"
# dependencies = []
#
# [tool.trapyze]
# name = "What takes the space?"
# description = "Shows the biggest files and subfolders in a folder."
# icon = "gauge"
# color = "blue"
# version = "1.0.0"
#
# [[tool.trapyze.settings]]
# key = "folder"
# label = "Folder to look in"
# type = "folder"
# required = true
#
# [[tool.trapyze.settings]]
# key = "top"
# label = "How many to list"
# type = "int"
# default = 25
# min = 5
# max = 500
# ///
"""What takes the space: only reads sizes; nothing is changed."""

import csv
from collections import Counter
from pathlib import Path

import trapyze_helper as tz

s = tz.settings()
folder = Path(s["folder"])
if not folder.is_dir():
    raise SystemExit(f"The folder {folder} doesn't exist.")
top = int(s.get("top", 25))

tz.step("Measuring")
sizes, per_sub, total = [], Counter(), 0
for n, p in enumerate(folder.rglob("*")):
    try:
        if not p.is_file() or p.is_symlink():
            continue
        size = p.stat().st_size
    except OSError:
        continue
    rel = p.relative_to(folder)
    sizes.append((size, str(rel)))
    per_sub[rel.parts[0] if len(rel.parts) > 1 else "(loose files)"] += size
    total += size
    if n % 500 == 0:
        tz.progress(0.5, f"{len(sizes)} files so far")

mb = lambda b: round(b / 1024 / 1024, 1)  # noqa: E731
with tz.output_path("biggest-files.csv").open("w", newline="", encoding="utf-8") as f:
    out = csv.writer(f)
    out.writerow(["size (MB)", "file"])
    out.writerows([mb(size), name] for size, name in sorted(sizes, reverse=True)[:top])
with tz.output_path("biggest-folders.csv").open("w", newline="", encoding="utf-8") as f:
    out = csv.writer(f)
    out.writerow(["size (MB)", "share (%)", "subfolder"])
    out.writerows([mb(size), round(100 * size / total) if total else 0, name] for name, size in per_sub.most_common(top))

tz.progress(1, "Done")
print(f"{len(sizes)} files, {mb(total)} MB in total.")
for name, size in per_sub.most_common(5):
    print(f"  {mb(size):>9} MB  {name}")

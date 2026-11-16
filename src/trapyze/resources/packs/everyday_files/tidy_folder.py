# /// script
# requires-python = ">=3.11"
# dependencies = []
#
# [tool.trapyze]
# name = "Tidy a folder"
# description = "Sorts the loose files in a folder into subfolders, by kind or by month."
# icon = "cube"
# color = "teal"
# version = "1.0.0"
#
# [[tool.trapyze.settings]]
# key = "folder"
# label = "Folder to tidy"
# type = "folder"
# required = true
# help = "For example your Downloads folder. Only loose files are moved; subfolders stay as they are."
#
# [[tool.trapyze.settings]]
# key = "sort_by"
# label = "Sort by"
# type = "choice"
# options = ["Kind of file", "Month"]
# default = "Kind of file"
#
# [[tool.trapyze.settings]]
# key = "really_move"
# label = "Really move the files"
# type = "bool"
# default = false
# help = "Off: only make a list of what would move, so you can check first."
# ///
"""Tidy a folder: sorts loose files into subfolders. Nothing is ever deleted or overwritten."""

import csv
import datetime
from pathlib import Path

import trapyze_helper as tz

KINDS = {
    "Pictures": "jpg jpeg png gif bmp webp heic tif tiff svg raw",
    "Documents": "pdf doc docx odt rtf txt md epub",
    "Spreadsheets": "xls xlsx xlsm ods csv tsv",
    "Presentations": "ppt pptx odp key",
    "Music": "mp3 wav flac m4a ogg aac",
    "Videos": "mp4 mov avi mkv wmv webm m4v",
    "Archives": "zip rar 7z tar gz bz2",
    "Installers": "exe msi dmg pkg deb rpm appimage",
    "Code": "py js ts html css json xml yaml yml sql ipynb",
}
BY_EXT = {ext: kind for kind, exts in KINDS.items() for ext in exts.split()}

s = tz.settings()
folder = Path(s["folder"])
if not folder.is_dir():
    raise SystemExit(f"The folder {folder} doesn't exist.")
by_month = s.get("sort_by") == "Month"
really = bool(s.get("really_move"))

files = sorted(p for p in folder.iterdir() if p.is_file() and not p.name.startswith("."))
plan = []
for p in files:
    if by_month:
        sub = datetime.datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m")
    else:
        sub = BY_EXT.get(p.suffix.lower().lstrip("."), "Other")
    plan.append((p, sub))

moved = 0
with tz.output_path("tidy-list.csv").open("w", newline="", encoding="utf-8") as f:
    out = csv.writer(f)
    out.writerow(["file", "goes to", "done"])
    for i, (p, sub) in enumerate(plan):
        tz.progress(i / max(len(plan), 1), p.name)
        target = folder / sub / p.name
        n = 2
        while target.exists():  # never overwrite: "name (2).ext"
            target = folder / sub / f"{p.stem} ({n}){p.suffix}"
            n += 1
        if really:
            target.parent.mkdir(exist_ok=True)
            p.rename(target)
            moved += 1
        out.writerow([p.name, f"{sub}/{target.name}", "moved" if really else "not yet"])

tz.progress(1, "Done")
if really:
    print(f"Moved {moved} files into subfolders of {folder.name}.")
else:
    print(f"{len(plan)} files would move. Check tidy-list.csv, then switch on 'Really move the files'.")

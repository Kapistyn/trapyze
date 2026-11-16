# /// script
# requires-python = ">=3.11"
# dependencies = []
#
# [tool.trapyze]
# name = "Rename files"
# description = "Gives all files in a folder tidy names: date first, numbered, or lowercase without spaces."
# icon = "document"
# color = "orange"
# version = "1.0.0"
#
# [[tool.trapyze.settings]]
# key = "folder"
# label = "Folder with the files"
# type = "folder"
# required = true
# help = "Only the files directly in this folder."
#
# [[tool.trapyze.settings]]
# key = "style"
# label = "New names"
# type = "choice"
# options = ["Date first (2026-11-16 name)", "Numbered (Name 001)", "Lowercase, no spaces"]
# default = "Date first (2026-11-16 name)"
#
# [[tool.trapyze.settings]]
# key = "base"
# label = "Name for numbered files"
# type = "text"
# default = "File"
# only_for = { style = ["Numbered (Name 001)"] }
#
# [[tool.trapyze.settings]]
# key = "really_rename"
# label = "Really rename the files"
# type = "bool"
# default = false
# help = "Off: only make a list of the new names, so you can check first."
# ///
"""Rename files: the list of old and new names is always saved, so a rename can be traced back."""

import csv
import datetime
import re
from pathlib import Path

import trapyze_helper as tz

s = tz.settings()
folder = Path(s["folder"])
if not folder.is_dir():
    raise SystemExit(f"The folder {folder} doesn't exist.")
style = str(s.get("style", "Date first"))
base = re.sub(r'[\\/:*?"<>|]+', " ", str(s.get("base") or "File")).strip() or "File"
really = bool(s.get("really_rename"))

files = sorted((p for p in folder.iterdir() if p.is_file() and not p.name.startswith(".")), key=lambda p: (p.stat().st_mtime, p.name))
width = max(3, len(str(len(files))))
taken = {p.name.lower() for p in folder.iterdir()}
plan = []
for n, p in enumerate(files, 1):
    if style.startswith("Date"):
        day = datetime.datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d")
        new = p.name if re.match(r"\d{4}-\d{2}-\d{2} ", p.name) else f"{day} {p.name}"
    elif style.startswith("Numbered"):
        new = f"{base} {n:0{width}d}{p.suffix.lower()}"
    else:
        new = re.sub(r"[\s_]+", "-", p.stem.strip().lower()) + p.suffix.lower()
    if new != p.name:
        stem, suffix, k = Path(new).stem, Path(new).suffix, 2
        while new.lower() in taken:  # never overwrite another file
            new, k = f"{stem} ({k}){suffix}", k + 1
        taken.add(new.lower())
    plan.append((p, new))

changed = 0
with tz.output_path("rename-list.csv").open("w", newline="", encoding="utf-8") as f:
    out = csv.writer(f)
    out.writerow(["old name", "new name", "done"])
    for i, (p, new) in enumerate(plan):
        tz.progress(i / max(len(plan), 1), p.name)
        if new == p.name:
            continue
        if really:
            p.rename(p.with_name(new))
        changed += 1
        out.writerow([p.name, new, "renamed" if really else "not yet"])

tz.progress(1, "Done")
if really:
    print(f"Renamed {changed} of {len(plan)} files. The old and new names are in rename-list.csv.")
else:
    print(f"{changed} of {len(plan)} files would get a new name. Check rename-list.csv, then switch on 'Really rename the files'.")

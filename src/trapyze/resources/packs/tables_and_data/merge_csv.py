# /// script
# requires-python = ">=3.11"
# dependencies = []
#
# [tool.trapyze]
# name = "Merge CSV files"
# description = "Joins all CSV files in a folder into one, also when their columns differ."
# icon = "table"
# color = "orange"
# version = "1.0.0"
#
# [[tool.trapyze.settings]]
# key = "folder"
# label = "Folder with the CSV files"
# type = "folder"
# required = true
#
# [[tool.trapyze.settings]]
# key = "add_source"
# label = "Add a column with the file each row came from"
# type = "bool"
# default = true
#
# [[tool.trapyze.settings]]
# key = "drop_doubles"
# label = "Leave out identical rows"
# type = "bool"
# default = false
# ///
"""Merge CSV files: the originals are only read. The result goes to this run's results."""

import csv
from pathlib import Path

import trapyze_helper as tz

s = tz.settings()
folder = Path(s["folder"])
if not folder.is_dir():
    raise SystemExit(f"The folder {folder} doesn't exist.")
files = sorted(p for p in folder.iterdir() if p.suffix.lower() in (".csv", ".tsv", ".txt") and p.is_file())
if not files:
    raise SystemExit(f"There are no CSV files in {folder}.")


def read(path):
    raw = path.read_bytes()
    if raw[:5].lower().startswith((b"<html", b"<!doc")):
        return None, []  # a web page saved by mistake, not data
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines:
        return [], []
    try:
        dialect = csv.Sniffer().sniff("\n".join(lines[:20]), delimiters=";,\t|")
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.reader(lines, dialect))
    return [h.strip() for h in rows[0]], rows[1:]


columns, tables = [], []
for i, p in enumerate(files):
    tz.progress(i / len(files) * 0.6, f"Reading {p.name}")
    header, body = read(p)
    if header is None:
        print(f"WARNING: skipped {p.name}: it's a web page, not data.")
        continue
    tables.append((p.name, header, body))
    columns += [h for h in header if h not in columns]

source = bool(s.get("add_source", True))
seen, written, skipped = set(), 0, 0
with tz.output_path("merged.csv").open("w", newline="", encoding="utf-8") as f:
    out = csv.writer(f)
    out.writerow(columns + (["source file"] if source else []))
    for i, (name, header, body) in enumerate(tables):
        tz.progress(0.6 + i / len(tables) * 0.4, f"Adding {name}")
        for r in body:
            by_name = dict(zip(header, r))
            line = [by_name.get(c, "") for c in columns]
            if s.get("drop_doubles") and tuple(line) in seen:
                skipped += 1
                continue
            seen.add(tuple(line))
            out.writerow(line + ([name] if source else []))
            written += 1

tz.progress(1, "Done")
print(f"Merged {len(tables)} files into merged.csv: {written} rows, {len(columns)} columns." + (f" Left out {skipped} identical rows." if skipped else ""))

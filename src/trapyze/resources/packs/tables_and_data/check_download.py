# /// script
# requires-python = ">=3.11"
# dependencies = []
#
# [tool.trapyze]
# name = "Check a download"
# description = "Checks a CSV file you downloaded: rows, empty cells, doubles, broken lines and the dates it covers."
# icon = "shield"
# color = "blue"
# version = "1.0.0"
#
# [[tool.trapyze.settings]]
# key = "file"
# label = "CSV file to check"
# type = "file"
# required = true
#
# [[tool.trapyze.settings]]
# key = "expect_rows"
# label = "Expect at least this many rows"
# type = "int"
# default = 1
# min = 0
# help = "The check fails when the file has fewer; handy in a chain before other tools use the file."
# ///
"""Check a download: reads the file and reports what's in it. It fails (so a chain stops) when the file is unusable."""

import csv
import datetime
from collections import Counter
from pathlib import Path

import trapyze_helper as tz

DATE_FORMATS = ("%Y-%m-%d", "%Y%m%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y", "%d.%m.%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S")

s = tz.settings()
path = Path(s["file"])
if not path.is_file():
    raise SystemExit(f"The file {path} doesn't exist.")
raw = path.read_bytes()
if not raw.strip():
    raise SystemExit(f"{path.name} is empty.")
if raw[:5].lower().startswith((b"<html", b"<!doc")):
    raise SystemExit(f"{path.name} is a web page, not data. The download probably needs you to log in first.")
for encoding in ("utf-8-sig", "cp1252", "latin-1"):
    try:
        text = raw.decode(encoding)
        break
    except UnicodeDecodeError:
        continue
lines = [l for l in text.splitlines() if l.strip()]
try:
    dialect = csv.Sniffer().sniff("\n".join(lines[:20]), delimiters=";,\t|")
except csv.Error:
    dialect = csv.excel
rows = list(csv.reader(lines, dialect))
header, body = rows[0], rows[1:]

tz.step("Checking the rows")
wrong = [i + 2 for i, r in enumerate(body) if len(r) != len(header)]
doubles = sum(n - 1 for n in Counter(tuple(r) for r in body).values() if n > 1)
empty = Counter()
for r in body:
    for name, value in zip(header, r):
        if not value.strip():
            empty[name] += 1


def parse_day(value):
    for fmt in DATE_FORMATS:
        try:
            return datetime.datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    return None


span = ""
for col, name in enumerate(header):
    days = [d for d in (parse_day(r[col]) for r in body[:5000] if col < len(r)) if d]
    if body and len(days) >= 0.9 * min(len(body), 5000):
        span = f"{min(days)} to {max(days)} (column '{name}')"
        break

report = [f"File: {path.name} ({len(raw) / 1024:.0f} KB, read as {encoding})",
          f"Columns ({len(header)}): {', '.join(header)}",
          f"Rows: {len(body)}",
          f"Dates: {span or 'no date column found'}",
          f"Identical rows: {doubles}",
          f"Rows with a different number of columns: {len(wrong)}" + (f" (lines {', '.join(map(str, wrong[:10]))})" if wrong else ""),
          "Empty cells: " + (", ".join(f"{name} {n}" for name, n in empty.most_common()) or "none")]
tz.output_path("check.txt").write_text("\n".join(report) + "\n", encoding="utf-8")
print("\n".join(report))
tz.progress(1, "Done")

if len(body) < int(s.get("expect_rows", 1)):
    raise SystemExit(f"Only {len(body)} rows, where at least {s.get('expect_rows')} were expected.")
if len(wrong) > len(body) / 2:
    raise SystemExit("More than half of the lines have the wrong number of columns; this file looks damaged.")

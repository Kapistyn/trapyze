# /// script
# requires-python = ">=3.11"
# dependencies = []
#
# [tool.trapyze]
# name = "{name}"
# description = "{description}"
# icon = "chart"
# color = "purple"
# version = "0.1.0"
#
# [[tool.trapyze.settings]]
# key = "file_name"
# label = "Data file to read"
# type = "text"
# default = "downloaded.csv"
# help = "A CSV file in the shared data folder."
#
# [[tool.trapyze.settings]]
# key = "top"
# label = "How many rows in the result"
# type = "int"
# default = 10
# min = 1
# max = 1000
# ///
"""{name}: reads a CSV from the shared data folder and writes a summary.

A starting point made by traPYze: for every column with numbers it works out
the count, average, lowest and highest value. Change the calculation as you like.
"""

import csv
import statistics

import trapyze_helper as tz

s = tz.settings()
source = tz.data_path(s.get("file_name") or "downloaded.csv")
if not source.exists():
    raise SystemExit(f"{source.name} isn't in the shared data folder yet. Run a Collect tool first.")

tz.step(f"Reading {source.name}")
with source.open(newline="", encoding="utf-8-sig") as f:
    rows = list(csv.DictReader(f))

summary = []
columns = list(rows[0].keys()) if rows else []
for i, column in enumerate(columns):
    tz.progress(i / max(len(columns), 1), f"Column {column}")
    numbers = []
    for row in rows:
        try:
            numbers.append(float(str(row[column]).replace(",", ".")))
        except (TypeError, ValueError):
            pass
    if numbers:
        summary.append({"column": column, "count": len(numbers), "average": round(statistics.fmean(numbers), 4),
                        "lowest": min(numbers), "highest": max(numbers)})

summary.sort(key=lambda r: r["count"], reverse=True)
out = tz.output_path("summary.csv")
with out.open("w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=["column", "count", "average", "lowest", "highest"])
    writer.writeheader()
    writer.writerows(summary[: int(s.get("top", 10))])
tz.progress(1, "Done")
print(f"Read {len(rows)} rows; summary of {len(summary)} number columns in {out.name}")

# /// script
# requires-python = ">=3.11"
# dependencies = []
#
# [tool.trapyze]
# name = "CSV into a database"
# description = "Puts a CSV file into a table of a database in the shared data folder, for other tools to use."
# icon = "database"
# color = "teal"
# version = "1.0.0"
#
# [[tool.trapyze.settings]]
# key = "file"
# label = "CSV file"
# type = "file"
# required = true
#
# [[tool.trapyze.settings]]
# key = "database"
# label = "Database name"
# type = "text"
# default = "my-data"
# help = "Kept in traPYze's shared data folder as <name>.sqlite."
#
# [[tool.trapyze.settings]]
# key = "table"
# label = "Table name"
# type = "text"
# default = ""
# help = "Empty: the name of the CSV file."
#
# [[tool.trapyze.settings]]
# key = "mode"
# label = "If the table is already there"
# type = "choice"
# options = ["Replace it", "Add the rows to it"]
# default = "Replace it"
# ///
"""CSV into a database: makes or updates one table in a SQLite database. Numbers are stored as numbers."""

import csv
import re
import sqlite3
from pathlib import Path

import trapyze_helper as tz

s = tz.settings()
path = Path(s["file"])
if not path.is_file():
    raise SystemExit(f"The file {path} doesn't exist.")
clean = lambda v, fallback: re.sub(r"\W+", "_", str(v or "").strip()).strip("_") or fallback  # noqa: E731
db = tz.data_path(clean(s.get("database"), "my-data").replace("_", "-") + ".sqlite")
table = clean(s.get("table") or path.stem, "data")

raw = path.read_bytes()
for encoding in ("utf-8-sig", "cp1252", "latin-1"):
    try:
        text = raw.decode(encoding)
        break
    except UnicodeDecodeError:
        continue
lines = [l for l in text.splitlines() if l.strip()]
if len(lines) < 2:
    raise SystemExit(f"{path.name} has no rows.")
try:
    dialect = csv.Sniffer().sniff("\n".join(lines[:20]), delimiters=";,\t|")
except csv.Error:
    dialect = csv.excel
rows = list(csv.reader(lines, dialect))
names, used = [], set()
for i, h in enumerate(rows[0]):
    name = clean(h, f"column_{i + 1}")
    while name.lower() in used:
        name += "_2"
    used.add(name.lower())
    names.append(name)
body = [r + [""] * (len(names) - len(r)) for r in rows[1:]]


def number(v):
    v = v.strip()
    if re.fullmatch(r"-?\d+", v) and not (len(v) > 1 and v.lstrip("-").startswith("0")):
        return int(v)
    if re.fullmatch(r"-?\d*\.\d+(e-?\d+)?|-?\d+\.\d*", v, re.I):
        return float(v)
    return None


kinds = []
for col in range(len(names)):
    filled = [r[col] for r in body if r[col].strip()]
    values = [number(v) for v in filled]
    kinds.append("TEXT" if not filled or None in values else "INTEGER" if all(isinstance(v, int) for v in values) else "REAL")

tz.step(f"Writing table {table}")
con = sqlite3.connect(db)
try:
    with con:
        if s.get("mode", "Replace it").startswith("Replace"):
            con.execute(f'DROP TABLE IF EXISTS "{table}"')
        con.execute(f'CREATE TABLE IF NOT EXISTS "{table}" (' + ", ".join(f'"{n}" {k}' for n, k in zip(names, kinds)) + ")")
        have = [r[1] for r in con.execute(f'PRAGMA table_info("{table}")')]
        if [h.lower() for h in have] != [n.lower() for n in names]:
            raise SystemExit(f"The table {table} has other columns ({', '.join(have)}). Choose 'Replace it' or another table name.")
        marks = ", ".join("?" * len(names))
        for start in range(0, len(body), 5000):
            tz.progress(start / len(body), f"{start} of {len(body)} rows")
            chunk = [[(number(v) if k != "TEXT" and v.strip() else (v if v.strip() else None)) for v, k in zip(r[: len(names)], kinds)]
                     for r in body[start:start + 5000]]
            con.executemany(f'INSERT INTO "{table}" VALUES ({marks})', chunk)
    total = con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
finally:
    con.close()

tz.progress(1, "Done")
print(f"Put {len(body)} rows into table {table} of {db.name}; it now has {total} rows.")
print("Columns: " + ", ".join(f"{n} ({k.lower()})" for n, k in zip(names, kinds)))

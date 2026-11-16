# /// script
# requires-python = ">=3.11"
# dependencies = []
#
# [tool.trapyze]
# name = "Database table to CSV"
# description = "Lists the tables in a database, or saves one as a CSV file to open in Excel."
# icon = "table"
# color = "slate"
# version = "1.0.0"
#
# [[tool.trapyze.settings]]
# key = "database"
# label = "Database file"
# type = "file"
# required = true
# help = "A .sqlite or .db file, for example from traPYze's shared data folder."
#
# [[tool.trapyze.settings]]
# key = "table"
# label = "Table"
# type = "text"
# default = ""
# help = "Empty: only list the tables and how many rows each has."
#
# [[tool.trapyze.settings]]
# key = "for_excel"
# label = "Make it open neatly in Excel"
# type = "bool"
# default = true
# help = "Uses semicolons and a marker Excel needs for accents."
# ///
"""Database table to CSV: opens the database read-only, so nothing in it can change."""

import csv
import sqlite3
from pathlib import Path

import trapyze_helper as tz

s = tz.settings()
path = Path(s["database"])
if not path.is_file():
    raise SystemExit(f"The file {path} doesn't exist.")
try:
    con = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%' ORDER BY name")]
except sqlite3.DatabaseError:
    raise SystemExit(f"{path.name} isn't a SQLite database.") from None

wanted = str(s.get("table") or "").strip()
try:
    if not wanted:
        print(f"Tables in {path.name}:")
        for t in tables:
            count = con.execute('SELECT COUNT(*) FROM "' + t + '"').fetchone()[0]
            print(f"  {t}: {count} rows")
        print("Fill in a table name to save it as CSV.")
    else:
        table = next((t for t in tables if t.lower() == wanted.lower()), None)
        if table is None:
            raise SystemExit(f"There's no table '{wanted}'. The tables are: {', '.join(tables) or 'none'}.")
        excel = bool(s.get("for_excel", True))
        cur = con.execute(f'SELECT * FROM "{table}"')
        n = 0
        with tz.output_path(f"{table}.csv").open("w", newline="", encoding="utf-8-sig" if excel else "utf-8") as f:
            out = csv.writer(f, delimiter=";" if excel else ",")
            out.writerow([c[0] for c in cur.description])
            while rows := cur.fetchmany(5000):
                out.writerows(rows)
                n += len(rows)
                tz.step(f"{n} rows")
        print(f"Saved {n} rows of {table} to {table}.csv.")
finally:
    con.close()
tz.progress(1, "Done")

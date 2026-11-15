# /// script
# requires-python = ">=3.11"
# dependencies = []
#
# [tool.trapyze]
# name = "Price report"
# description = "Reads the shared price data and writes a summary table per share."
# icon = "table"
# color = "orange"
# version = "1.0.0"
#
# [[tool.trapyze.settings]]
# key = "lookback"
# label = "Days to look back"
# type = "int"
# default = 20
# min = 5
# max = 500
#
# [[tool.trapyze.settings]]
# key = "sort_by"
# label = "Sort the table by"
# type = "choice"
# options = ["change", "symbol"]
# default = "change"
# ///
"""Reads the shared database that 'Demo price data' fills, and writes a CSV.

Shows a tool reading shared data instead of keeping its own copy.
"""

import csv
import sqlite3
import sys

import trapyze_helper as tz

s = tz.settings()
lookback = int(s.get("lookback", 20))
sort_by = s.get("sort_by", "change")

db = tz.data_path("demo_prices.sqlite")
if not db.exists():
    print("There's no price data yet. Run 'Demo price data' first.")
    sys.exit(2)

tz.step("Reading the shared price data")
con = sqlite3.connect(db)
symbols = [r[0] for r in con.execute("SELECT DISTINCT symbol FROM prices ORDER BY symbol")]

rows = []
for n, symbol in enumerate(symbols):
    tz.progress(n / max(1, len(symbols)), f"Summarising {symbol}")
    closes = [
        r[0]
        for r in con.execute(
            "SELECT close FROM prices WHERE symbol = ? ORDER BY day DESC LIMIT ?", (symbol, lookback + 1)
        )
    ][::-1]
    if len(closes) < 2:
        continue
    change = (closes[-1] / closes[0] - 1) * 100
    rows.append({"symbol": symbol, "last": closes[-1], "change_pct": round(change, 2),
                 "high": max(closes), "low": min(closes)})
con.close()

rows.sort(key=(lambda r: -r["change_pct"]) if sort_by == "change" else (lambda r: r["symbol"]))
path = tz.output_path(f"price_report_{lookback}d.csv")
with path.open("w", newline="", encoding="utf-8") as fh:
    writer = csv.DictWriter(fh, fieldnames=["symbol", "last", "change_pct", "high", "low"])
    writer.writeheader()
    writer.writerows(rows)

tz.progress(1, "Done")
print(f"Wrote a report for {len(rows)} shares to {path.name}")

# /// script
# requires-python = ">=3.11"
# dependencies = []
#
# [tool.trapyze]
# name = "Demo price data"
# description = "Fills the shared price database with made-up prices, for trying things out."
# icon = "database"
# color = "blue"
# version = "1.0.0"
# writes = ["data/demo_prices.sqlite"]
#
# [[tool.trapyze.settings]]
# key = "symbols"
# label = "Share codes"
# type = "text"
# default = "AAA,BBB,CCC"
# help = "Separate codes with commas."
#
# [[tool.trapyze.settings]]
# key = "days"
# label = "Number of days"
# type = "int"
# default = 250
# min = 20
# max = 2000
#
# [[tool.trapyze.settings]]
# key = "seed"
# label = "Random seed"
# type = "int"
# default = 7
# advanced = true
# ///
"""Writes MADE-UP daily prices into a shared SQLite database.

Shows how one tool fills shared data that other tools read
(see 'Price report'). The numbers are random, not real market data.
"""

import random
import sqlite3
from datetime import date, timedelta

import trapyze_helper as tz

s = tz.settings()
symbols = [x.strip().upper() for x in str(s.get("symbols", "AAA")).split(",") if x.strip()]
days = int(s.get("days", 250))
rng = random.Random(int(s.get("seed", 7)))

db = tz.data_path("demo_prices.sqlite")
con = sqlite3.connect(db)
con.execute(
    "CREATE TABLE IF NOT EXISTS prices (symbol TEXT, day TEXT, close REAL, PRIMARY KEY (symbol, day))"
)

start = date.today() - timedelta(days=days)
for n, symbol in enumerate(symbols):
    tz.progress(n / len(symbols), f"Making prices for {symbol}")
    price = 100.0
    rows = []
    for d in range(days):
        price *= 1 + rng.gauss(0.0003, 0.015)
        rows.append((symbol, (start + timedelta(days=d)).isoformat(), round(price, 2)))
    con.executemany("INSERT OR REPLACE INTO prices VALUES (?, ?, ?)", rows)
    con.commit()

con.close()
tz.progress(1, "Done")
print(f"Saved {days} made-up days for {len(symbols)} share codes in the shared data folder.")

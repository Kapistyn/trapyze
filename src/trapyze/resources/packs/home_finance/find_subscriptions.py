# /// script
# requires-python = ">=3.11"
# dependencies = []
#
# [tool.trapyze]
# name = "Find subscriptions"
# description = "Finds payments that come back every month or year in a bank export, and what they cost per year."
# icon = "calendar"
# color = "purple"
# version = "1.0.0"
#
# [[tool.trapyze.settings]]
# key = "statement"
# label = "Bank export (CSV)"
# type = "file"
# required = true
# help = "Best with a year or more of transactions. The file stays on your computer."
#
# [[tool.trapyze.settings]]
# key = "min_times"
# label = "Seen at least this many times"
# type = "int"
# default = 3
# min = 2
# max = 24
# ///
"""Find subscriptions: groups payments to the same party with about the same amount at a steady rhythm."""

import csv
import re
import statistics
from collections import defaultdict
from pathlib import Path

import bank_csv
import trapyze_helper as tz

s = tz.settings()
statement = Path(s["statement"])
if not statement.is_file():
    raise SystemExit(f"The file {statement} doesn't exist.")
at_least = int(s.get("min_times", 3))

tz.step("Reading the statement")
rows = [r for r in bank_csv.read(statement) if r["amount"] < 0]


def who(text):  # the first words, without numbers and dates, name the other party
    words = [w for w in re.sub(r"[^A-Za-z&.' ]+", " ", text).lower().split() if len(w) > 1]
    return " ".join(words[:3])


groups = defaultdict(list)
for r in rows:
    if who(r["text"]):
        groups[who(r["text"])].append(r)

RHYTHMS = (("weekly", 7, 2, 52), ("monthly", 30.4, 5, 12), ("every 3 months", 91, 12, 4), ("yearly", 365, 25, 1))
found = []
for i, (name, items) in enumerate(groups.items()):
    tz.progress(i / max(len(groups), 1), name)
    if len(items) < at_least:
        continue
    amounts = [-r["amount"] for r in items]
    middle = statistics.median(amounts)
    steady = [r for r in items if abs(-r["amount"] - middle) <= max(0.15 * middle, 1)]
    if len(steady) < at_least:
        continue
    gaps = [(b["date"] - a["date"]).days for a, b in zip(steady, steady[1:])]
    gap = statistics.median(gaps) if gaps else 0
    rhythm = next((r for r in RHYTHMS if abs(gap - r[1]) <= r[2]), None)
    if rhythm is None:
        continue
    found.append({"name": name, "rhythm": rhythm[0], "amount": middle, "per_year": middle * rhythm[3],
                  "times": len(steady), "last": steady[-1]["date"]})

found.sort(key=lambda x: -x["per_year"])
with tz.output_path("subscriptions.csv").open("w", newline="", encoding="utf-8") as f:
    out = csv.writer(f)
    out.writerow(["paid to", "how often", "amount", "per year", "times seen", "last payment"])
    for x in found:
        out.writerow([x["name"], x["rhythm"], f"{x['amount']:.2f}", f"{x['per_year']:.2f}", x["times"], x["last"].isoformat()])

tz.progress(1, "Done")
print(f"Found {len(found)} payments that keep coming back, about {sum(x['per_year'] for x in found):,.0f} a year together.")
for x in found[:8]:
    print(f"  {x['per_year']:>9,.0f} a year  {x['name']} ({x['rhythm']}, {x['amount']:.2f})")

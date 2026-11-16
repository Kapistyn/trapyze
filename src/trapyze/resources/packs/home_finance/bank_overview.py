# /// script
# requires-python = ">=3.11"
# dependencies = []
#
# [tool.trapyze]
# name = "Bank statement overview"
# description = "Sorts a bank export into categories and totals each month. Works with most banks' CSV files."
# icon = "coin"
# color = "teal"
# version = "1.0.0"
#
# [[tool.trapyze.settings]]
# key = "statement"
# label = "Bank export (CSV)"
# type = "file"
# required = true
# help = "Download your transactions as CSV from your bank's website. The file stays on your computer."
#
# [[tool.trapyze.settings]]
# key = "date_column"
# label = "Name of the date column"
# type = "text"
# default = ""
# advanced = true
# help = "Only needed when traPYze can't find it by itself."
#
# [[tool.trapyze.settings]]
# key = "amount_column"
# label = "Name of the amount column"
# type = "text"
# default = ""
# advanced = true
#
# [[tool.trapyze.settings]]
# key = "text_column"
# label = "Name of the description column"
# type = "text"
# default = ""
# advanced = true
# ///
"""Bank statement overview: categories per month as a web page and as CSV files.

The categories come from keywords in my-categories.csv in the shared data folder. It is
made the first time with common keywords; open it in Excel and add your own shops.
"""

import csv
import html
from collections import defaultdict
from pathlib import Path

import bank_csv
import trapyze_helper as tz

STARTER = """keyword,category
salary,Income
salaris,Income
loon,Income
pension,Income
rent,Housing
huur,Housing
mortgage,Housing
hypotheek,Housing
energy,Utilities
energie,Utilities
water,Utilities
internet,Utilities
telecom,Utilities
mobile,Utilities
insurance,Insurance
verzekering,Insurance
supermarket,Groceries
albert heijn,Groceries
jumbo,Groceries
lidl,Groceries
aldi,Groceries
tesco,Groceries
restaurant,Eating out
cafe,Eating out
thuisbezorgd,Eating out
uber eats,Eating out
fuel,Transport
shell,Transport
parking,Transport
ns groep,Transport
train,Transport
netflix,Subscriptions
spotify,Subscriptions
disney,Subscriptions
pharmacy,Health
apotheek,Health
dentist,Health
tandarts,Health
tax,Taxes
belasting,Taxes
amazon,Shopping
bol.com,Shopping
ikea,Shopping
savings,Savings
spaar,Savings
atm,Cash
geldautomaat,Cash
"""

s = tz.settings()
statement = Path(s["statement"])
if not statement.is_file():
    raise SystemExit(f"The file {statement} doesn't exist.")

rules_file = tz.data_path("my-categories.csv")
if not rules_file.exists():
    rules_file.write_text(STARTER, encoding="utf-8")
rules = []
with rules_file.open(newline="", encoding="utf-8-sig") as f:
    for row in csv.reader(f):
        if len(row) >= 2 and row[0].strip() and row[0].strip().lower() != "keyword":
            rules.append((row[0].strip().lower(), row[1].strip() or "Other"))
rules.sort(key=lambda r: -len(r[0]))  # the longest keyword wins

tz.step("Reading the statement")
rows = bank_csv.read(statement, s.get("date_column", ""), s.get("amount_column", ""), s.get("text_column", ""))


def category(row):
    text = row["text"].lower()
    for keyword, name in rules:
        if keyword in text:
            return name
    return "Other income" if row["amount"] > 0 else "Other"


months = sorted({r["date"].strftime("%Y-%m") for r in rows})
totals = defaultdict(lambda: defaultdict(float))
with tz.output_path("transactions.csv").open("w", newline="", encoding="utf-8") as f:
    out = csv.writer(f)
    out.writerow(["date", "amount", "category", "description"])
    for i, r in enumerate(rows):
        if i % 200 == 0:
            tz.progress(i / len(rows), "Sorting into categories")
        r["category"] = category(r)
        totals[r["category"]][r["date"].strftime("%Y-%m")] += r["amount"]
        out.writerow([r["date"].isoformat(), f"{r['amount']:.2f}", r["category"], r["text"]])

names = sorted(totals, key=lambda c: sum(totals[c].values()))
with tz.output_path("per-month.csv").open("w", newline="", encoding="utf-8") as f:
    out = csv.writer(f)
    out.writerow(["category", *months, "total"])
    for c in names:
        out.writerow([c, *[f"{totals[c][m]:.2f}" for m in months], f"{sum(totals[c].values()):.2f}"])

money_in = sum(r["amount"] for r in rows if r["amount"] > 0)
money_out = -sum(r["amount"] for r in rows if r["amount"] < 0)
other = sorted((r for r in rows if r["category"] == "Other"), key=lambda r: r["amount"])[:15]
num = lambda v: f"{v:,.2f}"  # noqa: E731
cells = "".join(
    "<tr><td>" + html.escape(c) + "</td>" + "".join(f"<td class=n>{num(totals[c][m]) if totals[c][m] else ''}</td>" for m in months)
    + f"<td class='n t'>{num(sum(totals[c].values()))}</td></tr>" for c in names)
page = f"""<!doctype html><meta charset="utf-8"><title>Bank statement overview</title>
<style>body{{font-family:system-ui,sans-serif;margin:40px;color:#151a23}}table{{border-collapse:collapse;margin:12px 0 28px}}
td,th{{border-bottom:1px solid #e3e6ec;padding:6px 12px;text-align:left}}th{{background:#f4f5f8}}.n{{text-align:right;
font-variant-numeric:tabular-nums}}.t{{font-weight:600}}.box{{display:inline-block;margin-right:28px}}.box b{{font-size:22px;display:block}}</style>
<h1>Bank statement overview</h1><p>{rows[0]['date']:%d %B %Y} to {rows[-1]['date']:%d %B %Y} · {len(rows)} transactions</p>
<p><span class=box>Money in<b>{num(money_in)}</b></span><span class=box>Money out<b>{num(money_out)}</b></span>
<span class=box>Difference<b>{num(money_in - money_out)}</b></span></p>
<h2>Per category and month</h2><table><tr><th>Category</th>{''.join(f'<th class=n>{m}</th>' for m in months)}<th class=n>Total</th></tr>{cells}</table>
<h2>Biggest payments without a category</h2><p>Add a keyword for these to my-categories.csv in the shared data folder.</p>
<table><tr><th>Date</th><th class=n>Amount</th><th>Description</th></tr>
{''.join(f"<tr><td>{r['date']}</td><td class=n>{num(r['amount'])}</td><td>{html.escape(r['text'][:90])}</td></tr>" for r in other)}</table>"""
tz.output_path("overview.html").write_text(page, encoding="utf-8")

tz.progress(1, "Done")
print(f"{len(rows)} transactions, {len(months)} months. In: {num(money_in)}  Out: {num(money_out)}")
print("Open overview.html. Not happy with a category? Add keywords to my-categories.csv in the shared data folder.")

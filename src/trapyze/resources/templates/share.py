# /// script
# requires-python = ">=3.11"
# dependencies = []
#
# [tool.trapyze]
# name = "{name}"
# description = "{description}"
# icon = "mail"
# color = "blue"
# version = "0.1.0"
#
# [[tool.trapyze.settings]]
# key = "title"
# label = "Report title"
# type = "text"
# default = "My report"
#
# [[tool.trapyze.settings]]
# key = "file_name"
# label = "Data file to show"
# type = "text"
# default = "downloaded.csv"
# help = "A CSV file in the shared data folder; the first rows go in the report."
#
# [[tool.trapyze.settings]]
# key = "rows"
# label = "Rows to show"
# type = "int"
# default = 20
# min = 1
# max = 500
# ///
"""{name}: turns a CSV from the shared data folder into a neat HTML report.

A starting point made by traPYze. To also mail the report: add an email
connection on the Connections screen, add  connections = ["gmail"]  to the
label above (use your connection's name), and send it with smtplib using
os.environ["SMTP_HOST"], ["SMTP_PORT"], ["SMTP_USER"] and ["SMTP_PASS"].
"""

import csv
import datetime
import html

import trapyze_helper as tz

s = tz.settings()
source = tz.data_path(s.get("file_name") or "downloaded.csv")
title = s.get("title") or "My report"
rows = []
if source.exists():
    with source.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))[: int(s.get("rows", 20)) + 1]

tz.step("Writing the report")
head, body = (rows[0], rows[1:]) if rows else ([], [])
table = "<tr>" + "".join(f"<th>{html.escape(c)}</th>" for c in head) + "</tr>"
table += "".join("<tr>" + "".join(f"<td>{html.escape(c)}</td>" for c in r) + "</tr>" for r in body)
page = f"""<!doctype html><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>body{{font-family:system-ui,sans-serif;margin:40px;color:#151a23}}table{{border-collapse:collapse}}
td,th{{border-bottom:1px solid #e3e6ec;padding:6px 12px;text-align:left}}th{{background:#f4f5f8}}</style>
<h1>{html.escape(title)}</h1><p>Made {datetime.datetime.now():%d %B %Y, %H:%M}</p>
{"<table>" + table + "</table>" if rows else "<p>No data found in " + html.escape(source.name) + ".</p>"}"""
out = tz.output_path("report.html")
out.write_text(page, encoding="utf-8")
tz.progress(1, "Done")
print(f"Report with {len(body)} rows written to {out.name}")

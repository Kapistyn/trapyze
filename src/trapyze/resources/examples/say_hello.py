# /// script
# requires-python = ">=3.11"
# dependencies = []
#
# [tool.trapyze]
# name = "Say hello"
# description = "A first test: writes a greeting to a text file."
# icon = "document"
# color = "teal"
# version = "1.0.0"
#
# [[tool.trapyze.settings]]
# key = "name"
# label = "Your name"
# type = "text"
# default = "Ada"
#
# [[tool.trapyze.settings]]
# key = "times"
# label = "How many greetings"
# type = "int"
# default = 3
# min = 1
# max = 10
#
# [[tool.trapyze.settings]]
# key = "shout"
# label = "Shout it"
# type = "bool"
# default = false
# ///
"""Say hello: the smallest possible traPYze tool."""

import time

import trapyze_helper as tz

s = tz.settings()
name = s.get("name", "there")
times = int(s.get("times", 3))
shout = str(s.get("shout", False)).lower() in ("true", "1", "yes")

lines = []
for i in range(times):
    tz.progress(i / times, f"Writing greeting {i + 1} of {times}")
    greeting = f"Hello, {name}!"
    lines.append(greeting.upper() if shout else greeting)
    time.sleep(0.2)

path = tz.output_path("greeting.txt")
path.write_text("\n".join(lines) + "\n", encoding="utf-8")
tz.progress(1, "Done")
print(f"Wrote {times} greetings to {path.name}")

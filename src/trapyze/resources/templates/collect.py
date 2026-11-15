# /// script
# requires-python = ">=3.11"
# dependencies = []
#
# [tool.trapyze]
# name = "{name}"
# description = "{description}"
# icon = "cloud"
# color = "teal"
# version = "0.1.0"
#
# [[tool.trapyze.settings]]
# key = "url"
# label = "Web address to download"
# type = "text"
# required = true
# help = "For example a CSV file on a website."
#
# [[tool.trapyze.settings]]
# key = "file_name"
# label = "Save it as"
# type = "text"
# default = "downloaded.csv"
# help = "Saved in the shared data folder, so other tools can read it."
# ///
"""{name}: downloads a file into the shared data folder.

A starting point made by traPYze. Change it as you like: the label at the top
makes the settings window, tz.progress() moves the progress bar.
"""

import urllib.request

import trapyze_helper as tz

s = tz.settings()
url = s["url"]
target = tz.data_path(s.get("file_name") or "downloaded.csv")

tz.step(f"Downloading {url}")
request = urllib.request.Request(url, headers={"User-Agent": "traPYze"})
with urllib.request.urlopen(request, timeout=60) as response:
    total = int(response.headers.get("Content-Length") or 0)
    data = bytearray()
    while chunk := response.read(64 * 1024):
        data.extend(chunk)
        if total:
            tz.progress(len(data) / total, f"{len(data) // 1024} of {total // 1024} KB")

target.parent.mkdir(parents=True, exist_ok=True)
target.write_bytes(data)
tz.progress(1, "Done")
print(f"Saved {len(data) // 1024} KB to {target.name}")

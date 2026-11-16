# /// script
# requires-python = ">=3.11"
# dependencies = []
#
# [tool.trapyze]
# name = "Restore a backup"
# description = "Checks a backup zip and unpacks it into a new folder, never over your current files."
# icon = "archive"
# color = "teal"
# version = "1.0.0"
#
# [[tool.trapyze.settings]]
# key = "backup"
# label = "Backup file (.zip)"
# type = "file"
# required = true
# help = "For example one made by 'Back up a folder'."
#
# [[tool.trapyze.settings]]
# key = "target"
# label = "Where to unpack it"
# type = "folder"
# required = true
# help = "A new folder with the backup's name is made here."
#
# [[tool.trapyze.settings]]
# key = "only_check"
# label = "Only check the backup"
# type = "bool"
# default = false
# help = "On: test that the backup is complete and readable, without unpacking it."
# ///
"""Restore a backup: always unpacks into a new, empty folder, so nothing you have now can be replaced."""

import zipfile
from pathlib import Path

import trapyze_helper as tz

s = tz.settings()
backup, where = Path(s["backup"]), Path(s["target"])
if not backup.is_file():
    raise SystemExit(f"The file {backup} doesn't exist.")
if not where.is_dir():
    raise SystemExit(f"The folder {where} doesn't exist.")
if not zipfile.is_zipfile(backup):
    raise SystemExit(f"{backup.name} isn't a zip file, or it is damaged.")

with zipfile.ZipFile(backup) as z:
    tz.step("Checking the backup")
    broken = z.testzip()
    if broken:
        raise SystemExit(f"The backup is damaged: '{broken}' can't be read. Use an older backup.")
    members = [m for m in z.infolist() if not m.is_dir()]
    size = sum(m.file_size for m in members)
    print(f"{backup.name}: {len(members)} files, {size / 1024 / 1024:.1f} MB, complete and readable.")
    if not s.get("only_check"):
        target = where / f"{backup.stem} restored"
        n = 2
        while target.exists():
            target = where / f"{backup.stem} restored ({n})"
            n += 1
        target.mkdir()
        for i, m in enumerate(members):
            tz.progress(i / max(len(members), 1), m.filename)
            z.extract(m, target)  # zipfile keeps every file inside the target folder
        print(f"Unpacked into {target}. Your current files weren't touched.")
tz.progress(1, "Done")

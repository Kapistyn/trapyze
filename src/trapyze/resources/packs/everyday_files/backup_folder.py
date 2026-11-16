# /// script
# requires-python = ">=3.11"
# dependencies = []
#
# [tool.trapyze]
# name = "Back up a folder"
# description = "Makes a dated zip of a folder on another drive, and keeps the newest few."
# icon = "archive"
# color = "slate"
# version = "1.0.0"
#
# [[tool.trapyze.settings]]
# key = "folder"
# label = "Folder to back up"
# type = "folder"
# required = true
#
# [[tool.trapyze.settings]]
# key = "target"
# label = "Where to put the backup"
# type = "folder"
# required = true
# help = "Best on another drive, such as a USB disk."
#
# [[tool.trapyze.settings]]
# key = "keep"
# label = "Backups to keep"
# type = "int"
# default = 5
# min = 1
# max = 100
# help = "Older backups of this same folder are removed."
# ///
"""Back up a folder: one zip per run, named after the folder and the date. Good to plan weekly."""

import datetime
import re
import zipfile
from pathlib import Path

import trapyze_helper as tz

s = tz.settings()
source, target = Path(s["folder"]).resolve(), Path(s["target"]).resolve()
if not source.is_dir():
    raise SystemExit(f"The folder {source} doesn't exist.")
if not target.is_dir():
    raise SystemExit(f"The backup place {target} doesn't exist. Is the drive connected?")
if target == source or source in target.parents:
    raise SystemExit("The backup can't go inside the folder it backs up. Choose another place.")

tz.step("Listing files")
files = [p for p in source.rglob("*") if p.is_file() and not p.is_symlink()]
stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
name = re.sub(r"[^A-Za-z0-9_-]+", "_", source.name) or "backup"
final = target / f"{name}-backup-{stamp}.zip"
part = final.with_suffix(".part")  # only a finished backup gets the .zip name

skipped = []
with zipfile.ZipFile(part, "w", zipfile.ZIP_DEFLATED) as z:
    for i, p in enumerate(files):
        tz.progress(i / max(len(files), 1), p.name)
        try:
            z.write(p, p.relative_to(source))
        except OSError:
            skipped.append(str(p.relative_to(source)))  # open in another program, for example
part.rename(final)

old = sorted(target.glob(f"{name}-backup-*.zip"))[: -int(s.get("keep", 5))]
for p in old:
    p.unlink()

tz.progress(1, "Done")
tz.output_path("backup-log.txt").write_text(
    f"Backup: {final}\nFiles: {len(files) - len(skipped)}\nSkipped: {len(skipped)}\n" + "\n".join(skipped) + "\n", encoding="utf-8")
print(f"Backed up {len(files) - len(skipped)} files to {final.name} ({final.stat().st_size / 1024 / 1024:.1f} MB).")
if skipped:
    print(f"WARNING: {len(skipped)} files couldn't be read and were skipped; see backup-log.txt.")
if old:
    print(f"Removed {len(old)} older backup(s).")

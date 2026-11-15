"""Updating traPYze itself, from its releases on GitHub.

traPYze looks once a day for a newer release (never more often, and only when
switched on). Updating can't happen while traPYze runs, because Windows won't
replace a program that is in use. So traPYze writes a small update script, starts
it on its own, and quits; the script waits for traPYze to close, installs the new
version with uv, and starts traPYze again. Everything it does goes to update.log.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

from . import __version__
from .project import LATEST_API, RELEASES, configured
from .store import _read, _write

CHECK_EVERY = 24 * 3600


class UpdateError(Exception):
    """A plain-English problem with updating."""


def version_key(v: str) -> tuple:
    """'0.12.0' < '0.12.1' < '1.0.0rc1' < '1.0.0'."""
    m = re.match(r"v?(\d+)(?:\.(\d+))?(?:\.(\d+))?(.*)$", v.strip())
    if not m:
        return (0, 0, 0, 0, v)
    major, minor, patch, rest = int(m[1]), int(m[2] or 0), int(m[3] or 0), m[4].lstrip(".-")
    return (major, minor, patch, 0 if rest else 1, rest)


def newer(candidate: str, current: str = __version__) -> bool:
    return version_key(candidate) > version_key(current)


def fetch_latest(opener: Callable | None = None, url: str = LATEST_API) -> dict[str, Any]:
    """The newest release on GitHub: {version, notes, page, wheel, published}."""
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": f"traPYze/{__version__}"})
    try:
        with (opener or urllib.request.urlopen)(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise UpdateError("There's no release online yet.") from None
        if exc.code == 403:
            raise UpdateError("GitHub asks to wait a while before checking again.") from None
        raise UpdateError(f"GitHub answered {exc.code}.") from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise UpdateError(f"Couldn't reach GitHub ({getattr(exc, 'reason', exc)}). Check the internet connection.") from None
    wheel = next((a.get("browser_download_url") for a in data.get("assets", [])
                  if str(a.get("name", "")).endswith(".whl")), None)
    notes = re.split(r"\n#+ *Install or update", str(data.get("body") or ""))[0].strip()  # the how-to is for the web page
    return {"version": str(data.get("tag_name", "")).lstrip("v"), "notes": notes[:20000],
            "page": data.get("html_url") or RELEASES, "wheel": wheel, "published": data.get("published_at")}


class Updates:
    def __init__(self, internal: Path):
        self.path = internal / "update.json"
        self.log = internal / "update.log"

    def state(self) -> dict[str, Any]:
        data = _read(self.path, {})
        data = data if isinstance(data, dict) else {}
        data.setdefault("auto", True)
        latest = data.get("latest") or {}
        data["current"] = __version__
        data["available"] = bool(latest.get("version") and newer(latest["version"]) and latest.get("wheel"))
        data["online"] = configured()
        return data

    def set_auto(self, on: bool) -> None:
        data = _read(self.path, {})
        data = data if isinstance(data, dict) else {}
        data["auto"] = bool(on)
        _write(self.path, data)

    def due(self, now: float | None = None) -> bool:
        if os.environ.get("TRAPYZE_NO_UPDATE_CHECK"):  # tests, or people who never want it
            return False
        st = self.state()
        return st["online"] and st["auto"] and (now or time.time()) - float(st.get("checked") or 0) >= CHECK_EVERY

    def check(self, opener: Callable | None = None, now: float | None = None) -> dict[str, Any]:
        if not configured():
            raise UpdateError("This copy of traPYze was built without a home online, so there's nothing to check.")
        data = _read(self.path, {})
        data = data if isinstance(data, dict) else {}
        data["checked"] = now or time.time()
        try:
            data["latest"] = fetch_latest(opener)
            data.pop("error", None)
        except UpdateError as exc:
            data["error"] = str(exc)
            _write(self.path, data)
            raise
        _write(self.path, data)
        return self.state()

    def last_result(self) -> str:
        try:
            return self.log.read_text(encoding="utf-8", errors="replace")[-4000:]
        except OSError:
            return ""


def update_script(engine: str, wheel: str, pid: int, log: Path, restart: list[str], platform: str = sys.platform) -> tuple[str, str]:
    """(file name, contents) of the script that waits for traPYze to close, updates it and starts it again."""
    spec = f"trapyze[desktop] @ {wheel}"
    if platform.startswith("win"):
        q = lambda s: "'" + str(s).replace("'", "''") + "'"  # noqa: E731 - PowerShell single quotes
        start = f"Start-Process -FilePath {q(restart[0])}" + (f" -ArgumentList {', '.join(q(a) for a in restart[1:])}" if restart[1:] else "")
        return "trapyze-update.ps1", "\n".join([
            "$ErrorActionPreference = 'Continue'",
            f"$log = {q(log)}",
            "function Say($t) { Add-Content -Path $log -Value ((Get-Date -Format 's') + '  ' + $t) }",
            "Say 'Waiting for traPYze to close'",
            f"for ($i = 0; $i -lt 120 -and (Get-Process -Id {pid} -ErrorAction SilentlyContinue); $i++) {{ Start-Sleep -Milliseconds 500 }}",
            f"Say 'Installing {wheel}'",
            f"$out = & {q(engine)} tool install --reinstall --python 3.12 {q(spec)} 2>&1",
            "Add-Content -Path $log -Value ($out | Out-String)",
            "if ($LASTEXITCODE -eq 0) { Say 'UPDATED' } else { Say ('FAILED with code ' + $LASTEXITCODE) }",
            start,
            "",
        ])
    sq = lambda s: "'" + str(s).replace("'", "'\\''") + "'"  # noqa: E731 - POSIX shell single quotes
    return "trapyze-update.sh", "\n".join([
        "#!/bin/sh",
        f"log={sq(log)}",
        'say() { echo "$(date +%Y-%m-%dT%H:%M:%S)  $1" >> "$log"; }',
        "say 'Waiting for traPYze to close'",
        f"i=0; while kill -0 {pid} 2>/dev/null && [ $i -lt 120 ]; do sleep 0.5; i=$((i+1)); done",
        f"say {sq('Installing ' + wheel)}",
        f'if {sq(engine)} tool install --reinstall --python 3.12 {sq(spec)} >> "$log" 2>&1; then say UPDATED; else say "FAILED with code $?"; fi',
        f"nohup {' '.join(sq(a) for a in restart)} >/dev/null 2>&1 &",
        "",
    ])


def start_update(internal: Path, engine: str | None, wheel: str, restart: list[str], pid: int | None = None,
                 popen: Callable = subprocess.Popen) -> Path:
    """Write the update script and start it on its own. The caller quits traPYze straight after."""
    if not engine:
        raise UpdateError("uv isn't found, so traPYze can't update itself. Run the installer again instead.")
    if not wheel or not wheel.startswith("https://"):
        raise UpdateError("The release has no installable file.")
    internal.mkdir(parents=True, exist_ok=True)
    log = internal / "update.log"
    log.write_text("", encoding="utf-8")
    name, text = update_script(engine, wheel, pid or os.getpid(), log, restart)
    script = internal / name
    script.write_text(text, encoding="utf-8")
    if name.endswith(".ps1"):
        flags = 0x00000008 | 0x00000200 | 0x08000000  # detached, own group, no window
        popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", str(script)],
              creationflags=flags, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        script.chmod(0o755)
        popen(["/bin/sh", str(script)], start_new_session=True, stdin=subprocess.DEVNULL,
              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return script

"""Updating traPYze itself, from its releases on GitHub.

traPYze looks once a day for a newer release (never more often, and only when
switched on). Updating can't happen while traPYze runs, because Windows won't
replace a program that is in use. So traPYze starts a small updater (a Python
script run by the base interpreter, outside traPYze), waits until it reports that
it runs, and only then quits; the updater waits for traPYze to close, installs the
new version with uv, and starts traPYze again. Everything it does goes to update.log.
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
    sums = next((a.get("browser_download_url") for a in data.get("assets", []) if a.get("name") == "SHA256SUMS"), None)
    return {"sums": sums, "version": str(data.get("tag_name", "")).lstrip("v"), "notes": notes[:20000],
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


def _fetch(url: str, opener: Callable | None, limit: int) -> bytes:
    if not str(url).startswith("https://"):
        raise UpdateError("The release has no installable file.")
    req = urllib.request.Request(url, headers={"User-Agent": f"traPYze/{__version__}"})
    try:
        with (opener or urllib.request.urlopen)(req, timeout=60) as resp:
            data = resp.read(limit + 1)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise UpdateError(f"Couldn't download the update ({getattr(exc, 'reason', exc)}).") from None
    if len(data) > limit:
        raise UpdateError("The update is much larger than expected, so it wasn't installed.")
    return data


def download_verified(internal: Path, latest: dict[str, Any], opener: Callable | None = None) -> Path:
    """Download the new version and compare it with the checksum the release published.

    Returns the downloaded file. Nothing is installed when the two don't match."""
    import hashlib

    wheel_url, sums_url = latest.get("wheel"), latest.get("sums")
    if not sums_url:
        raise UpdateError("This release has no checksums, so traPYze can't verify it. Run the installer from the "
                          "release page instead.")
    name = str(wheel_url or "").rsplit("/", 1)[-1]
    if not re.fullmatch(r"trapyze-[A-Za-z0-9.]+-py3-none-any\.whl", name):
        raise UpdateError("The release has no installable file.")
    listed = {}
    for line in _fetch(sums_url, opener, 100_000).decode("utf-8", "replace").splitlines():
        parts = line.split()
        if len(parts) == 2 and re.fullmatch(r"[0-9a-fA-F]{64}", parts[0]):
            listed[parts[1].lstrip("*")] = parts[0].lower()
    if name not in listed:
        raise UpdateError("The release's checksums don't mention the update file, so it wasn't installed.")
    data = _fetch(wheel_url, opener, 50 * 1024 * 1024)
    if hashlib.sha256(data).hexdigest() != listed[name]:
        raise UpdateError("The downloaded update doesn't match its checksum, so it wasn't installed. Try again later; "
                          "if it keeps happening, report it.")
    folder = internal / "update"
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob("*.whl"):
        old.unlink(missing_ok=True)
    target = folder / name
    target.write_bytes(data)
    return target


HELPER = r'''"""traPYze updater: waits for traPYze to close, installs the new version with uv, starts it again.
Standard library only, run by the base Python, so nothing it needs is replaced while it works."""
import json, os, subprocess, sys, time

job = json.loads(sys.argv[1])
log = job["log"]


def say(text):
    with open(log, "a", encoding="utf-8") as f:
        f.write(time.strftime("%Y-%m-%dT%H:%M:%S") + "  " + text + "\n")


def alive(pid):
    if os.name == "nt":
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x00100000 | 0x1000, False, pid)  # SYNCHRONIZE | QUERY_LIMITED_INFORMATION
        if not h:
            return False
        try:
            return k.WaitForSingleObject(h, 0) == 0x102  # still running
        finally:
            k.CloseHandle(h)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def detached(cmd, **kw):
    if os.name != "nt":
        return subprocess.Popen(cmd, start_new_session=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, **kw)
    base = 0x00000008 | 0x00000200  # detached, own process group
    try:
        return subprocess.Popen(cmd, creationflags=base | 0x01000000, close_fds=True, **kw)  # and out of any job
    except OSError:
        return subprocess.Popen(cmd, creationflags=base, close_fds=True, **kw)


say("STARTED: waiting for traPYze to close")
for _ in range(240):
    if not alive(job["pid"]):
        break
    time.sleep(0.5)
else:
    say("traPYze didn't close within two minutes; updating anyway")
say("Installing " + job["wheel"])
flags = 0x08000000 if os.name == "nt" else 0  # no console window
try:
    r = subprocess.run([job["engine"], "tool", "install", "--reinstall", "--python", "3.12",
                        "trapyze[desktop] @ " + job["wheel"]], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", creationflags=flags, timeout=900)
    with open(log, "a", encoding="utf-8") as f:
        f.write((r.stdout or "") + (r.stderr or ""))
    say("UPDATED" if r.returncode == 0 else "FAILED with code %d" % r.returncode)
except Exception as exc:
    say("FAILED: %r" % (exc,))
try:
    detached(job["restart"])
    say("Started traPYze again")
except Exception as exc:
    say("Couldn't start traPYze again (%r); open it from its shortcut" % (exc,))
'''


def helper_python() -> str:
    """The Python that runs the updater: the base interpreter (not the one being replaced), windowless on Windows."""
    base = Path(getattr(sys, "_base_executable", "") or sys.executable)
    if sys.platform.startswith("win"):
        w = base.with_name("pythonw.exe")
        if w.exists():
            return str(w)
    return str(base)


def start_update(internal: Path, engine: str | None, wheel: str, restart: list[str], pid: int | None = None,
                 popen: Callable = subprocess.Popen, python: str | None = None, wait: float = 15.0) -> Path:
    """Start the updater on its own and wait until it says it runs. The caller quits traPYze straight after.

    Raises UpdateError (and traPYze stays open) when the updater doesn't start."""
    if not engine:
        raise UpdateError("uv isn't found, so traPYze can't update itself. Run the installer again instead.")
    wheel = str(wheel or "")
    if not (wheel.startswith("https://") or Path(wheel).is_file()):
        raise UpdateError("The release has no installable file.")
    internal.mkdir(parents=True, exist_ok=True)
    log = internal / "update.log"
    log.write_text("", encoding="utf-8")
    script = internal / "trapyze-update.py"
    script.write_text(HELPER, encoding="utf-8")
    for old in ("trapyze-update.ps1", "trapyze-update.sh"):
        (internal / old).unlink(missing_ok=True)
    job = json.dumps({"log": str(log), "pid": pid or os.getpid(), "engine": engine, "wheel": wheel, "restart": restart})
    cmd = [python or helper_python(), "-I", str(script), job]
    if sys.platform.startswith("win"):
        base = 0x00000008 | 0x00000200  # detached, own process group
        try:
            popen(cmd, creationflags=base | 0x01000000, close_fds=True,  # out of any job traPYze runs in
                  stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            popen(cmd, creationflags=base, close_fds=True,
                  stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        popen(cmd, start_new_session=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
              stderr=subprocess.DEVNULL)
    deadline = time.time() + wait
    while time.time() < deadline:
        try:
            if "STARTED" in log.read_text(encoding="utf-8", errors="replace"):
                return script
        except OSError:
            pass
        time.sleep(0.2)
    raise UpdateError("The updater didn't start, so traPYze stays open and nothing changed. "
                      f"Run the installer from {RELEASES} instead; your tools, results and vault are kept.")

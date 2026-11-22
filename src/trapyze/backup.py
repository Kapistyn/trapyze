"""A backup of the scripts folder in Git: every tool and program, with the history of how they changed.

Only code and notes go in (a list of file types, never keys or data). Optionally the copy is
pushed to a remote that you own; use a private repository. Sign-in is Git's own business:
traPYze never sees or stores a password for it.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from .home import Home

DEFAULTS: dict[str, Any] = {"remote": "", "auto": False, "last": None, "last_ok": None, "last_note": ""}
EVERY = 20 * 3600
IGNORE = """# Made by traPYze: only code and notes are backed up, never keys or data.
*
!*/
!*.py
!*.md
!*.txt
!*.toml
!*.json
!*.yaml
!*.yml
!.gitignore
_replaced/
__pycache__/
.venv/
venv/
.env*
*.key
*.pem
"""
SECRET = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")


class BackupProblem(Exception):
    pass


def _path(home: Home) -> Path:
    return home.internal / "backup.json"


def read(home: Home) -> dict[str, Any]:
    try:
        data = json.loads(_path(home).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    return {**DEFAULTS, **{k: v for k, v in data.items() if k in DEFAULTS}}


def _write(home: Home, settings: dict[str, Any]) -> None:
    _path(home).parent.mkdir(parents=True, exist_ok=True)
    _path(home).write_text(json.dumps({k: settings[k] for k in DEFAULTS}, indent=1), encoding="utf-8")


def check_remote(url: str) -> str:
    url = url.strip()
    if not url:
        return ""
    if url.startswith("-") or re.search(r"\s", url):
        raise BackupProblem("That doesn't look like a Git address.")
    if re.match(r"^https://[^/@]+:[^/@]*@", url):
        raise BackupProblem("Leave the password out of the address. Git asks you to sign in itself the first time.")
    if not re.match(r"^(https://|ssh://|git@)[\w.@:/~+-]+$", url):
        raise BackupProblem("Use an address like https://github.com/you/scripts.git or git@github.com:you/scripts.git.")
    return url


def _git(home: Home, *args: str, timeout: int = 120) -> subprocess.CompletedProcess:
    exe = shutil.which("git")
    if not exe:
        raise BackupProblem("Git isn't installed on this computer. Install it from git-scm.com, then try again.")
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}
    try:
        return subprocess.run([exe, "-c", "user.name=traPYze", "-c", "user.email=trapyze@localhost", "-c", "core.autocrlf=false", *args],
                              cwd=home.scripts, capture_output=True, text=True, timeout=timeout, env=env, encoding="utf-8", errors="replace",
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        raise BackupProblem("Git took too long. Check the connection and the address, then try again.") from None


def state(home: Home) -> dict[str, Any]:
    s = read(home)
    s["git"] = bool(shutil.which("git"))
    s["started"] = (home.scripts / ".git").is_dir()
    s["commits"] = 0
    if s["git"] and s["started"]:
        done = _git(home, "rev-list", "--count", "HEAD")
        s["commits"] = int(done.stdout.strip() or 0) if done.returncode == 0 else 0
    return s


def change(home: Home, body: dict[str, Any]) -> dict[str, Any]:
    s = read(home)
    if "remote" in body:
        s["remote"] = check_remote(str(body["remote"]))
    if "auto" in body:
        s["auto"] = bool(body["auto"])
    _write(home, s)
    return state(home)


def due(home: Home) -> bool:
    s = read(home)
    return bool(s["auto"]) and shutil.which("git") is not None and time.time() - (s.get("last") or 0) > EVERY


def _start(home: Home) -> None:
    home.scripts.mkdir(parents=True, exist_ok=True)
    if not (home.scripts / ".git").is_dir():
        done = _git(home, "init", "-b", "main")
        if done.returncode != 0:
            raise BackupProblem(done.stderr.strip() or "Git could not start a backup here.")
    (home.scripts / ".gitignore").write_text(IGNORE, encoding="utf-8")


def run(home: Home) -> dict[str, Any]:
    """Save a snapshot of the scripts; push it when a remote is set. Returns what happened, in plain words."""
    s = read(home)
    s["last"] = time.time()
    try:
        _start(home)
        _git(home, "add", "-A")
        staged = _git(home, "diff", "--cached", "--name-only").stdout.split()
        held_back = []
        for name in staged:
            f = home.scripts / name
            try:
                if f.is_file() and SECRET.search(f.read_text(encoding="utf-8", errors="ignore")):
                    _git(home, "reset", "-q", "--", name)
                    held_back.append(name)
            except OSError:
                continue
        staged = [n for n in staged if n not in held_back]
        saved = 0
        if staged:
            done = _git(home, "commit", "-q", "-m", f"Backup {datetime.now():%Y-%m-%d %H:%M}")
            if done.returncode != 0:
                raise BackupProblem(done.stderr.strip() or done.stdout.strip() or "Git could not save the snapshot.")
            saved = len(staged)
        pushed = False
        if s["remote"]:
            have = _git(home, "remote", "get-url", "origin")
            if have.returncode != 0:
                _git(home, "remote", "add", "origin", s["remote"])
            elif have.stdout.strip() != s["remote"]:
                _git(home, "remote", "set-url", "origin", s["remote"])
            done = _git(home, "push", "-u", "origin", "HEAD:main", timeout=180)
            if done.returncode != 0:
                tail = (done.stderr.strip().splitlines() or ["The push was refused."])[-1]
                raise BackupProblem(f"Saved here, but not sent to the remote: {tail}")
            pushed = True
        note = (f"{saved} changed file{'s' if saved != 1 else ''} saved" if saved else "Nothing had changed") + \
               (", and sent to your remote" if pushed else "") + "."
        if held_back:
            note += f" Left out because they contain a private key: {', '.join(held_back)}."
        s.update(last_ok=time.time(), last_note=note)
        _write(home, s)
        return {"ok": True, "note": note, **state(home)}
    except BackupProblem as exc:
        s["last_note"] = str(exc)
        _write(home, s)
        raise

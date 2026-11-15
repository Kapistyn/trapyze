"""Opening a tool's script in the user's own editor (VS Code, PyCharm, Notepad++ …).

traPYze looks for the editors that are installed, lets the user pick one in Look and
feel, and starts it detached, so closing the editor never affects traPYze.
"""

from __future__ import annotations

import glob as _glob
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

DETACHED = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
NO_WINDOW = 0x08000000


def _first(paths: list[str], exists: Callable[[str], bool], glob: Callable[[str], list[str]]) -> str | None:
    for p in paths:
        if any(ch in p for ch in "*?"):
            hits = sorted(glob(p), reverse=True)  # newest version first
            if hits:
                return hits[0]
        elif p and exists(p):
            return p
    return None


def available(platform: str | None = None, env: dict[str, str] | None = None, which=shutil.which,
              exists: Callable[[str], bool] = os.path.exists, glob=_glob.glob) -> list[dict[str, Any]]:
    """The editors found on this computer, best first: {id, name, command: [...]}."""
    platform = platform or sys.platform
    env = os.environ if env is None else env
    found: list[dict[str, Any]] = []

    def add(eid: str, name: str, command: list[str] | None) -> None:
        if command and not any(e["id"] == eid for e in found):
            found.append({"id": eid, "name": name, "command": command})

    if platform.startswith("win"):
        local, pf = env.get("LOCALAPPDATA", ""), env.get("ProgramFiles", r"C:\Program Files")
        pf86 = env.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        j = lambda *a: "\\".join(a)  # noqa: E731 - Windows paths, also when tested elsewhere
        exe = _first([j(local, "Programs", "Microsoft VS Code", "Code.exe"), j(pf, "Microsoft VS Code", "Code.exe")], exists, glob)
        add("vscode", "Visual Studio Code", [exe] if exe else ([which("code")] if which("code") else None))
        exe = _first([j(pf, "JetBrains", "PyCharm*", "bin", "pycharm64.exe"), j(local, "Programs", "PyCharm*", "bin", "pycharm64.exe")], exists, glob)
        add("pycharm", "PyCharm", [exe] if exe else ([which("pycharm64")] if which("pycharm64") else None))
        exe = _first([j(local, "Programs", "cursor", "Cursor.exe")], exists, glob)
        add("cursor", "Cursor", [exe] if exe else None)
        exe = _first([j(pf, "Notepad++", "notepad++.exe"), j(pf86, "Notepad++", "notepad++.exe")], exists, glob)
        add("notepadpp", "Notepad++", [exe] if exe else None)
        exe = _first([j(pf, "Sublime Text", "sublime_text.exe"), j(pf, "Sublime Text 3", "sublime_text.exe")], exists, glob)
        add("sublime", "Sublime Text", [exe] if exe else None)
        add("idle", "IDLE (comes with Python)", _idle(platform, exists))
        add("notepad", "Notepad", ["notepad.exe"])
    elif platform == "darwin":
        for eid, name, app in (("vscode", "Visual Studio Code", "/Applications/Visual Studio Code.app"),
                               ("pycharm", "PyCharm", "/Applications/PyCharm*.app"),
                               ("cursor", "Cursor", "/Applications/Cursor.app"),
                               ("sublime", "Sublime Text", "/Applications/Sublime Text.app"),
                               ("bbedit", "BBEdit", "/Applications/BBEdit.app")):
            hit = _first([app], exists, glob)
            add(eid, name, ["open", "-a", hit] if hit else None)
        add("idle", "IDLE (comes with Python)", _idle(platform, exists))
        add("textedit", "TextEdit", ["open", "-e"])
    else:
        for eid, name, cmds in (("vscode", "Visual Studio Code", ("code", "codium")), ("pycharm", "PyCharm", ("pycharm", "pycharm-community", "charm")),
                                ("cursor", "Cursor", ("cursor",)), ("sublime", "Sublime Text", ("subl",)),
                                ("kate", "Kate", ("kate",)), ("gedit", "Text Editor", ("gnome-text-editor", "gedit", "xed", "mousepad")),
                                ("idle", "IDLE (comes with Python)", ("idle3", "idle"))):
            hit = next((which(c) for c in cmds if which(c)), None)
            add(eid, name, [hit] if hit else None)
        if which("xdg-open"):
            add("system", "The computer's default", [which("xdg-open")])
    return found


def _idle(platform: str, exists: Callable[[str], bool]) -> list[str] | None:
    try:
        import idlelib  # noqa: F401
        import tkinter  # noqa: F401
    except ImportError:
        return None
    python = sys.executable
    if platform.startswith("win"):
        w = str(Path(python).with_name("pythonw.exe"))
        python = w if exists(w) else python
    return [python, "-m", "idlelib"]


def choose(editors: list[dict[str, Any]], preferred: str = "") -> dict[str, Any] | None:
    return next((e for e in editors if e["id"] == preferred), editors[0] if editors else None)


def open_in(editor: dict[str, Any], path: Path, popen=subprocess.Popen) -> None:
    command = [*editor["command"], str(path)]
    kwargs: dict[str, Any] = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if sys.platform.startswith("win"):
        kwargs["creationflags"] = NO_WINDOW if command[0].lower().endswith((".cmd", ".bat")) else DETACHED
    else:
        kwargs["start_new_session"] = True
    popen(command, **kwargs)

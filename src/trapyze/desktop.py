"""traPYze in its own window, with an icon in the tray (by the clock).

Two optional open-source packages do the work: pywebview (the window, using
the computer's own web engine: WebView2 on Windows) and pystray (the tray
icon). Install them with the "desktop" extra:

    uv tool install --reinstall ".[desktop]"

Without them traPYze opens in the browser, exactly as before.

Closing the window keeps traPYze running in the tray, so tools carry on and a
notification says when one finishes. "Quit traPYze" in the tray menu ends it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

from .home import Home

STATIC = Path(__file__).parent / "web" / "static"


def load_webview() -> ModuleType | None:
    try:
        import webview  # type: ignore[import-not-found]
    except Exception:  # missing, or its engine can't load (for example no pythonnet)
        return None
    return webview


def load_pystray() -> ModuleType | None:
    try:
        import pystray  # type: ignore[import-not-found]
        from PIL import Image  # noqa: F401  (pystray needs Pillow for the picture)
    except Exception:
        return None
    return pystray


def available() -> dict[str, Any]:
    """What this computer can do, for the Look and feel screen."""
    window, tray = load_webview() is not None, load_pystray() is not None
    return {"window": window, "tray": tray, "shortcut": sys.platform.startswith(("win", "linux")),
            "install": 'uv tool install --reinstall ".[desktop]"'}


# One traPYze at a time ------------------------------------------------------
def _instance_file(home: Home) -> Path:
    return home.internal / "app.json"


def find_running(home: Home) -> dict[str, Any] | None:
    """The traPYze that's already open for this home, if any (and it answers).

    Includes its version and how many runs it has going, when it says so."""
    try:
        info = json.loads(_instance_file(home).read_text(encoding="utf-8"))
        url = f"http://127.0.0.1:{int(info['port'])}/api/ping?t={info['token']}"
        with urllib.request.urlopen(url, timeout=2) as answer:
            if answer.status == 200:
                try:
                    said = json.loads(answer.read())
                    info.update({k: said[k] for k in ("version", "busy", "window") if k in said})
                except ValueError:
                    pass
                return info
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def ask_to_quit(info: dict[str, Any]) -> bool:
    """Ask an older running traPYze to close, so this (newer) one can take over."""
    req = urllib.request.Request(f"http://127.0.0.1:{int(info['port'])}/api/desktop/quit", data=b"{}", method="POST",
                                 headers={"Content-Type": "application/json", "X-Trapyze-Token": info["token"]})
    try:
        with urllib.request.urlopen(req, timeout=3) as answer:
            return answer.status == 200
    except (OSError, ValueError):
        return False


def _tell(info: dict[str, Any], message: str) -> None:
    """Show a message in the running traPYze's window (newer versions can)."""
    req = urllib.request.Request(f"http://127.0.0.1:{int(info['port'])}/api/desktop/notice", data=json.dumps({"text": message}).encode(),
                                 method="POST", headers={"Content-Type": "application/json", "X-Trapyze-Token": info["token"]})
    try:
        urllib.request.urlopen(req, timeout=3).close()
    except (OSError, ValueError):
        pass


def ask_to_show(info: dict[str, Any]) -> bool:
    """Ask the running traPYze to bring its window forward. False if it has none."""
    req = urllib.request.Request(f"http://127.0.0.1:{int(info['port'])}/api/desktop/show", data=b"{}", method="POST",
                                 headers={"Content-Type": "application/json", "X-Trapyze-Token": info["token"]})
    try:
        with urllib.request.urlopen(req, timeout=3) as answer:
            return bool(json.loads(answer.read()).get("shown"))
    except (OSError, ValueError):
        return False


class Desktop:
    """Runs the server, the window and the tray icon together, and tidies up after."""

    def __init__(self, home: Home, mode: str = "auto", port: int = 0, webview: ModuleType | None = None,
                 pystray: ModuleType | None = None, open_browser: Callable[[str], Any] = webbrowser.open,
                 console: bool = True, auto_open: bool = True):
        from .web.server import make_server

        self.home = home
        self.webview = webview
        self.pystray = pystray
        self.open_browser = open_browser
        self.console = console
        self.auto_open = auto_open
        self.server, self.app = make_server(home, port)
        self.app.desktop = self
        self.app.quit_hook = self.quit
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/?t={self.app.token}"
        prefer = self.app.looks.get().get("window", "app")
        if mode == "auto":
            mode = "window" if prefer == "app" and webview is not None else "browser"
        if mode == "window" and webview is None:
            mode = "browser"
        self.mode = mode
        self.window: Any = None
        self.icon: Any = None
        self.visible = False
        self.quitting = False
        self.told_about_tray = False
        self._done = threading.Event()

    # Life cycle -----------------------------------------------------------
    def run(self) -> int:
        _instance_file(self.home).write_text(json.dumps({"pid": os.getpid(), "port": self.server.server_address[1],
                                                         "token": self.app.token}), encoding="utf-8")
        threading.Thread(target=self.server.serve_forever, name="trapyze-server", daemon=True).start()
        self.app.start_planner()
        try:
            if self.mode == "window":
                self._run_window()
            else:
                self._run_browser()
        finally:
            self._cleanup()
        return 0

    def _run_window(self) -> None:
        dark = self._dark()
        self.window = self.webview.create_window(
            "traPYze", self.url, width=1280, height=860, min_size=(820, 600),
            background_color="#0F131A" if dark else "#F4F5F7", text_select=True)
        self.window.events.closing += self._on_closing
        self.window.events.shown += lambda *a: setattr(self, "visible", True)
        self.visible = True
        storage = self.home.internal / "window"
        storage.mkdir(parents=True, exist_ok=True)
        if self.pystray is not None and sys.platform != "darwin":
            threading.Thread(target=self._run_tray, name="trapyze-tray", daemon=True).start()
            self.webview.start(private_mode=False, storage_path=str(storage))
        elif self.pystray is not None:  # macOS: the tray shares the window's main loop
            self.icon = self._make_icon()
            self.icon.run_detached()
            self.webview.start(private_mode=False, storage_path=str(storage))
        else:
            self.webview.start(private_mode=False, storage_path=str(storage))

    def _run_browser(self) -> None:
        if self.console:
            if self.auto_open:
                print("traPYze is open in your browser.")
                print(f"If it didn't open, paste this address into it:\n  {self.url}")
            else:
                print(f"traPYze is running. Open this address in your browser:\n  {self.url}")
            if self.pystray is not None and sys.platform != "darwin":
                print("traPYze also has an icon by the clock; use it, or Ctrl+C here, to close traPYze.")
            else:
                print("Keep this window open while you use traPYze. Press Ctrl+C here to close it.")
        if self.auto_open:
            threading.Timer(0.4, lambda: self.open_browser(self.url)).start()
        if self.pystray is not None and (sys.platform != "darwin" or not self.console):
            if self.console:
                threading.Thread(target=self._run_tray, name="trapyze-tray", daemon=True).start()
            else:
                self._run_tray()  # nothing else to keep running: the tray is the app
                return
        try:
            while not self._done.wait(0.3):  # short waits so Ctrl+C works on Windows too
                pass
        except KeyboardInterrupt:
            if self.console:
                print("Closing traPYze…")

    def _cleanup(self) -> None:
        self.quitting = True
        for live in list(self.app.runs.values()):
            if live.run.running:
                live.run.cancel()
        for chain in list(self.app.chain_runs.values()):
            if chain.status == "running":
                chain.stop()
        if self.icon is not None:
            try:
                self.icon.stop()
            except Exception:
                pass
        self.server.shutdown()
        self.server.server_close()
        try:
            info = json.loads(_instance_file(self.home).read_text(encoding="utf-8"))
            if info.get("pid") == os.getpid() and info.get("token") == self.app.token:
                _instance_file(self.home).unlink()  # only our own note, not a newer traPYze's
        except (OSError, ValueError):
            pass

    def quit(self) -> None:
        """From the tray: stop everything and close."""
        self.quitting = True
        self._done.set()
        if self.window is not None:
            self.window.destroy()  # webview.start() returns; run() tidies up
        elif self.icon is not None:
            self.icon.stop()

    def _dark(self) -> bool:
        theme = self.app.looks.get().get("theme", "auto")
        return theme == "dark"

    # The window -------------------------------------------------------------
    def _on_closing(self, *args: Any) -> bool:
        if self.quitting:
            return True
        if self.icon is not None:  # keep running in the tray
            threading.Thread(target=self.hide, daemon=True).start()
            if not self.told_about_tray:
                self.told_about_tray = True
                self.notify("traPYze is still here",
                            "Tools keep running. Click the icon by the clock to open traPYze, or right-click it to quit.")
            return False
        busy = self.busy()
        if busy and not self.window.create_confirmation_dialog(
                "Close traPYze?", f"{busy} still running. Closing traPYze stops {'it' if busy.startswith('1 ') else 'them'}."):
            return False
        self.quitting = True
        return True

    def show(self) -> bool:
        """Bring the window forward (from the tray, or when traPYze is started a second time)."""
        if self.window is None:
            self.open_browser(self.url)
            return False
        self.window.show()
        try:
            self.window.restore()
        except Exception:
            pass
        self.visible = True
        return True

    def hide(self) -> None:
        if self.window is not None:
            self.window.hide()
        self.visible = False

    # The tray -------------------------------------------------------------
    def busy(self) -> str:
        running = [live.run.tool.name for live in self.app.runs.values() if live.run.running]
        if not running:
            return ""
        return f"{running[0]} is" if len(running) == 1 else f"{len(running)} tools are"

    def _menu(self):
        item, menu = self.pystray.MenuItem, self.pystray.Menu

        def items():
            running = [live.run.tool.name for live in self.app.runs.values() if live.run.running]
            yield item("Open traPYze", lambda *a: self.show(), default=True)
            if running:
                yield menu.SEPARATOR
                for name in running[:8]:
                    yield item(f"Running: {name}", None, enabled=False)
            yield menu.SEPARATOR
            if self.window is not None:
                yield item("Open in the browser", lambda *a: self.open_browser(self.url))
            yield item("Open the outputs folder", lambda *a: self._open_folder(self.home.outputs))
            yield menu.SEPARATOR
            n = len(running)
            yield item("Quit traPYze" + (f" (stops {n} running tool{'s' if n != 1 else ''})" if n else ""),
                       lambda *a: self.quit())
        return menu(items)

    def _make_icon(self):
        from PIL import Image

        with Image.open(STATIC / "icon.png") as source:
            picture = source.copy()
        return self.pystray.Icon("traPYze", picture, "traPYze", menu=self._menu())

    def _run_tray(self) -> None:
        self.icon = self._make_icon()
        self.icon.run()

    def refresh(self) -> None:
        """Something started or finished: update the tray's menu and hover text."""
        if self.icon is None:
            return
        busy = self.busy()
        try:
            self.icon.title = f"traPYze: {busy} running" if busy else "traPYze"
            self.icon.update_menu()
        except Exception:
            pass

    def notify(self, title: str, message: str) -> None:
        if self.icon is None or not self.app.looks.get().get("notify", True):
            return
        try:
            if getattr(self.icon, "HAS_NOTIFICATION", True):
                self.icon.notify(message, title)
        except Exception:
            pass

    def finished(self, title: str, message: str) -> None:
        """A run or chain ended. Tell the person if they can't see the window."""
        self.refresh()
        if self.mode == "browser" or not self.visible:
            self.notify(title, message)

    @staticmethod
    def _open_folder(path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        if sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# Shortcuts ------------------------------------------------------------------
def launcher() -> tuple[str, list[str]]:
    """What a shortcut should start: traPYze without a console window."""
    exe = Path(sys.executable)
    quiet = exe.with_name("pythonw.exe")
    return (str(quiet if quiet.exists() else exe), ["-m", "trapyze.desktop"])


def make_shortcuts(home: Home) -> list[str]:
    """A traPYze shortcut on the desktop and in the Start menu (Windows) or the app list (Linux)."""
    target, args = launcher()
    if sys.platform.startswith("win"):
        script = (
            "$ws = New-Object -ComObject WScript.Shell; $made = @();"
            "foreach ($place in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))) {"
            " $p = Join-Path $place 'traPYze.lnk'; $s = $ws.CreateShortcut($p);"
            " $s.TargetPath = $env:TZ_TARGET; $s.Arguments = $env:TZ_ARGS; $s.WorkingDirectory = $env:TZ_HOME;"
            " $s.IconLocation = $env:TZ_ICON; $s.Description = 'traPYze: run your Python tools'; $s.Save(); $made += $p };"
            "$made -join [char]10"
        )
        env = {**os.environ, "TZ_TARGET": target, "TZ_ARGS": " ".join(args), "TZ_HOME": str(home.root),
               "TZ_ICON": str(STATIC / "icon.ico")}
        done = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], env=env,
                              capture_output=True, text=True, timeout=60,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if done.returncode != 0:
            raise OSError(done.stderr.strip() or "Windows wouldn't make the shortcut.")
        return [line for line in done.stdout.splitlines() if line.strip()]
    if sys.platform.startswith("linux"):
        entry = (
            "[Desktop Entry]\nType=Application\nName=traPYze\nComment=Run your Python tools\n"
            f"Exec=\"{target}\" {' '.join(args)}\nIcon={STATIC / 'icon.png'}\nTerminal=false\nCategories=Utility;Development;\n"
        )
        made = []
        apps = Path.home() / ".local" / "share" / "applications"
        apps.mkdir(parents=True, exist_ok=True)
        for folder in (apps, Path.home() / "Desktop"):
            if folder.is_dir():
                p = folder / "trapyze.desktop"
                p.write_text(entry, encoding="utf-8")
                p.chmod(0o755)
                made.append(str(p))
        return made
    if sys.platform == "darwin":
        return [str(make_mac_app(Path.home() / "Applications", target, args))]
    raise OSError("Shortcuts aren't supported on this system. Start traPYze with: trapyze open")


def make_mac_app(folder: Path, target: str, args: list[str], run=subprocess.run) -> Path:
    """~/Applications/traPYze.app: a tiny app bundle that starts traPYze, with its icon, for the Dock and Launchpad."""
    app = folder / "traPYze.app"
    macos, res = app / "Contents" / "MacOS", app / "Contents" / "Resources"
    macos.mkdir(parents=True, exist_ok=True)
    res.mkdir(parents=True, exist_ok=True)
    quoted = " ".join("'" + a.replace("'", "'\\''") + "'" for a in [target, *args])
    starter = macos / "traPYze"
    starter.write_text(f"#!/bin/sh\nexec {quoted}\n", encoding="utf-8")
    starter.chmod(0o755)
    (app / "Contents" / "Info.plist").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0"><dict>\n'
        '<key>CFBundleName</key><string>traPYze</string>\n'
        '<key>CFBundleDisplayName</key><string>traPYze</string>\n'
        '<key>CFBundleIdentifier</key><string>org.trapyze.app</string>\n'
        '<key>CFBundleExecutable</key><string>traPYze</string>\n'
        '<key>CFBundleIconFile</key><string>traPYze</string>\n'
        '<key>CFBundlePackageType</key><string>APPL</string>\n'
        '<key>LSUIElement</key><false/>\n'
        '</dict></plist>\n', encoding="utf-8")
    try:  # sips comes with macOS and turns the PNG into the icon format the Dock wants
        run(["sips", "-s", "format", "icns", str(STATIC / "icon.png"), "--out", str(res / "traPYze.icns")],
            capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        pass
    return app


def main(argv: list[str] | None = None) -> int:
    """Started from a shortcut: no console. Output goes to a log file instead."""
    home = Home(Path(os.environ["TRAPYZE_HOME"]) if os.environ.get("TRAPYZE_HOME") else None)
    if not home.exists():
        home.init(with_examples=True)
    else:
        home.init(with_examples=False)
    console = sys.stdout is not None and sys.stdout.isatty() if sys.stdout else False
    if not console:
        log = open(home.internal / "app.log", "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = log
        print(f"--- traPYze started {time.strftime('%Y-%m-%d %H:%M:%S')}")
    return open_app(home, "auto", console=console)


def open_app(home: Home, mode: str = "auto", port: int = 0, console: bool = True, open_browser: bool = True) -> int:
    """`trapyze open` and the shortcut both come here."""
    from . import __version__

    running = find_running(home)
    if running and running.get("version") != __version__:
        # An older traPYze is still open (for example in the tray, from before an update).
        if not running.get("busy") and ask_to_quit(running):
            for _ in range(60):  # it closes within a few seconds
                time.sleep(0.25)
                if find_running(home) is None:
                    break
            running = find_running(home)
            if running is None and console:
                print("Closed the older traPYze that was still open; starting this one.")
        else:
            older = running.get("version") or "an older version"
            message = (f"traPYze {older} is still open{' with tools running' if running.get('busy') else ''}. "
                       f"Quit it from the icon by the clock (right-click, Quit traPYze), then open traPYze again "
                       f"to use version {__version__}.")
            print(message)  # in the terminal, or app.log when started from the shortcut
            _tell(running, message)
    if running:
        if not ask_to_show(running) and open_browser:
            webbrowser.open(f"http://127.0.0.1:{running['port']}/?t={running['token']}")
        if console:
            print("traPYze was already open; it's in front now.")
        return 0
    webview = load_webview() if mode in ("auto", "window") else None
    if mode == "window" and webview is None and console:
        print("The own window needs the desktop add-on. Opening in the browser instead. To add it:")
        print(f"  {available()['install']}")
    desktop = Desktop(home, mode, port, webview=webview, pystray=load_pystray(), console=console, auto_open=open_browser)
    return desktop.run()


if __name__ == "__main__":
    raise SystemExit(main())

"""Phase 5b: the own window and the tray icon, with stand-ins for pywebview and pystray."""

import json
import os
import shutil
import sys
import tempfile
import threading
import time
import types
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trapyze import Home  # noqa: E402
from trapyze import desktop as dk  # noqa: E402


class Hooks(list):
    def __iadd__(self, fn):
        self.append(fn)
        return self


class FakeWindow:
    def __init__(self, title, url, **kw):
        self.title, self.url, self.kw = title, url, kw
        self.events = types.SimpleNamespace(closing=Hooks(), shown=Hooks())
        self.hidden = False
        self.shows = 0
        self.closed = threading.Event()
        self.answer = True
        self.asked = []

    def show(self):
        self.hidden = False
        self.shows += 1

    def restore(self):
        pass

    def hide(self):
        self.hidden = True

    def create_confirmation_dialog(self, title, message):
        self.asked.append(message)
        return self.answer

    def click_close(self):
        """What happens when the person clicks the window's ×."""
        if all(h() is not False for h in self.events.closing):
            self.closed.set()

    def destroy(self):
        self.click_close()


def fake_webview():
    mod = types.SimpleNamespace(windows=[])

    def create_window(title, url, **kw):
        w = FakeWindow(title, url, **kw)
        mod.windows.append(w)
        return w

    def start(**kw):
        mod.start_kw = kw
        mod.windows[0].closed.wait(30)
    mod.create_window, mod.start = create_window, start
    return mod


def fake_pystray():
    mod = types.SimpleNamespace(icons=[])

    class MenuItem:
        def __init__(self, text, action, default=False, enabled=True, **kw):
            self.text, self.action, self.default, self.enabled = text, action, default, enabled

    class Menu:
        SEPARATOR = MenuItem("----", None)

        def __init__(self, items):
            self.items = items

        def texts(self):
            return [i.text for i in self.items()]

        def click(self, text):
            next(i for i in self.items() if i.text.startswith(text)).action(None, None)

    class Icon:
        HAS_NOTIFICATION = True

        def __init__(self, name, image, title, menu):
            self.name, self.title, self.menu = name, title, menu
            self.notes, self.updates = [], 0
            self._stop = threading.Event()
            mod.icons.append(self)

        def run(self):
            self._stop.wait(30)

        def run_detached(self):
            pass

        def stop(self):
            self._stop.set()

        def notify(self, message, title=None):
            self.notes.append((title, message))

        def update_menu(self):
            self.updates += 1
    mod.Menu, mod.MenuItem, mod.Icon = Menu, MenuItem, Icon
    return mod


def wait_for(cond, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


class DesktopTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="tz-desk-"))
        self.home = Home(self.dir)
        self.home.init(with_examples=False)
        (self.home.scripts / "quick.py").write_text('# /// script\n# [tool.trapyze]\n# name = "Quick"\n# ///\nimport time; time.sleep(0.6); print("ok")\n')
        (self.home.scripts / "slow.py").write_text('# /// script\n# [tool.trapyze]\n# name = "Slow"\n# ///\nimport time; time.sleep(30)\n')

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def start(self, desktop):
        result = {}
        t = threading.Thread(target=lambda: result.setdefault("code", desktop.run()), daemon=True)
        t.start()
        self.assertTrue(wait_for(lambda: dk.find_running(self.home) is not None))
        return t, result

    def test_window_tray_notifications_and_quit(self):
        wv, tray = fake_webview(), fake_pystray()
        d = dk.Desktop(self.home, "auto", webview=wv, pystray=tray, open_browser=lambda u: None)
        self.assertEqual(d.mode, "window")
        t, result = self.start(d)
        self.assertTrue(wait_for(lambda: tray.icons))
        win, icon = wv.windows[0], tray.icons[0]
        self.assertTrue(win.url.startswith("http://127.0.0.1:") and "?t=" in win.url)
        self.assertEqual(win.kw["min_size"], (820, 600))
        self.assertTrue(Path(wv.start_kw["storage_path"]).is_dir())
        self.assertEqual(icon.menu.texts()[0], "Open traPYze")
        # A second start brings this window forward instead of opening another traPYze.
        self.assertTrue(dk.ask_to_show(dk.find_running(self.home)))
        self.assertEqual(win.shows, 1)
        # Closing the window hides it; tools keep running.
        live = d.app.start("quick", {})
        self.assertIn("Running: Quick", icon.menu.texts())
        self.assertTrue(any(x.startswith("Quit traPYze (stops 1 running tool)") for x in icon.menu.texts()))
        win.click_close()
        self.assertFalse(win.closed.is_set())
        self.assertTrue(wait_for(lambda: win.hidden))
        self.assertEqual(icon.notes[0][0], "traPYze is still here")
        self.assertTrue(wait_for(lambda: not live.run.running))
        self.assertTrue(wait_for(lambda: ("Bingo!", "Quick is done.") in icon.notes))
        self.assertGreater(icon.updates, 0)
        # Visible window: no notification needed.
        icon.menu.click("Open traPYze")
        self.assertFalse(win.hidden)
        live = d.app.start("quick", {})
        self.assertTrue(wait_for(lambda: not live.run.running))
        time.sleep(0.2)
        self.assertEqual(sum(1 for n in icon.notes if n[0] == "Bingo!"), 1)
        # Quit from the tray stops what's running and closes everything.
        slow = d.app.start("slow", {})
        icon.menu.click("Quit traPYze")
        t.join(20)
        self.assertEqual(result.get("code"), 0)
        self.assertTrue(wait_for(lambda: not slow.run.running))
        self.assertEqual(slow.run.result.status, "stopped")
        self.assertFalse((self.home.internal / "app.json").exists())
        self.assertIsNone(dk.find_running(self.home))

    def test_no_tray_asks_before_stopping_tools(self):
        wv = fake_webview()
        d = dk.Desktop(self.home, "window", webview=wv, pystray=None, open_browser=lambda u: None)
        t, result = self.start(d)
        win = wv.windows[0]
        slow = d.app.start("slow", {})
        win.answer = False
        win.click_close()
        self.assertFalse(win.closed.is_set())
        self.assertIn("Slow is still running", win.asked[0])
        win.answer = True
        win.click_close()
        t.join(20)
        self.assertTrue(wait_for(lambda: not slow.run.running))

    def test_browser_mode_and_preferences(self):
        tray, opened = fake_pystray(), []
        d = dk.Desktop(self.home, "auto", webview=None, pystray=tray, open_browser=opened.append, console=False)
        self.assertEqual(d.mode, "browser")
        t, result = self.start(d)
        self.assertTrue(wait_for(lambda: opened))
        self.assertIn("?t=", opened[0])
        icon = tray.icons[0]
        self.assertNotIn("Open in the browser", icon.menu.texts())
        icon.menu.click("Open traPYze")  # no window: opens the browser again
        self.assertEqual(len(opened), 2)
        d.app.looks.update({"notify": False})
        live = d.app.start("quick", {})
        self.assertTrue(wait_for(lambda: not live.run.running))
        time.sleep(0.2)
        self.assertEqual(icon.notes, [])
        icon.menu.click("Quit traPYze")
        t.join(20)
        self.assertEqual(result.get("code"), 0)

    def test_window_preference_and_chain_notification(self):
        wv, tray = fake_webview(), fake_pystray()
        Desktop = dk.Desktop
        from trapyze.store import Looks
        Looks(self.home.internal).update({"window": "browser"})
        self.assertEqual(Desktop(self.home, "auto", webview=wv, pystray=tray).mode, "browser")
        Looks(self.home.internal).update({"window": "app"})
        d = Desktop(self.home, "auto", webview=wv, pystray=tray, open_browser=lambda u: None)
        t, result = self.start(d)
        self.assertTrue(wait_for(lambda: tray.icons))
        icon, win = tray.icons[-1], wv.windows[-1]
        win.click_close()
        self.assertTrue(wait_for(lambda: win.hidden))
        from trapyze.store import Chain, Step
        cr = d.app.start_chain(Chain("c1", "Twice", [Step("quick", "standard"), Step("quick", "standard")]), [{}, {}])
        self.assertEqual(cr.wait(30), "done")
        self.assertTrue(wait_for(lambda: ("Bingo!", "The chain “Twice” is done.") in icon.notes))
        self.assertFalse(any(n == ("Bingo!", "Quick is done.") for n in icon.notes))  # steps stay quiet
        info = json.loads(urllib.request.urlopen(win.url.replace("/?t=", "/api/tools?t=")).read())["desktop"]
        self.assertEqual(info["mode"], "window")
        icon.menu.click("Quit traPYze")
        t.join(20)

    def test_newer_version_replaces_an_idle_older_one(self):
        import trapyze.web.server as server_module
        wv1, tray1 = fake_webview(), fake_pystray()
        old = dk.Desktop(self.home, "window", webview=wv1, pystray=tray1, open_browser=lambda u: None)
        with mock.patch.object(server_module, "__version__", "0.6.0"):
            t_old, res_old = self.start(old)
            self.assertEqual(dk.find_running(self.home)["version"], "0.6.0")
            # Busy: the older one stays, and gets told why.
            slow = old.app.start("slow", {})
            self.assertTrue(wait_for(lambda: slow.run.running and dk.find_running(self.home).get("busy")))
            with mock.patch("builtins.print") as said:
                self.assertEqual(dk.open_app(self.home, "auto", console=True, open_browser=False), 0)
            self.assertIn("traPYze 0.6.0 is still open with tools running", said.call_args_list[0].args[0])
            self.assertIn("Quit it from the icon", old.app.notice)
            self.assertTrue(t_old.is_alive())
            slow.run.cancel()
            self.assertTrue(wait_for(lambda: not slow.run.running))
            # Idle: the older one closes and the new one starts.
            wv2, tray2 = fake_webview(), fake_pystray()
            result = {}
            with mock.patch.object(dk, "load_webview", return_value=wv2), mock.patch.object(dk, "load_pystray", return_value=tray2):
                t_new = threading.Thread(target=lambda: result.setdefault("code", dk.open_app(self.home, "auto", console=False)), daemon=True)
                t_new.start()
                t_old.join(20)
                self.assertFalse(t_old.is_alive())
        self.assertTrue(wait_for(lambda: tray2.icons and wv2.windows),
                        f"new one: returned {result!r}, alive {t_new.is_alive()}, sees {dk.find_running(self.home)!r}")
        self.assertTrue(wait_for(lambda: (dk.find_running(self.home) or {}).get("version") not in (None, "0.6.0")))
        tray2.icons[0].menu.click("Quit traPYze")
        t_new.join(20)
        self.assertEqual(result.get("code"), 0)

    @unittest.skipUnless(sys.platform.startswith("linux"), "Linux shortcut")
    def test_linux_shortcut(self):
        fake_home = self.dir / "userhome"
        (fake_home / "Desktop").mkdir(parents=True)
        with mock.patch.object(Path, "home", return_value=fake_home):
            made = dk.make_shortcuts(self.home)
        self.assertEqual(len(made), 2)
        text = Path(made[0]).read_text()
        self.assertIn("-m trapyze.desktop", text)
        self.assertIn("icon.png", text)
        self.assertTrue(os.access(made[0], os.X_OK))

    def test_icons_are_packaged(self):
        for name in ("icon.png", "icon.ico", "favicon.png"):
            self.assertGreater((dk.STATIC / name).stat().st_size, 1000)


if __name__ == "__main__":
    unittest.main()

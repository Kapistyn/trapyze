"""0.13: updating traPYze itself, the release helpers and the Mac app bundle."""
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from trapyze import __version__, updater  # noqa: E402
from trapyze.desktop import make_mac_app  # noqa: E402

try:
    import test_web as _web
except ImportError:  # run from the project root
    from tests import test_web as _web


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


RELEASE = {"tag_name": "v99.0.0", "html_url": "https://github.com/o/trapyze/releases/tag/v99.0.0", "body": "## New\n- things",
           "published_at": "2026-12-01T10:00:00Z",
           "assets": [{"name": "install.ps1", "browser_download_url": "https://x/install.ps1"},
                      {"name": "trapyze-99.0.0-py3-none-any.whl", "browser_download_url": "https://x/trapyze-99.0.0-py3-none-any.whl"}]}


def opener(payload):
    return lambda req, timeout=None: Resp(json.dumps(payload).encode())


class UpdaterTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="tz-up-"))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_versions(self):
        self.assertTrue(updater.newer("0.13.1", "0.13.0"))
        self.assertTrue(updater.newer("1.0.0", "0.99.9"))
        self.assertTrue(updater.newer("v0.14", "0.13.9"))
        self.assertFalse(updater.newer("1.0.0rc1", "1.0.0"))
        self.assertTrue(updater.newer("1.0.0", "1.0.0rc1"))
        self.assertFalse(updater.newer(__version__))

    def test_fetch_latest(self):
        latest = updater.fetch_latest(opener(RELEASE))
        self.assertEqual((latest["version"], latest["wheel"]), ("99.0.0", "https://x/trapyze-99.0.0-py3-none-any.whl"))

        def missing(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, 404, "x", {}, io.BytesIO(b""))
        with self.assertRaises(updater.UpdateError) as ctx:
            updater.fetch_latest(missing)
        self.assertIn("no release", str(ctx.exception))

    def test_check_and_due(self):
        u = updater.Updates(self.dir)
        with mock.patch.object(updater, "configured", return_value=False):
            self.assertFalse(u.due())
            with self.assertRaises(updater.UpdateError):
                u.check(opener(RELEASE))
        with mock.patch.object(updater, "configured", return_value=True), mock.patch.dict("os.environ", {"TRAPYZE_NO_UPDATE_CHECK": ""}):
            self.assertTrue(u.due(now=1_000_000))
            st = u.check(opener(RELEASE), now=1_000_000)
            self.assertTrue(st["available"])
            self.assertFalse(u.due(now=1_000_000 + 3600))
            self.assertTrue(u.due(now=1_000_000 + 25 * 3600))
            u.set_auto(False)
            self.assertFalse(u.due(now=1_000_000 + 99 * 3600))
            self.assertTrue(u.state()["available"])  # switching the daily look off keeps what's known

    def test_scripts(self):
        log = self.dir / "update.log"
        name, ps = updater.update_script(r"C:\Users\o'neil\.local\bin\uv.exe", "https://x/t.whl", 4242, log,
                                         [r"C:\venv\pythonw.exe", "-m", "trapyze.desktop"], platform="win32")
        self.assertEqual(name, "trapyze-update.ps1")
        self.assertIn("Get-Process -Id 4242", ps)
        self.assertIn("'C:\\Users\\o''neil\\.local\\bin\\uv.exe' tool install --reinstall --python 3.12 'trapyze[desktop] @ https://x/t.whl'", ps)
        self.assertIn("Start-Process -FilePath 'C:\\venv\\pythonw.exe' -ArgumentList '-m', 'trapyze.desktop'", ps)
        name, sh = updater.update_script("/home/a/.local/bin/uv", "https://x/t.whl", 4242, log, ["/v/python", "-m", "trapyze.desktop"], platform="linux")
        self.assertEqual(name, "trapyze-update.sh")
        self.assertIn("kill -0 4242", sh)
        if shutil.which("sh"):
            p = self.dir / "t.sh"
            p.write_text(sh)
            self.assertEqual(subprocess.run(["sh", "-n", str(p)]).returncode, 0)

    def test_start_update(self):
        calls = []
        with self.assertRaises(updater.UpdateError):
            updater.start_update(self.dir, None, "https://x/t.whl", ["a"], popen=lambda *a, **k: calls.append(a))
        with self.assertRaises(updater.UpdateError):
            updater.start_update(self.dir, "/uv", "http://insecure/t.whl", ["a"], popen=lambda *a, **k: calls.append(a))
        script = updater.start_update(self.dir, "/uv", "https://x/t.whl", ["/v/python", "-m", "trapyze.desktop"], pid=7,
                                      popen=lambda cmd, **k: calls.append((cmd, k)))
        self.assertTrue(script.exists())
        self.assertIn(str(script), calls[0][0])


class ReleaseToolTests(unittest.TestCase):
    def test_set_repo_and_notes(self):
        import release
        import set_repo
        tmp = Path(tempfile.mkdtemp(prefix="tz-rel-"))
        try:
            for name in set_repo.FILES:
                (tmp / name).parent.mkdir(parents=True, exist_ok=True)
                (tmp / name).write_text(f"see https://github.com/{set_repo.PLACEHOLDER}/releases\n", encoding="utf-8")
            for name in ("CHANGELOG.md", "pyproject.toml"):
                shutil.copy(ROOT / name, tmp / name)
            with mock.patch.object(set_repo, "ROOT", tmp):
                self.assertEqual(set_repo.main(["someone/trapyze"]), 0)
                self.assertEqual(set_repo.main(["not a repo"]), 2)
            for name in set_repo.FILES:
                self.assertEqual((tmp / name).read_text(encoding="utf-8"), "see https://github.com/someone/trapyze/releases\n", name)
            with mock.patch.object(release, "ROOT", tmp):
                self.assertEqual(release.main(["check", "v" + __version__]), 0)
                self.assertEqual(release.main(["check", "v0.0.1"]), 1)
                notes = release.notes(__version__, "someone/trapyze")
            self.assertIn("someone/trapyze/releases/latest/download/install.ps1", notes)
            self.assertNotIn("## [", notes)  # only this version's part
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_installers_point_where_traPYze_lives(self):
        from trapyze.project import REPO
        for name in ("installer/install.ps1", "installer/install.sh", "installer/windows/trapyze.iss", "README.md"):
            text = (ROOT / name).read_text(encoding="utf-8")
            self.assertIn(REPO, text, name)
            self.assertNotIn("YOUR-GITHUB-NAME", text, name)
        if shutil.which("sh"):
            for name in ("installer/install.sh", "installer/uninstall.sh"):
                self.assertEqual(subprocess.run(["sh", "-n", str(ROOT / name)]).returncode, 0, name)


class MacAppTests(unittest.TestCase):
    @unittest.skipIf(sys.platform.startswith("win"), "file permissions work differently on Windows")
    def test_bundle(self):
        tmp = Path(tempfile.mkdtemp(prefix="tz-mac-"))
        try:
            ran = []
            app = make_mac_app(tmp, "/Users/a b/venv/bin/python", ["-m", "trapyze.desktop"], run=lambda cmd, **k: ran.append(cmd))
            starter = app / "Contents" / "MacOS" / "traPYze"
            self.assertEqual(starter.read_text(), "#!/bin/sh\nexec '/Users/a b/venv/bin/python' '-m' 'trapyze.desktop'\n")
            self.assertTrue(starter.stat().st_mode & 0o111)
            self.assertIn("<string>org.trapyze.app</string>", (app / "Contents" / "Info.plist").read_text())
            self.assertEqual(ran[0][0], "sips")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class UpdateWebTests(_web.WebTests):
    def test_update_endpoints(self):
        status, data = self.request("GET", "/api/tools")
        self.assertEqual(data["update"]["current"], __version__)
        self.assertFalse(data["update"]["available"])
        with mock.patch.object(updater, "configured", return_value=False):
            status, data = self.request("POST", "/api/update/check", {})
        self.assertEqual(status, 400)  # a copy without a home online can't check
        with mock.patch.object(updater, "configured", return_value=True), \
             mock.patch.object(updater, "fetch_latest", return_value=updater.fetch_latest(opener(RELEASE))):
            status, data = self.request("POST", "/api/update/check", {})
            self.assertEqual(status, 200, data)
            self.assertEqual((data["available"], data["version"]), (True, "99.0.0"))
            self.assertIn("things", data["notes"])
            self.app.quit_hook = None
            status, data = self.request("POST", "/api/update/install", {})
            self.assertEqual(status, 400)  # can't close itself in this test
            quit_calls = []
            self.app.quit_hook = lambda: quit_calls.append(1)
            with mock.patch("trapyze.web.server.start_update") as started:
                status, data = self.request("POST", "/api/update/install", {})
            self.assertEqual((status, data.get("version")), (200, "99.0.0"))
            self.assertEqual(started.call_args[0][2], "https://x/trapyze-99.0.0-py3-none-any.whl")
            status, data = self.request("POST", "/api/update/auto", {"on": False})
            self.assertFalse(data["auto"])

    def test_notice_after_an_update(self):
        log = self.app.home.internal / "update.log"
        log.write_text("2026-12-01  Installing x\n2026-12-01  UPDATED\n")
        self.app._update_notice()
        self.assertIn(__version__, self.app.notice)
        self.assertFalse(log.exists())
        self.assertTrue(log.with_name("update-last.log").exists())


for name in [n for n in dir(_web.WebTests) if n.startswith("test_")]:
    setattr(UpdateWebTests, name, None)

if __name__ == "__main__":
    unittest.main()

"""0.11: editors, versions, the health check and new-tool templates."""
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trapyze import editors  # noqa: E402
from trapyze.health import add_package, check, summary  # noqa: E402
from trapyze.label import read_tool  # noqa: E402
from trapyze.layout import suggest  # noqa: E402
from trapyze.store import StoreError  # noqa: E402
from trapyze.templates import KINDS, make  # noqa: E402
from trapyze.versions import Versions  # noqa: E402

try:
    import test_web as _web
except ImportError:  # run from the project root
    from tests import test_web as _web

LABEL = '# /// script\n# dependencies = [{deps}]\n# [tool.trapyze]\n# name = "T"\n# description = "d"\n{extra}# ///\n'


class Temp(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="tz-suite-"))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def tool(self, body, deps="", extra=""):
        p = self.dir / "t.py"
        p.write_text(LABEL.format(deps=deps, extra=extra) + body, encoding="utf-8")
        return read_tool(p)


class HealthTests(Temp):
    def codes(self, t):
        return {f["code"]: f for f in check(t)}

    def test_healthy(self):
        t = self.tool("import pandas\nprint(pandas)\n", deps='"pandas>=2"')
        self.assertEqual(check(t), [])
        self.assertEqual(summary([])["level"], "good")

    def test_syntax_stops_there(self):
        found = check(self.tool("def x(:\n"))
        self.assertEqual([f["code"] for f in found], ["syntax"])
        self.assertEqual(summary(found)["level"], "bad")

    def test_missing_and_unused_packages(self):
        c = self.codes(self.tool("import yfinance\nfrom bs4 import BeautifulSoup\nimport os, json\n", deps='"requests", "openpyxl"'))
        self.assertEqual(c["missing-package"]["fix"]["package"], "yfinance")
        missing = [f for f in check(self.tool("from bs4 import X\n")) if f["code"] == "missing-package"]
        self.assertEqual(missing[0]["fix"]["package"], "beautifulsoup4")
        self.assertIn("unused-package", c)  # requests; openpyxl is used indirectly and not reported
        self.assertNotIn("openpyxl", c["unused-package"]["title"])

    def test_a_file_in_a_neighbouring_program_is_not_a_package(self):
        scripts = self.dir / "scripts"
        (scripts / "market_db").mkdir(parents=True)
        (scripts / "market_db" / "market_core.py").write_text("x = 1\n")
        (scripts / "maps").mkdir()
        p = scripts / "maps" / "mood.py"
        p.write_text(LABEL.format(deps='"pandas"', extra="") + "import pandas\ndef f():\n    import market_core\n", encoding="utf-8")
        self.assertNotIn("missing-package", self.codes(read_tool(p)))

    def test_local_module_is_not_a_package(self):
        (self.dir / "helpers.py").write_text("x = 1\n")
        self.assertNotIn("missing-package", self.codes(self.tool("import helpers\n")))

    def test_secrets(self):
        c = self.codes(self.tool('API_KEY = "abcd1234efgh5678"\n'))
        self.assertEqual(c["secret"]["level"], "bad")
        self.assertNotIn("abcd1234", c["secret"]["title"] + c["secret"]["detail"])
        self.assertNotIn("secret", self.codes(self.tool('import os\nAPI_KEY = os.environ["X_KEY"]\npassword = "your_password"\n')))
        self.assertIn("secret", self.codes(self.tool('x = "ghp_' + "a" * 36 + '"\n')))
        self.assertIn("secret", self.codes(self.tool('FMP_KEY = "k3y9f8a7s6d5f4g3h2"\n')))
        self.assertNotIn("secret", self.codes(self.tool('sort_key = "market_value"\nKEY = "AAPL"\n')))

    def test_risky_and_paths(self):
        c = self.codes(self.tool('import os, shutil, subprocess\neval("1")\nos.system("dir")\nshutil.rmtree("x")\n'
                                 'subprocess.run("ls", shell=True)\nopen(r"C:\\Users\\alex\\prices.csv")\n'))
        for code in ("eval", "shell", "rmtree", "path"):
            self.assertIn(code, c)
        self.assertEqual(c["eval"]["line"], 8)  # counted in the whole file, label included

    def test_unused_setting(self):
        extra = '# [[tool.trapyze.settings]]\n# key = "days"\n# label = "Days"\n# type = "int"\n# default = 5\n'
        self.assertIn("unused-setting", self.codes(self.tool("print(1)\n", extra=extra)))
        self.assertNotIn("unused-setting", self.codes(self.tool("import trapyze_helper as tz\nprint(tz.settings()['days'])\n", extra=extra)))

    def test_add_package_keeps_the_rest(self):
        src = '# /// script\r\n# dependencies = [\r\n#   "pandas",\r\n# ]\r\n# [tool.trapyze]\r\n# name = "x"\r\n# ///\r\nimport pandas\r\n'
        new = add_package(src, "yfinance")
        self.assertIn('# dependencies = ["pandas", "yfinance"]\r\n', new)
        self.assertTrue(new.endswith("# name = \"x\"\r\n# ///\r\nimport pandas\r\n"))
        self.assertEqual(add_package(new, "YFinance"), new)
        with self.assertRaises(ValueError):
            add_package("print(1)\n", "x")
        with self.assertRaises(ValueError):
            add_package(src, 'x"; import os')


class VersionTests(Temp):
    def test_snapshot_diff_restore(self):
        v, p = Versions(self.dir / "internal"), self.dir / "t.py"
        p.write_text("a\nb\n")
        first = v.snapshot(p, "t", "First copy")
        self.assertIsNotNone(first)
        self.assertIsNone(v.snapshot(p, "t", "Again"))  # same content: no new copy
        p.write_text("a\nc\n")
        self.assertTrue(v.list(p, "t")["changed"])
        lines = v.diff(p, "t", first["id"])
        self.assertIn({"kind": "del", "text": "b"}, lines)
        self.assertIn({"kind": "add", "text": "c"}, lines)
        v.restore(p, "t", first["id"])
        self.assertEqual(p.read_text(), "a\nb\n")
        listing = v.list(p, "t")
        self.assertFalse(listing["changed"])
        self.assertEqual([x["reason"] for x in listing["versions"]][:2], ["Went back to an earlier version", "Before going back"])
        with self.assertRaises(StoreError):
            v.diff(p, "t", "../../etc")

    def test_keeps_at_most_forty(self):
        v, p = Versions(self.dir / "internal"), self.dir / "t.py"
        for i in range(45):
            p.write_text(f"v{i}\n")
            v.snapshot(p, "t", "x")
        self.assertEqual(v.count("t"), 40)
        self.assertEqual(len(list((self.dir / "internal" / "versions" / "t").glob("*.py"))), 40)


class TemplateTests(Temp):
    def test_every_template_is_a_healthy_tool_on_its_shelf(self):
        for kind in KINDS:
            p = make(self.dir, f'My "{kind}" tool', kind)
            t = read_tool(p)
            self.assertEqual(t.name, f'My "{kind}" tool')
            compile(p.read_text(), str(p), "exec")
            self.assertEqual(suggest(t), kind, kind)
            self.assertEqual([f for f in check(t) if f["level"] != "info"], [], kind)
        self.assertTrue((self.dir / "my_collect_tool_2.py").exists() is False)
        make(self.dir, 'My "collect" tool', "collect")
        self.assertTrue((self.dir / "my_collect_tool_2.py").exists())
        with self.assertRaises(ValueError):
            make(self.dir, "", "collect")


class EditorTests(unittest.TestCase):
    def test_windows_detection(self):
        files = {r"C:\Users\s\AppData\Local\Programs\Microsoft VS Code\Code.exe", r"C:\Program Files\Notepad++\notepad++.exe"}
        found = editors.available("win32", env={"LOCALAPPDATA": r"C:\Users\s\AppData\Local", "ProgramFiles": r"C:\Program Files"},
                                  which=lambda c: None, exists=lambda p: p in files,
                                  glob=lambda p: [r"C:\Program Files\JetBrains\PyCharm 2026.2\bin\pycharm64.exe"] if "JetBrains" in p else [])
        ids = [e["id"] for e in found]
        self.assertEqual(ids[:3], ["vscode", "pycharm", "notepadpp"])
        self.assertEqual(ids[-1], "notepad")
        self.assertEqual(editors.choose(found, "notepadpp")["name"], "Notepad++")
        self.assertEqual(editors.choose(found, "gone")["id"], "vscode")

    def test_linux_and_open(self):
        found = editors.available("linux", env={}, which=lambda c: f"/usr/bin/{c}" if c in ("codium", "xdg-open") else None)
        self.assertEqual([e["id"] for e in found], ["vscode", "system"])
        calls = []
        editors.open_in(found[0], Path("/x/t.py"), popen=lambda cmd, **kw: calls.append((cmd, kw)))
        self.assertEqual(calls[0][0], ["/usr/bin/codium", str(Path("/x/t.py"))])


class SuiteWebTests(_web.WebTests):
    def test_suite_endpoints(self):
        status, data = self.request("POST", "/api/new-tool", {"name": "Fetch AEX", "kind": "collect"})
        self.assertEqual(status, 200, data)
        tid = data["result"]["id"]
        tool = next(t for t in data["tools"] if t["id"] == tid)
        self.assertEqual((tool["kind"], tool["health"]["level"]), ("collect", "good"))
        self.assertIn(f"tool:{tid}", next(s for s in data["layout"]["shelves"] if s["id"] == "collect")["items"])
        self.assertEqual(tool["changes"], 1)

        path = Path(tool["path"])
        path.write_text(path.read_text().replace("import urllib.request", "import urllib.request\nimport yfinance"))
        time.sleep(0.01)
        status, data = self.request("GET", f"/api/health/{tid}")
        self.assertEqual(data["summary"]["level"], "bad")
        status, data = self.request("POST", "/api/health/fix", {"tool": tid, "action": "add-package", "package": "yfinance"})
        self.assertEqual(status, 200, data)
        self.assertIn('"yfinance"', path.read_text())

        status, data = self.request("GET", f"/api/versions/{tid}")
        self.assertGreaterEqual(len(data["versions"]), 2)
        oldest = data["versions"][-1]["id"]
        status, data = self.request("POST", "/api/versions/diff", {"tool": tid, "version": oldest})
        self.assertTrue(any(l["kind"] == "add" and "yfinance" in l["text"] for l in data["lines"]))
        status, data = self.request("POST", "/api/versions/restore", {"tool": tid, "version": oldest})
        self.assertEqual(status, 200)
        self.assertNotIn("yfinance", path.read_text())

        status, data = self.request("GET", "/api/editors")
        self.assertIn("editors", data)
        status, data = self.request("POST", "/api/new-tool", {"name": "", "kind": "collect"})
        self.assertEqual(status, 400)
        status, data = self.request("GET", "/api/health/nope")
        self.assertEqual(status, 404)


for name in [n for n in dir(_web.WebTests) if n.startswith("test_")]:
    setattr(SuiteWebTests, name, None)

if __name__ == "__main__":
    unittest.main()

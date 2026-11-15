"""Phase 7a: importing a folder (a program with several files) or a single script."""

import json
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from trapyze import Home  # noqa: E402
from trapyze.importer import ImportProblem, apply, find_data_uses, read_options, scan, PyInfo  # noqa: E402
from trapyze.runner import Run  # noqa: E402
import test_web  # noqa: E402

MAIN = '''"""Price database: index members and prices since 2006."""
from __future__ import annotations
import argparse, os, sqlite3
from pathlib import Path
from helpers import shout

BASE = Path(__file__).parent
DB = BASE / "price_db.sqlite"
XLSX = os.path.join(str(BASE), "index_members.xlsx")


def main():
    p = argparse.ArgumentParser(description="Build the price database")
    sub = p.add_subparsers(dest="command")
    b = sub.add_parser("build")
    b.add_argument("--start", default="2006-01-01", help="First date (default %(default)s)")
    b.add_argument("--force", action="store_true", help="Rebuild everything")
    u = sub.add_parser("update")
    u.add_argument("--days", type=int, default=5, help="Days to fetch")
    u.add_argument("--force", action="store_true", help="Rebuild everything")
    sub.add_parser("validate")
    args = p.parse_args()
    con = sqlite3.connect(DB)
    con.execute("CREATE TABLE IF NOT EXISTS runs (command TEXT)")
    con.execute("INSERT INTO runs VALUES (?)", (args.command,))
    con.commit()
    print(shout(f"{args.command} done, xlsx there: {Path(XLSX).exists()}"))


if __name__ == "__main__":
    main()
'''


def make_program(folder: Path) -> Path:
    prog = folder / "price_db"
    (prog / "fixes").mkdir(parents=True)
    (prog / ".venv" / "lib").mkdir(parents=True)
    (prog / "__pycache__").mkdir()
    (prog / "price_db.py").write_text(MAIN)
    (prog / "helpers.py").write_text("def shout(x):\n    return x.upper()\n")
    (prog / "fixes" / "hwm_from_aa.py").write_text(
        "import argparse\np = argparse.ArgumentParser()\np.add_argument('--dry-run', action='store_true')\n"
        "p.add_argument('--items', nargs='+')\nif __name__ == '__main__':\n    print(p.parse_args())\n")
    (prog / "requirements.txt").write_text("# for the build\npandas>=2\nyfinance\n-r other.txt\n")
    import sqlite3
    sqlite3.connect(prog / "price_db.sqlite").close()
    con = sqlite3.connect(prog / "price_db.sqlite")
    con.execute("CREATE TABLE prices (d TEXT)")
    con.commit()
    con.close()
    (prog / "index_members.xlsx").write_bytes(b"PK\x03\x04xlsx")
    for name in ("price_db.sqlite.bak_20261029", "validate.log", "run_daily.bat", ".venv/lib/x.py", "__pycache__/a.pyc"):
        (prog / name).write_text("x")
    (prog / "START_HERE.md").write_text("# Start here\n")
    (prog / "price.env").write_text("FMP_API_KEY=abc123\n")
    (prog / "price.env.example").write_text("FMP_API_KEY=\n")
    return prog


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="tz-imp-"))
        self.home = Home(self.dir / "home")
        self.home.init(with_examples=False)
        self.prog = make_program(self.dir / "projects")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_scan_sorts_everything(self):
        plan = scan(self.prog, self.home)
        kinds = {i["rel"]: i["kind"] for i in plan["items"]}
        self.assertEqual(kinds["price_db.py"], "program")
        self.assertEqual(kinds["fixes/hwm_from_aa.py"], "program")
        self.assertEqual(kinds["helpers.py"], "module")
        self.assertEqual(kinds["price_db.sqlite"], "data")
        self.assertEqual(kinds["price.env"], "env")
        self.assertEqual(kinds["price.env.example"], "doc")
        self.assertEqual(kinds["price_db.sqlite.bak_20261029"], "skip")
        self.assertEqual(kinds["validate.log"], "skip")
        self.assertEqual(kinds["requirements.txt"], "deps")
        self.assertFalse(next(i for i in plan["items"] if i["rel"] == "run_daily.bat")["include"])
        self.assertFalse(any(".venv" in r or "__pycache__" in r for r in kinds))
        main = next(p for p in plan["programs"] if p["rel"] == "price_db.py")
        self.assertEqual(main["id"], "price_db")
        self.assertEqual(main["dependencies"], ["pandas>=2", "yfinance"])
        self.assertEqual(main["label"]["description"], "Price database: index members and prices since 2006.")
        self.assertEqual(main["label"]["writes"], ["data/price_db.sqlite"])  # the spreadsheet is only read
        settings = {s["key"]: s for s in main["label"]["settings"]}
        self.assertEqual(settings["command"]["options"], ["build", "update", "validate"])
        self.assertEqual(settings["start"]["only_for"], {"command": ["build"]})
        self.assertEqual(settings["force"]["only_for"], {"command": ["build", "update"]})  # same option, two commands
        self.assertEqual((settings["days"]["type"], settings["days"]["default"]), ("int", 5))
        self.assertEqual(settings["start"]["help"], "First date (default 2006-01-01)")
        fix = next(p for p in plan["programs"] if p["rel"] == "fixes/hwm_from_aa.py")
        self.assertEqual(fix["id"], "price_db.fixes.hwm_from_aa")
        self.assertIn("--items", fix["notes"][0])
        self.assertEqual({c["data"] for c in plan["changes"]}, {"price_db.sqlite", "index_members.xlsx"})

    def test_import_and_run(self):
        # No extra packages here (no uv in the test machine); the real import keeps them.
        report = apply(self.prog, self.home, {"name": "Price database", "programs": {"price_db.py": {"dependencies": []}}})
        self.assertEqual(report["tools"], ["price_db"])
        self.assertEqual(report["hidden"], ["price_db.fixes.hwm_from_aa"])  # runs on its own, but the main doesn't use it
        self.assertEqual(sorted(report["data"]), ["index_members.xlsx", "price_db.sqlite"])
        self.assertEqual([Path(p).resolve() for p in report["env"]], [(self.prog / "price.env").resolve()])
        self.assertFalse((self.home.scripts / "price_db" / "price.env").exists())
        self.assertTrue((self.home.scripts / "price_db" / "helpers.py").exists())
        self.assertFalse((self.home.scripts / "price_db" / "validate.log").exists())
        self.assertEqual(self.home.programs()["price_db"]["name"], "Price database")
        self.assertEqual(self.home.programs()["price_db"]["readme"], "START_HERE.md")
        self.assertEqual((self.prog / "price_db.py").read_text(), MAIN)  # the original is untouched
        tools, problems = self.home.tools()
        self.assertEqual(problems, [])
        tool = next(t for t in tools if t.id == "price_db")
        self.assertEqual(tool.group, "price_db")
        # It really runs from its new place, finds its helper, and writes the shared database.
        result = Run(self.home, tool, {"command": "update", "days": 3}, engine=None).start().wait(60)
        self.assertEqual(result.status, "done", result.cause)
        import sqlite3
        con = sqlite3.connect(self.home.data / "price_db.sqlite")
        self.assertEqual(con.execute("SELECT command FROM runs").fetchall(), [("update",)])
        con.close()
        text = (self.home.scripts / "price_db" / "price_db.py").read_text()
        self.assertTrue(text.startswith("# /// script\n"))
        self.assertIn('DB = _tz_data("price_db.sqlite")', text)
        self.assertLess(text.index("from __future__"), text.index("def _tz_data"))

    def test_the_conductor_gets_the_tile(self):
        prog = self.dir / "MarketEvaluator"
        prog.mkdir()
        test_block = '\n\nif __name__ == "__main__":\n    print("self test")\n'
        (prog / "main.py").write_text(
            "import argparse, subprocess, sys\nfrom main_engine import Engine\n\n"
            "def dashboard():\n    subprocess.Popen([sys.executable, 'dashboard.py'])\n\n"
            "if __name__ == '__main__':\n    p = argparse.ArgumentParser()\n    p.add_argument('--mode', choices=['daily', 'live'], default='daily')\n"
            "    Engine().run(p.parse_args().mode)\n")
        (prog / "main_engine.py").write_text(
            "from data_collector import DataCollector\nfrom signal_engine import Signals\n\n"
            "class Engine:\n    def run(self, mode):\n        from email_sender import send\n        from report_charts import chart\n"
            "        send(chart(Signals(DataCollector())))\n")
        for name in ("data_collector", "signal_engine", "email_sender", "report_charts", "trend_indicator"):
            (prog / f"{name}.py").write_text(f"def {name}():\n    return 1\nDataCollector = Signals = send = chart = {name}" + test_block)
        (prog / "signal_engine.py").write_text("from trend_indicator import trend_indicator\nSignals = trend_indicator" + test_block)
        (prog / "dashboard.py").write_text("import http.server" + test_block)
        (prog / "run_daily_sentiment.py").write_text("from data_collector import DataCollector" + test_block)
        (prog / "test_spy.py").write_text("import main_engine" + test_block)
        plan = scan(prog, self.home)
        role = {p["rel"]: (p["role"], p["include"]) for p in plan["programs"]}
        self.assertEqual(role, {"main.py": ("main", True), "run_daily_sentiment.py": ("extra", False)})
        kinds = {i["rel"]: i["kind"] for i in plan["items"]}
        for helper in ("main_engine.py", "data_collector.py", "email_sender.py", "report_charts.py", "trend_indicator.py",
                       "dashboard.py", "test_spy.py"):
            self.assertEqual(kinds[helper], "module", helper)
        self.assertEqual(next(i for i in plan["items"] if i["rel"] == "email_sender.py")["why"], "Used by main.py")
        report = apply(prog, self.home, {})
        self.assertEqual((report["tools"], report["hidden"]), (["MarketEvaluator.main"], ["MarketEvaluator.run_daily_sentiment"]))
        tools = {t.id: t for t in self.home.tools()[0]}
        self.assertFalse(tools["MarketEvaluator.main"].hidden)
        self.assertTrue(tools["MarketEvaluator.run_daily_sentiment"].hidden)
        # One click gives it a tile (and takes it away again).
        self.home.set_hidden("MarketEvaluator", set(), {"MarketEvaluator.run_daily_sentiment"})
        self.assertFalse(self.home.find("MarketEvaluator.run_daily_sentiment").hidden)

    def test_tidy_up_a_program_imported_before(self):
        from trapyze.importer import tidy
        folder = self.home.scripts / "MarketEvaluator"
        folder.mkdir()
        label = lambda n: f'# /// script\n# [tool.trapyze]\n# name = "{n}"\n# ///\n'  # noqa: E731
        (folder / "main.py").write_text(label("Main") + "import engine\nimport email_sender\nif __name__ == '__main__':\n    engine.go()\n")
        (folder / "engine.py").write_text("import trend\ndef go():\n    pass\n")
        for n in ("email_sender", "trend", "analyze_stock"):
            (folder / f"{n}.py").write_text(label(n) + "if __name__ == '__main__':\n    print(1)\n")
        self.assertEqual(len([t for t in self.home.tools()[0] if not t.hidden]), 4)
        result = tidy(self.home, "MarketEvaluator")
        self.assertEqual((result["main"], result["main_file"]), ("MarketEvaluator.main", "main.py"))
        self.assertEqual(result["hidden"], ["MarketEvaluator.analyze_stock", "MarketEvaluator.email_sender", "MarketEvaluator.trend"])
        self.assertEqual([t.id for t in self.home.tools()[0] if not t.hidden], ["MarketEvaluator.main"])
        with self.assertRaises(ImportProblem):
            tidy(self.home, "nope")

    def test_keeps_data_already_there_and_the_hand_made_label(self):
        (self.home.data / "price_db.sqlite").write_bytes(b"mine")
        (self.home.scripts / "price_db.py").write_text(
            '# /// script\n# dependencies = ["lxml"]\n# [tool.trapyze]\n# name = "Price DB"\n# warning_codes = [2]\n# ///\nprint(1)\n')
        plan = scan(self.prog, self.home)
        main = next(p for p in plan["programs"] if p["id"] == "price_db")
        self.assertEqual((main["kept_label"], main["label"]["name"]), ("price_db.py", "Price DB"))
        self.assertIn("lxml", main["dependencies"])
        self.assertTrue(next(i for i in plan["items"] if i["rel"] == "price_db.sqlite")["keep_existing"])
        report = apply(self.prog, self.home, {})
        self.assertEqual(report["kept_data"], ["price_db.sqlite"])
        self.assertEqual((self.home.data / "price_db.sqlite").read_bytes(), b"mine")
        self.assertEqual(report["replaced"], ["scripts/price_db.py"])
        self.assertTrue(list((self.home.scripts / "_replaced").glob("price_db-*.py")))
        tools, problems = self.home.tools()
        self.assertEqual(problems, [])
        self.assertEqual(next(t for t in tools if t.id == "price_db").warning_codes, [2])
        # Importing again: the folder exists, so it asks.
        with self.assertRaises(ImportProblem):
            apply(self.prog, self.home, {})
        report = apply(self.prog, self.home, {"replace_folder": True})
        self.assertEqual(report["replaced"], ["scripts/price_db"])

    def test_single_script_and_plain_problems(self):
        one = self.dir / "quick_rank.py"
        one.write_text("import argparse\np = argparse.ArgumentParser()\np.add_argument('--top', type=int, default=10)\n"
                       "p.add_argument('--market', choices=['AEX', 'DAX'], default='AEX')\nprint(p.parse_args())\n")
        plan = scan(one, self.home)
        self.assertTrue(plan["single"])
        report = apply(one, self.home, {"programs": {"quick_rank.py": {"name": "Quick rank"}}})
        self.assertEqual(report["tools"], ["quick_rank"])
        tool = self.home.find("Quick rank")
        self.assertEqual([(s.key, s.type) for s in tool.settings], [("top", "int"), ("market", "choice")])
        for bad, words in ((self.dir / "nope", "Can't find"), (self.home.scripts, "traPYze's own folder")):
            with self.assertRaises(ImportProblem) as caught:
                scan(bad, self.home)
            self.assertIn(words, str(caught.exception))
        (self.dir / "empty").mkdir()
        with self.assertRaises(ImportProblem):
            scan(self.dir / "empty", self.home)

    def test_wsl_paths_links_and_unreadable_files(self):
        import subprocess
        from trapyze.importer import windows_path, wsl_distros
        # wsl.exe answers in UTF-16, with docker's own distro in the list.
        said = "Ubuntu\r\ndocker-desktop\r\nDebian\r\n".encode("utf-16-le")
        run = lambda cmd: subprocess.CompletedProcess(cmd, 0, said, b"")  # noqa: E731
        everything = lambda p: True  # noqa: E731
        self.assertEqual(wsl_distros("win32", run, everything), ["Ubuntu", "Debian"])
        self.assertEqual(wsl_distros("linux", run), [])
        # wsl.exe missing: try the usual names.
        def broken(cmd):
            raise OSError("no wsl.exe")
        self.assertEqual(wsl_distros("win32", broken, lambda p: p.endswith("\\Ubuntu-24.04")), ["Ubuntu-24.04"])
        self.assertEqual(windows_path("/home/alex/price_db", "win32", ["Ubuntu"], everything),
                         "\\\\wsl.localhost\\Ubuntu\\home\\alex\\price_db")
        only_debian = lambda p: "Debian" in p  # noqa: E731
        self.assertEqual(windows_path("/srv/x", "win32", ["Ubuntu", "Debian"], only_debian), "\\\\wsl.localhost\\Debian\\srv\\x")
        self.assertEqual(windows_path("/mnt/c/Users/alex/x", "win32", []), "C:\\Users\\alex\\x")
        self.assertEqual(windows_path("/home/alex/x", "linux"), "/home/alex/x")
        self.assertEqual(windows_path("C:\\x", "win32", []), "C:\\x")
        with self.assertRaises(ImportProblem):
            windows_path("/home/x", "win32", [])
        # A .venv full of Linux links (one looping, one broken) is never entered; links elsewhere are skipped.
        venv = self.prog / ".venv"
        (venv / "lib64").unlink(missing_ok=True) if (venv / "lib64").is_symlink() else None
        (venv / "lib64").symlink_to(venv)  # a loop
        (self.prog / "broken_link.csv").symlink_to(self.prog / "nowhere.csv")
        (self.prog / "data_link").symlink_to(self.prog)
        real_stat = Path.stat
        def flaky(path, *a, **kw):
            if path.name == "START_HERE.md":
                raise PermissionError(13, "The file cannot be accessed by the system", str(path))
            return real_stat(path, *a, **kw)
        from unittest import mock
        with mock.patch.object(Path, "stat", flaky):
            plan = scan(f'  "{self.prog}"  ', self.home)
        rels = {i["rel"] for i in plan["items"]}
        self.assertFalse(any(r.startswith((".venv", "data_link")) for r in rels))
        self.assertNotIn("broken_link.csv", rels)
        self.assertNotIn("START_HERE.md", rels)
        self.assertTrue(any("couldn't read 1 file" in n and "START_HERE.md" in n for n in plan["notes"]))
        self.assertIn("price_db.py", rels)

    def test_path_changes_only_where_safe(self):
        info = PyInfo("x.py", 'import os\nA = "prices.csv"\nB = os.path.join(D, "sub", "prices.csv")\nC = f"{D}/prices.csv"\n')
        found = find_data_uses(info, {"prices.csv"})
        self.assertEqual([c["after"] for c in found], ['_tz_data("prices.csv")'] * 2)
        self.assertEqual(found[1]["before"], 'os.path.join(D, "sub", "prices.csv")')


class ImportWebTests(unittest.TestCase):
    setUp = test_web.WebTests.setUp
    tearDown = test_web.WebTests.tearDown
    request = test_web.WebTests.request

    def test_wizard_calls(self):
        prog = make_program(Path(tempfile.mkdtemp(prefix="tz-impw-")))
        status, plan = self.request("POST", "/api/import/scan", {"path": f'"{prog}"'})
        self.assertEqual(status, 200, plan)
        self.assertEqual(plan["folder"], "price_db")
        status, data = self.request("POST", "/api/import/scan", {"path": "/no/such/folder"})
        self.assertEqual(status, 400)
        status, data = self.request("POST", "/api/import/apply", {"path": str(prog), "choices": {
            "name": "Prices", "files": {"index_members.xlsx": {"include": True, "place": "program"}},
            "changes": {c["id"]: False for c in plan["changes"] if c["data"] == "price_db.sqlite"}}})
        self.assertEqual(status, 200, data)
        self.assertEqual(data["programs"]["price_db"]["name"], "Prices")
        self.assertTrue((self.home.scripts / "price_db" / "index_members.xlsx").exists())
        text = (self.home.scripts / "price_db" / "price_db.py").read_text()
        self.assertIn('DB = BASE / "price_db.sqlite"', text)  # that change was turned off
        self.assertEqual({t["group"] for t in data["tools"] if t["id"].startswith("price_db")}, {"price_db"})
        status, data = self.request("POST", "/api/programs/visibility", {"tool": "price_db.fixes.hwm_from_aa", "hidden": False})
        self.assertEqual(status, 200, data)
        self.assertFalse(next(t for t in data["tools"] if t["id"] == "price_db.fixes.hwm_from_aa")["hidden"])
        status, data = self.request("POST", "/api/programs/tidy", {"folder": "price_db"})
        self.assertEqual(data["result"]["hidden"], ["price_db.fixes.hwm_from_aa"])
        shutil.rmtree(prog.parent, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

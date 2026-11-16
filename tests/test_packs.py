"""The packs that come with traPYze: every tool is healthy, offline, and really runs on sample data."""
import os
import shutil
import sqlite3
import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trapyze import Home  # noqa: E402
from trapyze.health import check  # noqa: E402
from trapyze.packs import PACKS, PackProblem, install, overview  # noqa: E402
from trapyze.review import wants  # noqa: E402
from trapyze.runner import run_tool  # noqa: E402

try:
    import test_web as _web
except ImportError:  # run from the project root
    from tests import test_web as _web

ING = """"Datum";"Naam / Omschrijving";"Rekening";"Tegenrekening";"Code";"Af Bij";"Bedrag (EUR)";"Mutatiesoort";"Mededelingen"
"20260105";"Werkgever BV";"NL01";"NL02";"OV";"Bij";"2.850,00";"Overschrijving";"Salaris januari"
"20260106";"Albert Heijn 1234";"NL01";"";"BA";"Af";"54,20";"Betaalautomaat";"Pasvolgnr 001"
"20260110";"Netflix International";"NL01";"NL03";"IC";"Af";"13,99";"Incasso";"Netflix"
"20260210";"Netflix International";"NL01";"NL03";"IC";"Af";"13,99";"Incasso";"Netflix"
"20260310";"Netflix International";"NL01";"NL03";"IC";"Af";"13,99";"Incasso";"Netflix"
"20260312";"Onbekende Winkel";"NL01";"";"BA";"Af";"1.250,00";"Betaalautomaat";"iets groots"
"""
US = """Some bank, exported 2026-04-01

Transaction Date,Description,Debit,Credit
01/05/2026,PAYROLL ACME INC,,"3,100.00"
01/31/2026,SPOTIFY USA,10.99,
02/28/2026,SPOTIFY USA,10.99,
03/31/2026,SPOTIFY USA,10.99,
03/15/2026,TESCO STORES,82.40,
"""


class PackTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="tz-pack-"))
        self.home = Home(self.dir / "home")
        self.home.init(with_examples=False)
        for pack in PACKS:
            install(self.home.scripts, pack["id"])
        self.tools = {t.name: t for t in self.home.tools()[0]}
        self.work = self.dir / "work"
        self.work.mkdir()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def run_tool(self, name, **settings):
        result = run_tool(self.home, self.tools[name], {k: str(v) for k, v in settings.items()}, engine=None)
        log = Path(result.log).read_text(encoding="utf-8", errors="replace") if getattr(result, "log", None) else ""
        return result, log

    def out(self, result, name):
        return (Path(result.output_dir) / name).read_text(encoding="utf-8-sig")

    def test_every_tool_is_healthy_offline_and_standard_library_only(self):
        self.assertEqual(len(self.tools), 11)
        for t in self.tools.values():
            self.assertEqual(t.dependencies, [], t.name)  # nothing to install: works without the internet
            source = t.path.read_text(encoding="utf-8")
            found = check(t, source)
            self.assertEqual([f["title"] for f in found if f["level"] != "info"], [], t.name)
            self.assertFalse([w for w in wants(t, source, found) if "internet" in w or "programs" in w], t.name)
            self.assertTrue(t.description and t.icon != "terminal", t.name)

    def test_install_keeps_what_you_changed(self):
        mine = self.home.scripts / "everyday_files" / "tidy_folder.py"
        mine.write_text(mine.read_text() + "# my change\n")
        (self.home.scripts / "everyday_files" / "rename_files.py").unlink()
        self.assertTrue(next(p for p in overview(self.home.scripts) if p["id"] == "everyday_files")["partly"])
        self.assertEqual(install(self.home.scripts, "everyday_files"), ["rename_files.py"])
        self.assertIn("# my change", mine.read_text())
        self.assertTrue(all(p["installed"] for p in overview(self.home.scripts)))
        with self.assertRaises(PackProblem):
            install(self.home.scripts, "../etc")

    def test_tidy_and_rename_preview_first_and_never_overwrite(self):
        for name in ("a.jpg", "b.PDF", "c.xyz"):
            (self.work / name).write_text(name)
        (self.work / "Pictures").mkdir()
        (self.work / "Pictures" / "a.jpg").write_text("already here")
        r, log = self.run_tool("Tidy a folder", folder=self.work)
        self.assertEqual(r.status, "done", log)
        self.assertTrue((self.work / "a.jpg").exists())  # preview: nothing moved
        r, log = self.run_tool("Tidy a folder", folder=self.work, really_move="true")
        self.assertEqual(r.status, "done", log)
        self.assertEqual((self.work / "Pictures" / "a.jpg").read_text(), "already here")
        self.assertEqual((self.work / "Pictures" / "a (2).jpg").read_text(), "a.jpg")
        self.assertTrue((self.work / "Documents" / "b.PDF").exists() and (self.work / "Other" / "c.xyz").exists())

        folder = self.work / "Other"
        (folder / "My File.TXT").write_text("1")
        (folder / "my-file.txt").write_text("2")
        r, log = self.run_tool("Rename files", folder=folder, style="Lowercase, no spaces")
        self.assertTrue((folder / "My File.TXT").exists())
        r, log = self.run_tool("Rename files", folder=folder, style="Lowercase, no spaces", really_rename="true")
        self.assertEqual(r.status, "done", log)
        self.assertEqual(sorted(p.read_text() for p in folder.glob("my-file*")), ["1", "2"])
        self.assertIn("My File.TXT", self.out(r, "rename-list.csv"))

    def test_duplicates_space_and_backup(self):
        (self.work / "sub").mkdir()
        (self.work / "one.bin").write_bytes(b"x" * 20000)
        (self.work / "sub" / "copy.bin").write_bytes(b"x" * 20000)
        (self.work / "other.bin").write_bytes(b"y" * 20000)
        r, log = self.run_tool("Find duplicate files", folder=self.work)
        self.assertEqual(r.status, "done", log)
        listed = self.out(r, "duplicates.csv")
        self.assertIn("one.bin", listed)
        self.assertIn("copy.bin", listed)
        self.assertNotIn("other.bin", listed)
        self.assertTrue((self.work / "sub" / "copy.bin").exists())  # it only lists

        r, log = self.run_tool("What takes the space?", folder=self.work)
        self.assertEqual(r.status, "done", log)
        self.assertIn("sub", self.out(r, "biggest-folders.csv"))

        target = self.dir / "backups"
        target.mkdir()
        (target / "keep-me.zip").write_text("someone else's file")
        for _ in range(3):
            r, log = self.run_tool("Back up a folder", folder=self.work, target=target, keep=2)
            self.assertEqual(r.status, "done", log)
            time.sleep(1.1)
        zips = sorted(target.glob("work-backup-*.zip"))
        self.assertEqual(len(zips), 2)
        self.assertTrue((target / "keep-me.zip").exists())  # only its own old backups are removed
        with zipfile.ZipFile(zips[-1]) as z:
            self.assertEqual(sorted(z.namelist()), ["one.bin", "other.bin", "sub/copy.bin"])
        r, log = self.run_tool("Back up a folder", folder=self.work, target=self.work / "sub")
        self.assertEqual(r.status, "failed")

    def test_home_finance_reads_different_banks(self):
        ing, us = self.work / "ing.csv", self.work / "us.csv"
        ing.write_text(ING, encoding="utf-8")
        us.write_bytes(US.encode("cp1252"))
        r, log = self.run_tool("Bank statement overview", statement=ing)
        self.assertEqual(r.status, "done", log)
        tx = self.out(r, "transactions.csv")
        self.assertIn("2026-01-05,2850.00,Income", tx)
        self.assertIn("2026-01-06,-54.20,Groceries", tx)
        self.assertIn("2026-03-12,-1250.00,Other", tx)
        self.assertIn("Onbekende Winkel", self.out(r, "overview.html"))
        rules = self.home.data / "my-categories.csv"
        rules.write_text(rules.read_text() + "onbekende winkel,Furniture\n")
        r, log = self.run_tool("Bank statement overview", statement=ing)
        self.assertIn("-1250.00,Furniture", self.out(r, "transactions.csv"))  # your own keywords are used

        r, log = self.run_tool("Bank statement overview", statement=us)
        self.assertEqual(r.status, "done", log)
        tx = self.out(r, "transactions.csv")
        self.assertIn("2026-01-05,3100.00", tx)
        self.assertIn("2026-03-15,-82.40,Groceries", tx)

        for path, who in ((ing, "netflix international"), (us, "spotify usa")):
            r, log = self.run_tool("Find subscriptions", statement=path)
            self.assertEqual(r.status, "done", log)
            subs = self.out(r, "subscriptions.csv")
            self.assertTrue(subs.splitlines()[1].startswith(who) and ",monthly," in subs, subs)
            self.assertEqual(len(subs.strip().splitlines()), 2, subs)

        bad = self.work / "notes.csv"
        bad.write_text("hello;world\n1;2\n")
        r, log = self.run_tool("Bank statement overview", statement=bad)
        self.assertEqual(r.status, "failed")
        self.assertIn("Couldn't find the date and amount columns", log)

    def test_tables_and_data(self):
        a, b = self.work / "a.csv", self.work / "b.csv"
        a.write_text("date;city;temp\n2026-01-01;Utrecht;4.5\n2026-01-02;Utrecht;\n", encoding="utf-8")
        b.write_text("date,city,rain\n2026-01-03,Breda,1\n2026-01-03,Breda,1\n", encoding="utf-8")
        r, log = self.run_tool("Check a download", file=a)
        self.assertEqual(r.status, "done", log)
        report = self.out(r, "check.txt")
        self.assertIn("Rows: 2", report)
        self.assertIn("2026-01-01 to 2026-01-02", report)
        self.assertIn("temp 1", report)
        r, log = self.run_tool("Check a download", file=a, expect_rows=10)
        self.assertEqual(r.status, "failed")
        page = self.work / "login.csv"
        page.write_text("<html><body>Please log in</body></html>")
        r, log = self.run_tool("Check a download", file=page)
        self.assertEqual(r.status, "failed")
        self.assertIn("web page", log)

        r, log = self.run_tool("Merge CSV files", folder=self.work, drop_doubles="true")
        self.assertEqual(r.status, "done", log)
        merged = self.out(r, "merged.csv").splitlines()
        self.assertEqual(merged[0], "date,city,temp,rain,source file")
        self.assertIn("2026-01-03,Breda,,1,b.csv", merged)
        self.assertEqual(sum("Breda" in l for l in merged), 1)

        r, log = self.run_tool("CSV into a database", file=a, database="Weather Data", mode="Replace it")
        self.assertEqual(r.status, "done", log)
        db = self.home.data / "Weather-Data.sqlite"
        con = sqlite3.connect(db)
        self.assertEqual(con.execute("SELECT typeof(temp), temp FROM a ORDER BY date").fetchall(), [("real", 4.5), ("null", None)])
        con.close()
        r, log = self.run_tool("CSV into a database", file=a, database="Weather Data", mode="Add the rows to it")
        r, log = self.run_tool("Database table to CSV", database=db)
        self.assertIn("a: 4 rows", log)
        r, log = self.run_tool("Database table to CSV", database=db, table="A")
        self.assertEqual(r.status, "done", log)
        self.assertEqual(self.out(r, "a.csv").splitlines()[:2], ["date;city;temp", "2026-01-01;Utrecht;4.5"])
        r, log = self.run_tool("Database table to CSV", database=a)
        self.assertEqual(r.status, "failed")


class PackWebTests(unittest.TestCase):
    setUp = _web.WebTests.setUp
    tearDown = _web.WebTests.tearDown
    request = _web.WebTests.request

    def test_gallery(self):
        self.request("GET", "/api/tools")
        status, data = self.request("GET", "/api/packs")
        self.assertEqual([p["name"] for p in data["packs"]], ["Everyday files", "Home finance", "Tables and data"])
        self.assertFalse(any(p["installed"] for p in data["packs"]))
        self.assertEqual(len(data["packs"][1]["tools"]), 2)  # the helper module isn't shown as a tool
        status, data = self.request("POST", "/api/packs/install", {"pack": "home_finance"})
        self.assertEqual(status, 200, data)
        new = [t for t in data["tools"] if t["group"] == "home_finance"]
        self.assertEqual(sorted(t["name"] for t in new), ["Bank statement overview", "Find subscriptions"])
        self.assertFalse(any(t["review"] for t in new))  # they come with traPYze: no first-run question
        self.assertEqual(data["programs"]["home_finance"]["name"], "Home finance")
        self.assertTrue(data["packs"][1]["installed"])
        status, data = self.request("POST", "/api/packs/install", {"pack": "nope"})
        self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main()

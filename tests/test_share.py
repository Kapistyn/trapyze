"""Phase 7b: sharing a tool as one file, and importing it on the other side."""

import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from trapyze import Home  # noqa: E402
from trapyze.importer import ImportProblem, apply, scan  # noqa: E402
from trapyze.share import ShareProblem, share  # noqa: E402
from trapyze.store import Presets  # noqa: E402
from test_import import make_program  # noqa: E402
import test_web  # noqa: E402

RANKER = ('# /// script\n# [tool.trapyze]\n# name = "Quick rank"\n#\n# [[tool.trapyze.settings]]\n# key = "top"\n'
          '# label = "Top"\n# type = "int"\n# default = 10\n# ///\nprint("rank")\n')


class ShareTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="tz-share-"))
        self.mine = Home(self.dir / "mine")
        self.mine.init(with_examples=False)
        self.theirs = Home(self.dir / "theirs")
        self.theirs.init(with_examples=False)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_single_script_with_presets(self):
        (self.mine.scripts / "quick_rank.py").write_text(RANKER)
        tool = self.mine.find("quick_rank")
        Presets(self.mine.internal).save(tool, "Top 25", {"top": 25})
        result = share(self.mine, tool, self.mine.tools()[0], Presets(self.mine.internal).all(), ["sk_live_secret99"])
        out = Path(result["path"])
        self.assertEqual((out.parent.name, out.suffix), ("Shared", ".py"))
        self.assertIn('# "Top 25" = { top = 25 }', out.read_text())
        plan = scan(out, self.theirs)
        self.assertIn("1 preset", " ".join(plan["notes"]))
        report = apply(out, self.theirs, {})
        self.assertEqual(report["presets"], 1)
        tool_id = report["tools"][0]
        self.assertEqual(Presets(self.theirs.internal).get(tool_id, "Top 25"), {"top": 25})

    def test_vault_values_never_leave(self):
        (self.mine.scripts / "leaky.py").write_text(RANKER.replace('print("rank")', 'KEY = "sk_live_secret99"\nprint(KEY)'))
        tool = self.mine.find("leaky")
        with self.assertRaises(ShareProblem) as caught:
            share(self.mine, tool, self.mine.tools()[0], {}, ["sk_live_secret99"])
        self.assertIn("leaky.py", str(caught.exception))
        self.assertFalse(list((self.mine.outputs / "Shared").glob("*")))
        # Not in the vault, but looks like a key: shared, with a warning.
        result = share(self.mine, tool, self.mine.tools()[0], {}, [])
        self.assertEqual(result["notes"], [])  # "KEY" alone isn't a key-ish name
        (self.mine.scripts / "leaky.py").write_text(RANKER.replace('print("rank")', 'api_key = "abcdef123456"'))
        result = share(self.mine, self.mine.find("leaky"), self.mine.tools()[0], {}, [])
        self.assertIn("line 11", result["notes"][0])

    def test_program_as_zip_round_trip(self):
        prog = make_program(self.dir / "projects")
        apply(prog, self.mine, {"name": "Price database", "description": "Index members since 2006."})
        tools = self.mine.tools()[0]
        main = next(t for t in tools if t.id == "price_db")
        Presets(self.mine.internal).save(main, "Quick update", {"command": "update", "days": 2})
        (self.mine.scripts / "price_db" / "price_db.py.lock").write_text("version = 1\n")
        (self.mine.scripts / "price_db" / "local.env").write_text("FMP_API_KEY=abc\n")
        result = share(self.mine, main, tools, Presets(self.mine.internal).all(), [], include_data=True)
        out = Path(result["path"])
        names = zipfile.ZipFile(out).namelist()
        self.assertIn("price_db/price_db.py", names)
        self.assertIn("price_db/price_db.py.lock", names)
        self.assertIn("price_db/presets.json", names)
        self.assertIn("price_db/data/price_db.sqlite", names)
        self.assertNotIn("price_db/local.env", names)
        self.assertFalse(any("__pycache__" in n or "_replaced" in n for n in names))
        # The other side imports the .zip.
        plan = scan(out, self.theirs)
        self.assertEqual((plan["name"], plan["description"]), ("Price database", "Index members since 2006."))
        self.assertEqual(plan["zip"], str(out))
        report = apply(out, self.theirs, {})
        self.assertEqual((report["tools"], report["hidden"]), (["price_db"], ["price_db.fixes.hwm_from_aa"]))
        self.assertIn("price_db.sqlite", report["data"])
        self.assertEqual(report["presets"], 1)
        self.assertTrue((self.theirs.scripts / "price_db" / "price_db.py.lock").exists())
        self.assertEqual(self.theirs.programs()["price_db"]["name"], "Price database")
        # A script I gave its own tile keeps it on the other side.
        self.mine.set_hidden("price_db", set(), {"price_db.fixes.hwm_from_aa"})
        again = share(self.mine, main, self.mine.tools()[0], {}, [])
        other = Home(self.dir / "third")
        other.init(with_examples=False)
        self.assertEqual(sorted(apply(again["path"], other, {})["tools"]), ["price_db", "price_db.fixes.hwm_from_aa"])
        # Without data, smaller; and a damaged zip is refused plainly.
        lean = share(self.mine, main, tools, {}, [], include_data=False)
        self.assertNotIn("price_db/data/price_db.sqlite", zipfile.ZipFile(lean["path"]).namelist())
        bad = self.dir / "broken.zip"
        bad.write_bytes(b"not a zip")
        with self.assertRaises(ImportProblem):
            scan(bad, self.theirs)

    def test_zip_cannot_write_outside(self):
        evil = self.dir / "evil.zip"
        with zipfile.ZipFile(evil, "w") as z:
            z.writestr("../../escaped.py", "print(1)")
            z.writestr("prog/run.py", "if __name__ == '__main__':\n    print(1)\n")
        plan = scan(evil, self.theirs)
        self.assertEqual([p["rel"] for p in plan["programs"]], ["run.py"])
        self.assertFalse((self.dir / "escaped.py").exists())


class ShareWebTests(unittest.TestCase):
    setUp = test_web.WebTests.setUp
    tearDown = test_web.WebTests.tearDown
    request = test_web.WebTests.request

    def test_share_and_packages_calls(self):
        tool = self.request("GET", "/api/tools")[1]["tools"][0]["id"]
        status, data = self.request("POST", "/api/share", {"tool": tool})
        self.assertEqual(status, 200, data)
        self.assertTrue(Path(data["path"]).exists())
        self.assertIn("vault was locked", data["notes"][0])
        status, data = self.request("POST", "/api/packages/status", {"tool": tool})
        self.assertEqual(status, 200)
        self.assertFalse(data["status"]["locked"])
        self.assertEqual(self.request("GET", "/api/import/wsl")[1]["path"], None)


if __name__ == "__main__":
    unittest.main()

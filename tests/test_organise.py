import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from trapyze import scriptfiles as sf, storage  # noqa: E402
from trapyze.bin import Bin  # noqa: E402
from trapyze.home import Home  # noqa: E402

HEAD = '# /// script\n# [tool.trapyze]\n# name = "{n}"\n# ///\n'


class OrganiseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Home(self.tmp.name)
        self.home.init(with_examples=False)
        s = self.home.scripts
        (s / "ranker.py").write_text(HEAD.format(n="Ranker") + "print(1)\n")
        (s / "ranker.py.lock").write_text("lock")
        (s / "lone.py").write_text(HEAD.format(n="Lone") + "print(2)\n")
        (s / "prog").mkdir()
        (s / "prog" / "prog.py").write_text(HEAD.format(n="Prog") + "print(3)\n")
        (s / "prog" / "helper.py").write_text("x = 1\n")
        i = self.home.internal
        (i / "presets.json").write_text(json.dumps({"ranker": {"fast": {"top": 5}}}))
        (i / "last_settings.json").write_text(json.dumps({"ranker": {"top": 9}}))
        (i / "chains.json").write_text(json.dumps({"chains": [{"id": "c1", "name": "C", "steps": [{"tool": "ranker", "use": "last"}]}]}))
        (i / "schedules.json").write_text(json.dumps({"plans": [{"id": "p1", "name": "P", "target_kind": "tool", "target": "ranker"}]}))
        (i / "looks.json").write_text(json.dumps({"tools": {"ranker": {"icon": "bolt"}}}))
        (i / "versions" / "ranker").mkdir(parents=True)
        (i / "versions" / "ranker" / "index.json").write_text("[]")

    def tearDown(self):
        self.tmp.cleanup()

    def read(self, name):
        return json.loads((self.home.internal / name).read_text())

    def test_move_into_a_program_carries_everything_along(self):
        done = sf.move_file(self.home, "ranker.py", "prog")
        self.assertEqual(done["mapping"], {"ranker": "prog.ranker"})
        self.assertTrue((self.home.scripts / "prog" / "ranker.py").is_file())
        self.assertTrue((self.home.scripts / "prog" / "ranker.py.lock").is_file())
        self.assertFalse((self.home.scripts / "ranker.py").exists())
        self.assertIn("prog.ranker", self.read("presets.json"))
        self.assertIn("prog.ranker", self.read("last_settings.json"))
        self.assertEqual(self.read("chains.json")["chains"][0]["steps"][0]["tool"], "prog.ranker")
        self.assertEqual(self.read("schedules.json")["plans"][0]["target"], "prog.ranker")
        self.assertIn("prog.ranker", self.read("looks.json")["tools"])
        self.assertTrue((self.home.internal / "versions" / "prog.ranker").is_dir())
        ids = {t.id for t in self.home.tools()[0]}
        self.assertIn("prog.ranker", ids)

    def test_move_refuses_a_name_that_is_taken_and_warns_about_helpers(self):
        (self.home.scripts / "prog" / "lone.py").write_text("x = 2\n")
        with self.assertRaises(sf.ScriptFileError):
            sf.move_file(self.home, "lone.py", "prog")
        (self.home.scripts / "prog" / "uses.py").write_text(HEAD.format(n="Uses") + "import helper\n")
        done = sf.move_file(self.home, "prog/uses.py", "")
        self.assertTrue(any("helper.py" in n for n in done["notes"]))

    def test_rename_file_and_program(self):
        done = sf.rename_file(self.home, "ranker.py", "top ranker")
        self.assertEqual(done["mapping"], {"ranker": "top ranker"})
        self.assertTrue((self.home.scripts / "top ranker.py").is_file())
        self.assertTrue((self.home.scripts / "top ranker.py.lock").is_file())
        with self.assertRaises(sf.ScriptFileError):
            sf.rename_file(self.home, "lone.py", "../x")
        done = sf.rename_program(self.home, "prog", "Price Tools")
        self.assertEqual(done["folder"], "price_tools")
        self.assertEqual(done["mapping"]["prog"], "price_tools")
        self.assertEqual(self.home.programs()["price_tools"]["name"], "Price Tools")

    def test_new_program_from_loose_scripts(self):
        done = sf.new_program(self.home, "Plus One", ["ranker.py", "lone.py"])
        self.assertEqual(done["folder"], "plus_one")
        self.assertEqual(done["mapping"], {"ranker": "plus_one.ranker", "lone": "plus_one.lone"})
        self.assertEqual(self.read("schedules.json")["plans"][0]["target"], "plus_one.ranker")
        with self.assertRaises(sf.ScriptFileError):
            sf.new_program(self.home, "Plus One", ["x.py"])

    def test_duplicates_and_new_versions(self):
        s = self.home.scripts
        body = "".join(f"line {i}\n" for i in range(60))
        (s / "same_a.py").write_text(HEAD.format(n="A") + body)
        (s / "prog" / "same_a_copy.py").write_text(body)
        (s / "ranker (1).py").write_text(HEAD.format(n="Ranker") + "print(1)\nprint(99)\n")
        pairs = sf.duplicates(self.home)
        kinds = {(p["a"]["name"], p["b"]["name"]): p["kind"] for p in pairs}
        self.assertEqual(kinds[("same_a.py", "same_a_copy.py")] if ("same_a.py", "same_a_copy.py") in kinds else kinds[("same_a_copy.py", "same_a.py")], "identical")
        self.assertTrue(any({p["a"]["name"], p["b"]["name"]} == {"ranker.py", "ranker (1).py"} for p in pairs))
        self.assertEqual([f["name"] for f in sf.looks_like(self.home, "ranker_v2.py")], ["ranker (1).py", "ranker.py"])
        d = sf.compare(self.home, "ranker.py", "ranker (1).py")
        self.assertEqual((d["added"], d["removed"], d["same"]), (1, 0, False))

    def test_update_plan_suggests_the_old_file_and_can_be_pointed_at_it(self):
        s = self.home.scripts
        (s / "prog" / "report.py").write_text(HEAD.format(n="Report") + "print('old')\n")
        out = Path(self.tmp.name) / "incoming"
        out.mkdir()
        (out / "report_v2.py").write_text("print('new')\nprint('more')\n")
        plan = sf.update_plan(self.home, "prog", str(out))
        item = plan["items"][0]
        self.assertEqual(item["state"], "new")
        self.assertEqual([f["rel"] for f in item["looks_like"]], ["prog/report.py"])
        plan = sf.update_plan(self.home, "prog", str(out), {"report_v2.py": "report.py"})
        self.assertEqual((plan["items"][0]["to"], plan["items"][0]["state"]), ("report.py", "changed"))
        self.assertGreater(plan["items"][0]["diff"]["added"], 0)
        done = sf.update_apply(self.home, "prog", str(out), None, {"report_v2.py": "report.py"})
        self.assertEqual(done["updated"], ["report.py"])
        self.assertIn("more", (s / "prog" / "report.py").read_text())
        self.assertIn('name = "Report"', (s / "prog" / "report.py").read_text())

    def test_old_copies_go_to_the_bin_by_the_tidy_up(self):
        s = self.home.scripts
        (s / "_replaced" / "prog-update-1").mkdir(parents=True)
        (s / "_replaced" / "prog-update-1" / "a.py").write_text("old")
        (s / "_set_aside_2026-01-01").mkdir()
        (s / "_set_aside_2026-01-01" / "b.py").write_text("old")
        (s / "_replaced" / "fresh").mkdir()
        old = time.time() - 40 * 86400
        for p in [s / "_replaced" / "prog-update-1", s / "_replaced" / "prog-update-1" / "a.py", s / "_set_aside_2026-01-01", s / "_set_aside_2026-01-01" / "b.py"]:
            os.utime(p, (old, old))
        found = {p.name for p in storage.old_copies(self.home, 30)}
        self.assertEqual(found, {"prog-update-1", "_set_aside_2026-01-01"})
        done = storage.tidy(self.home, Bin(self.home))
        self.assertEqual(done["moved"], 2)
        self.assertFalse((s / "_set_aside_2026-01-01").exists())
        self.assertTrue((s / "_replaced" / "fresh").exists())


if __name__ == "__main__":
    unittest.main()

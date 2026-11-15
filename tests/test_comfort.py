"""Phase 5a: presets, data freshness, chains and look and feel."""

import base64
import datetime as dt
import json
import os
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from trapyze import Home, read_tool  # noqa: E402
from trapyze.freshness import checks, parse_age, too_old, weekdays_between  # noqa: E402
from trapyze.label import LabelError, SettingError  # noqa: E402
from trapyze.runner import Run  # noqa: E402
from trapyze.store import Chains, ChainRun, Looks, Presets, StoreError, step_settings  # noqa: E402
import test_web  # noqa: E402

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")


def script(home, name, body, label=""):
    (home.scripts / f"{name}.py").write_text(f"# /// script\n# [tool.trapyze]\n# name = \"{name.title()}\"\n{label}# ///\n{body}\n")
    return read_tool(home.scripts / f"{name}.py")


class FreshnessTests(unittest.TestCase):
    def test_ages(self):
        self.assertEqual(parse_age("1td"), (1.0, "td"))
        with self.assertRaises(ValueError):
            parse_age("yesterday")
        fri, mon, tue = dt.datetime(2026, 11, 13, 22), dt.datetime(2026, 11, 16, 9), dt.datetime(2026, 11, 17, 9)
        self.assertEqual(weekdays_between(fri.date(), mon.date()), 0)
        self.assertFalse(too_old(fri.timestamp(), "1td", mon.timestamp()))  # Friday's prices are fine on Monday
        self.assertTrue(too_old(fri.timestamp(), "1td", tue.timestamp()))   # but not on Tuesday
        self.assertTrue(too_old(fri.timestamp(), "1d", mon.timestamp()))
        self.assertFalse(too_old(time.time() - 3600, "2h"))

    def test_label_reads(self):
        import tempfile
        home = Home(Path(tempfile.mkdtemp()))
        home.init(with_examples=False)
        t = script(home, "a", "", '# reads = { "data/p.db" = "1td" }\n')
        self.assertEqual(t.reads, {"data/p.db": "1td"})
        self.assertEqual(script(home, "b", "", '# reads = ["data/p.db"]\n').reads, {"data/p.db": None})
        with self.assertRaises(LabelError) as caught:
            script(home, "c", "", '# reads = { "data/p.db" = "soon" }\n')
        self.assertIn("isn't an age", str(caught.exception))

    def test_checks_name_the_maker(self):
        import tempfile
        home = Home(Path(tempfile.mkdtemp()))
        home.init(with_examples=False)
        maker = script(home, "maker", "", '# writes = ["data/p.db"]\n')
        user = script(home, "user", "", '# reads = { "{data}/p.db" = "12h" }\n')
        found = checks(home, user, [maker, user], True, 50 * 1024**3)
        self.assertEqual((found[0]["code"], found[0]["action"]["tool"]), ("missing", "maker"))
        db = home.data / "p.db"
        db.write_text("x")
        self.assertEqual(checks(home, user, [maker, user], True, None), [])
        old = time.time() - 3 * 86400
        os.utime(db, (old, old))
        found = checks(home, user, [maker, user], False, 10 * 1024**2)
        self.assertEqual([n["code"] for n in found], ["old", "disk"])
        self.assertIn("3 days ago, by Maker", found[0]["text"])


class StoreTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.home = Home(Path(tempfile.mkdtemp()))
        self.home.init(with_examples=False)
        self.tool = script(self.home, "ranker", "import sys; print(sys.argv[1:])",
                           '# [[tool.trapyze.settings]]\n# key = "top_n"\n# label = "Top"\n# type = "int"\n# default = 10\n# max = 50\n')

    def test_presets(self):
        p = Presets(self.home.internal)
        p.save(self.tool, " Weekly  big ", {"top_n": 40})
        self.assertEqual(p.get("ranker", "Weekly big"), {"top_n": 40})
        with self.assertRaises(SettingError):
            p.save(self.tool, "Too big", {"top_n": 99})
        p.delete("ranker", "Weekly big")
        self.assertEqual(p.all(), {})

    def test_chain_runs_in_order_and_stops_after_a_problem(self):
        ok = script(self.home, "ok", 'print("ran ok")')
        bad = script(self.home, "bad", "raise SystemExit(3)")
        tools = [ok, bad, self.tool]
        chains, presets = Chains(self.home.internal), Presets(self.home.internal)
        presets.save(self.tool, "Wide", {"top_n": 33})
        with self.assertRaises(StoreError):
            chains.save({"name": "x", "steps": [{"tool": "ranker", "use": "preset:Nope"}]}, tools, presets)
        chain = chains.save({"name": "Morning", "steps": [{"tool": "ok"}, {"tool": "bad"}, {"tool": "ranker", "use": "preset:Wide"}]},
                            tools, presets)
        settings = [step_settings(s, presets, {}) for s in chain.steps]
        self.assertEqual(settings[2], {"top_n": 33})
        by_id = {t.id: t for t in tools}
        start = lambda tid, chosen: Run(self.home, by_id[tid], chosen, engine=None).start()  # noqa: E731
        cr = ChainRun(chain, settings, {}, start).begin()
        self.assertEqual(cr.wait(60), "failed")
        self.assertEqual([s["status"] for s in cr.steps], ["done", "failed", "skipped"])
        chain = chains.save({"id": chain.id, "name": "Morning", "on_problem": "continue",
                             "steps": [{"tool": "bad"}, {"tool": "ranker", "use": "preset:Wide"}]}, tools, presets)
        cr = ChainRun(chain, [{}, {"top_n": 33}], {}, start).begin()
        cr.wait(60)
        self.assertEqual([s["status"] for s in cr.steps], ["failed", "done"])
        self.assertEqual(len(chains.all()), 1)  # edited, not duplicated

    def test_looks(self):
        looks = Looks(self.home.internal)
        self.assertEqual(looks.update({"theme": "dark", "accent": "teal"})["theme"], "dark")
        with self.assertRaises(StoreError):
            looks.update({"theme": "neon"})
        looks.set_tool("ranker", "rocket", "rose")
        self.assertEqual(looks.get()["tools"]["ranker"], {"icon": "rocket", "color": "rose"})
        looks.set_image("ranker", "data:image/png;base64," + base64.b64encode(PNG).decode())
        self.assertEqual(looks.image_path("ranker").suffix, ".png")
        for bad in ("data:image/svg+xml;base64," + base64.b64encode(b"<svg onload=alert(1)>").decode(), "nonsense"):
            with self.assertRaises(StoreError):
                looks.set_image("ranker", bad)
        with self.assertRaises(StoreError):
            looks.set_image("../escape", "data:image/png;base64," + base64.b64encode(PNG).decode())
        looks.reset_tool("ranker")
        self.assertIsNone(looks.image_path("ranker"))
        self.assertEqual(looks.get()["tools"], {})


class ComfortWebTests(unittest.TestCase):
    setUp = test_web.WebTests.setUp
    tearDown = test_web.WebTests.tearDown
    request = test_web.WebTests.request

    def test_presets_looks_and_update_first_chain(self):
        maker = self.home.scripts / "maker.py"
        maker.write_text('# /// script\n# [tool.trapyze]\n# name = "Maker"\n# writes = ["data/p.db"]\n# ///\n'
                         'import os, pathlib\npathlib.Path(os.environ["TRAPYZE_DATA_DIR"], "p.db").write_text("fresh")\n')
        (self.home.scripts / "user.py").write_text(
            '# /// script\n# [tool.trapyze]\n# name = "User"\n# reads = { "data/p.db" = "1h" }\n'
            '# [[tool.trapyze.settings]]\n# key = "n"\n# label = "N"\n# type = "int"\n# default = 1\n# ///\n'
            'import os, pathlib\nprint(pathlib.Path(os.environ["TRAPYZE_DATA_DIR"], "p.db").read_text())\n')
        tools = {t["id"]: t for t in self.request("GET", "/api/tools")[1]["tools"]}
        self.assertEqual(tools["user"]["checks"][0]["action"], {"kind": "update", "tool": "maker", "name": "Maker"})
        # Presets
        status, data = self.request("POST", "/api/presets/save", {"tool": "user", "name": "Five", "settings": {"n": 5}})
        self.assertEqual(status, 200)
        self.assertEqual(next(t for t in data["tools"] if t["id"] == "user")["presets"], {"Five": {"n": 5}})
        status, data = self.request("POST", "/api/presets/save", {"tool": "user", "name": "Bad", "settings": {"n": "x"}})
        self.assertEqual(status, 400)
        # Update first, then run: a two-step chain
        status, cr = self.request("POST", "/api/chains/run", {"tool": "user", "update_first": "maker", "settings": {"n": 2}})
        self.assertEqual(status, 201, cr)
        deadline = time.time() + 60
        while cr["status"] == "running" and time.time() < deadline:
            time.sleep(0.2)
            cr = self.request("GET", f"/api/chains/runs/{cr['id']}")[1]
        self.assertEqual(cr["status"], "done", cr)
        self.assertEqual([s["name"] for s in cr["steps"]], ["Maker", "User"])
        tools = {t["id"]: t for t in self.request("GET", "/api/tools")[1]["tools"]}
        self.assertEqual(tools["user"]["checks"], [])
        self.assertEqual(tools["user"]["remembered"], {"n": 2})
        # A saved chain
        status, data = self.request("POST", "/api/chains/save", {"name": "Both", "steps": [{"tool": "maker"}, {"tool": "user", "use": "preset:Five"}]})
        self.assertEqual(status, 200)
        self.assertEqual(data["chains"][0]["name"], "Both")
        # Looks
        status, data = self.request("POST", "/api/looks/window", {"theme": "dark"})
        self.assertEqual(data["looks"]["theme"], "dark")
        self.request("POST", "/api/looks/tool", {"tool": "user", "icon": "rocket", "color": "teal"})
        status, data = self.request("POST", "/api/looks/image", {"tool": "user", "data": "data:image/png;base64," + base64.b64encode(PNG).decode()})
        user = next(t for t in data["tools"] if t["id"] == "user")
        self.assertEqual((user["icon"], user["color"], user["label_look"]["icon"]), ("rocket", "teal", "terminal"))
        status, raw = self.request("GET", user["image"].split("?")[0])
        self.assertEqual(status, 200)
        self.assertEqual(self.request("GET", "/api/icons/user", token=False)[0], 403)


if __name__ == "__main__":
    unittest.main()

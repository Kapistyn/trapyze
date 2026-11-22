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

    def test_chain_step_tries_again_after_a_failure(self):
        flaky = script(self.home, "flaky", 'import pathlib, sys\nm = pathlib.Path(__file__).with_name("count.txt")\n'
                       'n = int(m.read_text()) + 1 if m.exists() else 1\nm.write_text(str(n))\nsys.exit(0 if n >= 3 else 1)')
        tools = [flaky]
        chains, presets = Chains(self.home.internal), Presets(self.home.internal)
        chain = chains.save({"name": "Retry me", "steps": [{"tool": "flaky"}]}, tools, presets)
        by_id = {t.id: t for t in tools}
        start = lambda tid, chosen: Run(self.home, by_id[tid], chosen, engine=None).start()  # noqa: E731
        cr = ChainRun(chain, [{}], {}, start, retries=1, retry_wait=0).begin()
        self.assertEqual(cr.wait(60), "failed")
        self.assertEqual(cr.steps[0]["tries"], 1)
        (self.home.scripts / "count.txt").unlink()
        cr = ChainRun(chain, [{}], {}, start, retries=2, retry_wait=0).begin()
        self.assertEqual(cr.wait(60), "done")
        self.assertEqual(cr.steps[0]["tries"], 2)

    def test_plan_keeps_its_retry_settings(self):
        from trapyze.schedule import Plans
        tools = [script(self.home, "ok2", 'print(1)')]
        plans = Plans(self.home.internal)
        body = {"target_kind": "tool", "target": "ok2", "when": {"kind": "weekly", "days": [0], "times": ["07:30"]}}
        plan = plans.save({**body, "retries": 2, "retry_wait": 5}, tools, [], Presets(self.home.internal))
        self.assertEqual((plan["retries"], plan["retry_wait"]), (2, 5))
        plan = plans.save({**body, "id": plan["id"], "retries": 99, "retry_wait": "x"}, tools, [], Presets(self.home.internal))
        self.assertEqual((plan["retries"], plan["retry_wait"]), (3, 10))

    def test_background_plan_tries_a_failed_tool_again(self):
        from unittest import mock
        from trapyze import schedule
        script(self.home, "flaky2", 'import pathlib, sys\nm = pathlib.Path(__file__).with_name("count2.txt")\n'
               'n = int(m.read_text()) + 1 if m.exists() else 1\nm.write_text(str(n))\nsys.exit(0 if n >= 2 else 1)')
        tools = self.home.tools()[0]
        plans = schedule.Plans(self.home.internal)
        plan = plans.save({"target_kind": "tool", "target": "flaky2", "retries": 1, "retry_wait": 1,
                           "when": {"kind": "weekly", "days": [0], "times": ["07:30"]}}, tools, [], Presets(self.home.internal))
        waits = []
        with mock.patch.object(schedule.time, "sleep", lambda s: waits.append(s)):
            status = schedule.run_here(self.home, plan, __import__("datetime").datetime.now())
        self.assertEqual(status, "done")
        self.assertEqual(waits, [60])

    def test_chain_step_waits_for_an_ok(self):
        import time as _t
        a, b = script(self.home, "first", 'print(1)'), script(self.home, "second", 'print(2)')
        tools = [a, b]
        chains, presets = Chains(self.home.internal), Presets(self.home.internal)
        chain = chains.save({"name": "Ask", "steps": [{"tool": "first"}, {"tool": "second", "ask": True}]}, tools, presets)
        self.assertTrue(chains.all()[0].steps[1].ask)
        by_id = {t.id: t for t in tools}
        start = lambda tid, chosen: Run(self.home, by_id[tid], chosen, engine=None).start()  # noqa: E731
        asked = []
        for decision, expect in (("go", ["done", "done"]), ("skip", ["done", "skipped"]), ("stop", ["done", "skipped"])):
            cr = ChainRun(chain, [{}, {}], {}, start, on_ask=lambda c, s: asked.append(s["name"])).begin()
            for _ in range(100):
                if cr.steps[1]["status"] == "asking":
                    break
                _t.sleep(0.1)
            self.assertEqual(cr.steps[1]["status"], "asking")
            cr.answer(decision)
            cr.wait(60)
            self.assertEqual([s["status"] for s in cr.steps], expect)
        self.assertEqual(cr.status, "stopped")
        cr = ChainRun(chain, [{}, {}], {}, start, ask_wait=1).begin()
        self.assertEqual(cr.wait(60), "stopped")
        self.assertIn("No answer", cr.steps[1]["message"])
        with self.assertRaises(StoreError):
            cr.answer("maybe")

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

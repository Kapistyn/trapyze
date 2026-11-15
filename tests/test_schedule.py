"""Phase 6: plans, their sentences and times, the background tasks and running a plan."""

import datetime as dt
import json
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from trapyze import Home  # noqa: E402
from trapyze import schedule as sc  # noqa: E402
from trapyze.store import Chains, Presets, StoreError  # noqa: E402
import test_web  # noqa: E402

NS = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
FRI = dt.datetime(2026, 11, 13, 23, 30)  # a Friday


class WhenTests(unittest.TestCase):
    def test_sentences_and_next_times(self):
        weekdays = sc.check_when({"kind": "weekly", "days": [4, 0, 1, 2, 3], "times": ["18:00", "07:30"]})
        self.assertEqual(sc.describe(weekdays), "Every weekday at 07:30 and 18:00")
        self.assertEqual(sc.next_times(weekdays, FRI, 2), [dt.datetime(2026, 11, 16, 7, 30), dt.datetime(2026, 11, 16, 18, 0)])
        self.assertEqual(sc.last_time(weekdays, FRI), dt.datetime(2026, 11, 13, 18, 0))
        some = sc.check_when({"kind": "weekly", "days": [0, 3], "times": ["09:00"]})
        self.assertEqual(sc.describe(some), "Every Monday and Thursday at 09:00")
        rep = sc.check_when({"kind": "interval", "every": 15, "unit": "minutes", "from": "09:00", "to": "17:30", "days": list(range(5))})
        self.assertEqual(sc.describe(rep), "Every 15 minutes from 09:00 to 17:30, every weekday")
        self.assertEqual(len(sc.times_of_day(rep)), 35)
        self.assertEqual(sc.times_of_day(rep)[-1], (17, 30))
        last = sc.check_when({"kind": "monthly", "day": "last", "time": "20:00"})
        self.assertEqual(sc.describe(last), "On the last day of every month at 20:00")
        self.assertEqual(sc.next_times(last, FRI, 3), [dt.datetime(2026, 11, 30, 20), dt.datetime(2026, 12, 31, 20), dt.datetime(2027, 1, 31, 20)])
        self.assertEqual(sc.describe(sc.check_when({"kind": "monthly", "day": 2, "time": "06:00"})), "On the 2nd of every month at 06:00")
        once = sc.check_when({"kind": "once", "at": "2026-11-20T09:00"})
        self.assertEqual(sc.describe(once), "Once, on Friday 20 November 2026 at 09:00")
        self.assertEqual(sc.next_times(once, dt.datetime(2026, 11, 21), 1), [])
        self.assertEqual(sc.nice_time(dt.datetime(2026, 11, 14, 7, 30), FRI), "tomorrow at 07:30")

    def test_bad_input_in_plain_words(self):
        for when, words in (({"kind": "weekly", "days": [], "times": ["07:30"]}, "at least one day"),
                            ({"kind": "weekly", "days": [1], "times": ["7.30"]}, "24-hour clock"),
                            ({"kind": "interval", "every": 2, "unit": "minutes", "from": "09:00", "to": "10:00", "days": [1]}, "every 5 minutes"),
                            ({"kind": "interval", "every": 1, "unit": "hours", "from": "10:00", "to": "09:00", "days": [1]}, "later than"),
                            ({"kind": "monthly", "day": 30, "time": "07:00"}, "not every month"),
                            ({"kind": "sometimes"}, "Choose when")):
            with self.assertRaises(StoreError) as caught:
                sc.check_when(when)
            self.assertIn(words, str(caught.exception))


class BackgroundFormatTests(unittest.TestCase):
    plan = {"id": "abc123", "name": "Morning routine", "when": {"kind": "weekly", "days": [0, 1, 2, 3, 4], "times": ["07:30"]},
            "enabled": True, "wake": True, "logged_out": True, "missed": "run"}

    def test_windows_task(self):
        xml = sc.windows_xml(self.plan, Path("C:/Users/alex/Trapyze"), "LAPTOP\\alex", dt.date(2026, 11, 14))
        root = ET.fromstring(xml.split("\n", 1)[1])
        f = lambda p: root.find(p, NS)  # noqa: E731
        self.assertEqual(f("t:Settings/t:WakeToRun").text, "true")
        self.assertEqual(f("t:Settings/t:StartWhenAvailable").text, "true")
        self.assertEqual(f("t:Principals/t:Principal/t:LogonType").text, "Password")
        self.assertEqual(f("t:Principals/t:Principal/t:UserId").text, "LAPTOP\\alex")
        trig = f("t:Triggers/t:CalendarTrigger")
        self.assertEqual(trig.find("t:StartBoundary", NS).text, "2026-11-14T07:30:00")
        self.assertEqual([d.tag.split("}")[1] for d in trig.find("t:ScheduleByWeek/t:DaysOfWeek", NS)],
                         ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"])
        self.assertIn("fire abc123", f("t:Actions/t:Exec/t:Arguments").text)
        # Repeating, monthly and once
        rep = {**self.plan, "logged_out": False, "wake": False, "missed": "skip",
               "when": {"kind": "interval", "every": 2, "unit": "hours", "from": "09:00", "to": "17:00", "days": list(range(7))}}
        r = ET.fromstring(sc.windows_xml(rep, Path("/h"), "u").split("\n", 1)[1])
        self.assertEqual(r.find("t:Triggers/t:CalendarTrigger/t:Repetition/t:Interval", NS).text, "PT120M")
        self.assertEqual(r.find("t:Triggers/t:CalendarTrigger/t:Repetition/t:Duration", NS).text, "PT481M")
        self.assertIsNotNone(r.find("t:Triggers/t:CalendarTrigger/t:ScheduleByDay", NS))
        self.assertEqual(r.find("t:Principals/t:Principal/t:LogonType", NS).text, "InteractiveToken")
        self.assertEqual(r.find("t:Settings/t:WakeToRun", NS).text, "false")
        self.assertEqual(r.find("t:Settings/t:StartWhenAvailable", NS).text, "false")
        mon = {**self.plan, "when": {"kind": "monthly", "day": "last", "time": "20:00"}}
        m = ET.fromstring(sc.windows_xml(mon, Path("/h"), "u").split("\n", 1)[1])
        self.assertEqual(m.find("t:Triggers/t:CalendarTrigger/t:ScheduleByMonth/t:DaysOfMonth/t:Day", NS).text, "Last")
        self.assertEqual(len(m.find("t:Triggers/t:CalendarTrigger/t:ScheduleByMonth/t:Months", NS)), 12)
        once = {**self.plan, "when": {"kind": "once", "at": "2026-11-20T09:00"}}
        o = ET.fromstring(sc.windows_xml(once, Path("/h"), "u").split("\n", 1)[1])
        self.assertEqual(o.find("t:Triggers/t:TimeTrigger/t:StartBoundary", NS).text, "2026-11-20T09:00:00")

    def test_cron_and_launchd(self):
        rep = {**self.plan, "when": {"kind": "interval", "every": 30, "unit": "minutes", "from": "09:00", "to": "10:30", "days": [0, 4]}}
        lines = sc.cron_lines([self.plan, rep, {**self.plan, "id": "off", "enabled": False}], Path("/home/u/Trapyze"))
        self.assertTrue(lines[0].startswith("30 7 * * 1,2,3,4,5 "))
        self.assertIn("fire abc123", lines[0])
        self.assertEqual([line.split(" * * ")[0] for line in lines[1:]], ["0 9,10", "30 9,10"])
        self.assertFalse(any("trapyze:off" in line for line in lines))
        last = {**self.plan, "when": {"kind": "monthly", "day": "last", "time": "20:00"}}
        self.assertTrue(sc.cron_lines([last], Path("/h"))[0].startswith("0 20 28-31 * * "))
        import plistlib
        data = plistlib.loads(sc.launchd_plist(self.plan, Path("/h")).encode())
        self.assertEqual(len(data["StartCalendarInterval"]), 5)
        self.assertEqual(data["StartCalendarInterval"][0], {"Weekday": 1, "Hour": 7, "Minute": 30})

    def test_crontab_keeps_other_lines(self):
        calls = []
        existing = "MAILTO=me\n0 3 * * * backup.sh\n\n" + sc.CRON_BEGIN + "\nold line\n" + sc.CRON_END + "\n"

        def run(cmd, **kw):
            calls.append((cmd, kw.get("input")))
            if cmd == ["crontab", "-l"]:
                return subprocess.CompletedProcess(cmd, 0, existing, "")
            return subprocess.CompletedProcess(cmd, 0, "", "")
        system = sc.System(Path("/h"), platform="linux", run=run)
        system.install(self.plan, [self.plan])
        written = calls[-1][1]
        self.assertIn("0 3 * * * backup.sh", written)
        self.assertNotIn("old line", written)
        self.assertEqual(written.count(sc.CRON_BEGIN), 1)
        system.remove(self.plan, [])
        self.assertNotIn(sc.CRON_BEGIN, calls[-1][1])

    def test_windows_password_goes_through_stdin(self):
        calls = []

        def run(cmd, **kw):
            calls.append((cmd, kw))
            return subprocess.CompletedProcess(cmd, 0, "", "")
        system = sc.System(Path(tempfile.mkdtemp()), platform="win32", run=run)
        with self.assertRaises(sc.NeedsPassword):
            system.install(self.plan, [self.plan])
        system.install(self.plan, [self.plan], password="s3cret-pw")
        cmd, kw = calls[-1]
        self.assertNotIn("s3cret-pw", " ".join(cmd))
        self.assertNotIn("s3cret-pw", json.dumps({k: v for k, v in kw["env"].items() if k.startswith("TZ_")}))
        self.assertEqual(kw["input"], "s3cret-pw\n")
        self.assertEqual(kw["env"]["TZ_PATH"], "\\traPYze\\")

        def refuse(cmd, **kw):
            return subprocess.CompletedProcess(cmd, 1, "", "Register-ScheduledTask : The user name or password is incorrect.")
        with self.assertRaises(OSError) as caught:
            sc.System(Path(tempfile.mkdtemp()), platform="win32", run=refuse).install(self.plan, [], password="x")
        self.assertIn("password is wrong", str(caught.exception))


class DecisionTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="tz-plan-"))
        self.home = Home(self.dir)
        self.home.init(with_examples=False)
        (self.home.scripts / "hello.py").write_text('# /// script\n# [tool.trapyze]\n# name = "Hello"\n# ///\nprint("hi")\n')
        self.plans = sc.Plans(self.home.internal)
        self.tools = self.home.tools()[0]

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def make(self, **more):
        body = {"target_kind": "tool", "target": "hello", "when": {"kind": "weekly", "days": list(range(7)), "times": ["07:30"]}, **more}
        return self.plans.save(body, self.tools, [], Presets(self.home.internal))

    def test_on_time_late_missed_and_only_once(self):
        plan = self.make()
        self.plans._set_fired(plan["id"], dt.datetime(2026, 11, 13, 8, 0))
        at = dt.datetime(2026, 11, 14, 7, 30)
        self.assertEqual(self.plans.due(plan, at - dt.timedelta(minutes=1))[0], "nothing")
        self.assertEqual(self.plans.claim(plan, at + dt.timedelta(minutes=2)), ("run", at))
        self.assertEqual(self.plans.claim(plan, at + dt.timedelta(minutes=3))[0], "nothing")  # not twice
        # Asleep at 07:30 next day, awake at 11:00: catch up...
        self.assertEqual(self.plans.due(plan, dt.datetime(2026, 11, 15, 11, 0)), ("run", dt.datetime(2026, 11, 15, 7, 30)))
        # ...unless the plan skips missed runs; then it's logged as missed.
        skip = self.plans.update(plan["id"], missed="skip")
        self.assertEqual(self.plans.claim(skip, dt.datetime(2026, 11, 15, 11, 0))[0], "missed")
        self.assertEqual(self.plans.history(plan["id"])[0]["status"], "missed")
        off = self.plans.update(plan["id"], enabled=False)
        self.assertEqual(self.plans.due(off, dt.datetime(2026, 11, 16, 7, 31))[0], "nothing")

    def test_new_plan_does_not_count_earlier_times_as_missed(self):
        plan = self.make()
        self.assertNotEqual(self.plans.due(plan, dt.datetime.now())[0], "run")

    def test_save_checks(self):
        with self.assertRaises(StoreError):
            self.make(target="nope")
        with self.assertRaises(StoreError):
            self.make(when={"kind": "once", "at": "2020-01-01T09:00"})
        self.make(name="Daily hello")
        with self.assertRaises(StoreError):
            self.make(name="daily HELLO")

    def test_fire_runs_in_the_background_and_logs(self):
        plan = self.make()
        self.plans._set_fired(plan["id"], dt.datetime(2026, 11, 13, 8, 0))
        code = sc.fire(self.home, plan["id"], now=dt.datetime(2026, 11, 14, 7, 31))
        self.assertEqual(code, 0)
        entry = self.plans.history(plan["id"])[0]
        self.assertEqual((entry["status"], entry["how"], entry["occurrence"]), ("done", "background", "2026-11-14T07:30"))
        self.assertTrue(entry["run_id"])
        self.assertEqual(sc.fire(self.home, plan["id"], now=dt.datetime(2026, 11, 14, 7, 32)), 0)
        self.assertEqual(len(self.plans.history(plan["id"])), 1)  # not twice
        self.assertEqual(sc.fire(self.home, "deleted-plan"), 0)

    def test_fire_a_chain_needing_a_missing_connection_fails_plainly(self):
        (self.home.scripts / "mailer.py").write_text('# /// script\n# [tool.trapyze]\n# name = "Mailer"\n# connections = ["gmail"]\n# ///\nprint("x")\n')
        tools = self.home.tools()[0]
        chain = Chains(self.home.internal).save({"name": "Both", "steps": [{"tool": "hello"}, {"tool": "mailer"}]}, tools, Presets(self.home.internal))
        plan = self.plans.save({"target_kind": "chain", "target": chain.id, "when": {"kind": "weekly", "days": list(range(7)), "times": ["07:30"]}},
                               tools, [chain], Presets(self.home.internal))
        self.assertEqual(sc.fire(self.home, plan["id"], force=True), 1)
        entry = self.plans.history(plan["id"])[0]
        self.assertEqual(entry["status"], "failed")
        self.assertIn("Mailer", entry["note"])
        self.assertIn("vault", entry["note"])


class PlanWebTests(unittest.TestCase):
    setUp = test_web.WebTests.setUp
    tearDown = test_web.WebTests.tearDown
    request = test_web.WebTests.request

    def test_plan_from_the_window(self):
        calls = []
        self.app.system = sc.System(self.home.root, platform="linux",
                                    run=lambda cmd, **kw: calls.append((cmd, kw.get("input"))) or subprocess.CompletedProcess(cmd, 0, "", ""))
        status, prev = self.request("POST", "/api/schedules/preview", {"when": {"kind": "weekly", "days": [0, 1, 2, 3, 4], "times": ["07:30"]}})
        self.assertEqual(prev["sentence"], "Every weekday at 07:30")
        self.assertEqual(len(prev["next"]), 3)
        self.assertEqual(self.request("POST", "/api/schedules/preview", {"when": {"kind": "weekly", "days": [], "times": []}})[0], 400)
        tool = self.request("GET", "/api/tools")[1]["tools"][0]["id"]
        status, data = self.request("POST", "/api/schedules/save", {"target_kind": "tool", "target": tool, "name": "Hello at 7",
                                                                      "when": {"kind": "weekly", "days": list(range(7)), "times": ["07:00"]}})
        self.assertEqual(status, 200, data)
        plan = data["plans"][0]
        self.assertEqual((plan["sentence"], plan["sync"]["ok"], plan["sync"]["by"]), ("Every day at 07:00", True, "cron"))
        self.assertIn("trapyze:" + plan["id"], calls[-1][1])
        status, data = self.request("POST", "/api/schedules/run-now", {"id": plan["id"]})
        self.assertTrue(data["started"])
        deadline = time.time() + 60
        while time.time() < deadline:
            hist = self.request("GET", "/api/tools")[1]["schedule"]["plans"][0]["history"]
            if hist and hist[0]["status"] != "running":
                break
            time.sleep(0.2)
        self.assertEqual((hist[0]["status"], hist[0]["how"]), ("done", "now"))
        status, data = self.request("POST", "/api/schedules/toggle", {"id": plan["id"], "enabled": False})
        self.assertIsNone(data["plans"][0]["next"])
        self.assertNotIn("trapyze:" + plan["id"], calls[-1][1])
        status, data = self.request("POST", "/api/schedules/delete", {"id": plan["id"]})
        self.assertEqual(data["plans"], [])


if __name__ == "__main__":
    unittest.main()

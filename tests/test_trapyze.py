import json
import os
import shutil
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trapyze import Home, LabelError, Run, SettingError, history, read_tool, run_tool  # noqa: E402
from trapyze.cli import main as cli_main  # noqa: E402
from trapyze.locks import Busy, Locks  # noqa: E402
from trapyze.runner import EngineMissing, build_command, find_engine  # noqa: E402

UV = find_engine()


def label(body: str) -> str:
    lines = ["# /// script"] + [("# " + l) if l else "#" for l in textwrap.dedent(body).strip().splitlines()] + ["# ///"]
    return "\n".join(lines) + "\n"


class TempHome(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="tz-test-"))
        self.home = Home(self.dir)
        self.home.init(with_examples=True)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def script(self, name: str, text: str) -> Path:
        path = self.home.scripts / name
        path.write_text(text, encoding="utf-8")
        return path


class LabelTests(TempHome):
    def test_full_label(self):
        tool = read_tool(self.home.scripts / "say_hello.py")
        self.assertEqual(tool.name, "Say hello")
        self.assertEqual(tool.version, "1.0.0")
        self.assertEqual([s.key for s in tool.settings], ["name", "times", "shout"])
        self.assertEqual(tool.defaults(), {"name": "Ada", "times": 3, "shout": False})

    def test_script_without_label_is_still_a_tool(self):
        path = self.script("my_old_script.py", "print('hi')\n")
        tool = read_tool(path)
        self.assertEqual(tool.name, "My old script")
        self.assertEqual(tool.settings, [])

    def test_broken_toml_is_reported_plainly(self):
        path = self.script("broken.py", "# /// script\n# dependencies = [\n# ///\n")
        with self.assertRaises(LabelError) as ctx:
            read_tool(path)
        self.assertIn("can't be read", str(ctx.exception))

    def test_unknown_type(self):
        path = self.script("t.py", label('[tool.trapyze]\n[[tool.trapyze.settings]]\nkey = "x"\ntype = "colour"'))
        with self.assertRaises(LabelError) as ctx:
            read_tool(path)
        self.assertIn("Use one of", str(ctx.exception))

    def test_choice_needs_options(self):
        path = self.script("t.py", label('[[tool.trapyze.settings]]\nkey = "x"\ntype = "choice"'))
        with self.assertRaises(LabelError):
            read_tool(path)

    def test_duplicate_keys(self):
        path = self.script("t.py", label('[[tool.trapyze.settings]]\nkey = "x"\n[[tool.trapyze.settings]]\nkey = "x"'))
        with self.assertRaises(LabelError):
            read_tool(path)

    def test_bad_default_is_caught_at_read_time(self):
        path = self.script("t.py", label('[[tool.trapyze.settings]]\nkey = "n"\ntype = "int"\ndefault = 500\nmax = 100'))
        with self.assertRaises(LabelError) as ctx:
            read_tool(path)
        self.assertIn("Default for 'n'", str(ctx.exception))

    def test_home_lists_problems_without_failing(self):
        self.script("broken.py", "# /// script\n# dependencies = [\n# ///\n")
        tools, problems = self.home.tools()
        self.assertEqual(len(tools), 3)
        self.assertEqual([p.path.name for p in problems], ["broken.py"])


class SettingTests(TempHome):
    def setUp(self):
        super().setUp()
        self.tool = read_tool(self.script("t.py", label('''
            [[tool.trapyze.settings]]
            key = "n"
            label = "Number"
            type = "int"
            default = 5
            min = 1
            max = 10

            [[tool.trapyze.settings]]
            key = "rate"
            type = "float"
            default = 0.5

            [[tool.trapyze.settings]]
            key = "on"
            type = "bool"
            default = true

            [[tool.trapyze.settings]]
            key = "size"
            type = "choice"
            options = ["small", "large"]
            default = "large"

            [[tool.trapyze.settings]]
            key = "day"
            type = "date"
            default = "2026-11-12"

            [[tool.trapyze.settings]]
            key = "who"
            type = "text"
            required = true
            default = "me"
        ''')))

    def test_text_values_are_converted(self):
        v = self.tool.resolve({"n": "7", "rate": "1,5", "on": "no", "size": "small", "day": "2026-01-02"})
        self.assertEqual(v, {"n": 7, "rate": 1.5, "on": False, "size": "small", "day": "2026-01-02", "who": "me"})

    def test_all_problems_reported_together(self):
        with self.assertRaises(SettingError) as ctx:
            self.tool.resolve({"n": "11", "rate": "abc", "on": "maybe", "size": "medium", "day": "12/11", "who": ""})
        lines = str(ctx.exception).splitlines()
        self.assertEqual(len(lines), 6)
        self.assertIn("Number must be between 1 and 10.", lines)

    def test_whole_number_rule(self):
        with self.assertRaises(SettingError):
            self.tool.resolve({"n": "2.5"})


class HomeTests(TempHome):
    def test_init_never_overwrites(self):
        path = self.home.scripts / "say_hello.py"
        path.write_text("print('mine')\n", encoding="utf-8")
        added = self.home.init()
        self.assertEqual(added, [])
        self.assertEqual(path.read_text(encoding="utf-8"), "print('mine')\n")

    def test_find_by_name_or_file(self):
        self.assertEqual(self.home.find("Say Hello").id, "say_hello")
        self.assertEqual(self.home.find("say_hello.py").id, "say_hello")
        with self.assertRaises(LookupError):
            self.home.find("nothing")


class RunnerTests(TempHome):
    engines = [None] + ([UV] if UV else [])

    def test_run_collects_files_events_and_record(self):
        for engine in self.engines:
            with self.subTest(engine=engine):
                tool = self.home.find("say_hello")
                events = []
                result = run_tool(self.home, tool, {"times": "2", "name": "Ada"}, on_event=events.append, engine=engine)
                self.assertTrue(result.ok, result.cause)
                self.assertEqual(result.files, ["greeting.txt"])
                text = (Path(result.output_dir) / "greeting.txt").read_text(encoding="utf-8")
                self.assertEqual(text, "Hello, Ada!\nHello, Ada!\n")
                kinds = [e.kind for e in events]
                self.assertEqual(kinds[0], "started")
                self.assertEqual(kinds[-1], "finished")
                self.assertIn("progress", kinds)
                fractions = [e.fraction for e in events if e.kind == "progress"]
                self.assertEqual(fractions[-1], 1.0)
                record = json.loads((self.home.runs / result.run_id / "record.json").read_text())
                self.assertEqual(record["status"], "done")
                self.assertEqual(record["settings"]["name"], "Ada")

    def test_shared_data_between_tools(self):
        first = run_tool(self.home, self.home.find("demo price data"), {"days": "30"}, engine=None)
        self.assertTrue(first.ok, first.cause)
        self.assertEqual(first.files, [])  # writes shared data, no result files
        self.assertTrue((self.home.data / "demo_prices.sqlite").exists())
        second = run_tool(self.home, self.home.find("price report"), {"lookback": "10"}, engine=None)
        self.assertTrue(second.ok, second.cause)
        self.assertEqual(second.files, ["price_report_10d.csv"])

    def test_failure_is_explained(self):
        self.script("needs_pkg.py", "import some_package_that_is_missing\n")
        result = run_tool(self.home, self.home.find("needs_pkg"), engine=None)
        self.assertEqual(result.status, "failed")
        self.assertIn("some_package_that_is_missing", result.cause)
        self.assertIsNone(result.output_dir)

    def test_cancel_stops_the_tool(self):
        self.script("slow.py", "import time\nprint('start', flush=True)\ntime.sleep(60)\n")
        for engine in self.engines:
            with self.subTest(engine=engine):
                run = Run(self.home, self.home.find("slow"), engine=engine).start()
                time.sleep(0.8)
                t0 = time.monotonic()
                run.cancel()
                result = run.wait(timeout=10)
                self.assertIsNotNone(result)
                self.assertEqual(result.status, "stopped")
                self.assertLess(time.monotonic() - t0, 6)

    def test_scripts_run_in_their_output_folder(self):
        self.script("relative.py", "open('result.txt', 'w').write('x')\n")
        result = run_tool(self.home, self.home.find("relative"), engine=None)
        self.assertEqual(result.files, ["result.txt"])

    def test_engine_needed_for_dependencies(self):
        path = self.script("deps.py", label('dependencies = ["pandas"]'))
        with self.assertRaises(EngineMissing):
            build_command(read_tool(path), {}, engine=None)

    def test_settings_reach_the_script_as_arguments_too(self):
        tool = self.home.find("say_hello")
        cmd = build_command(tool, tool.resolve({"shout": "yes"}), engine=None)
        self.assertEqual(cmd[-6:], ["--name", "Ada", "--times", "3", "--shout", "true"])

    def test_flag_keeps_the_scripts_own_option_names(self):
        path = self.script("legacy.py", label('''
            [[tool.trapyze.settings]]
            key = "smh_weight"
            type = "float"
            flag = "--smh-weight"

            [[tool.trapyze.settings]]
            key = "start"
            type = "date"
            default = "2008-01-01"
        '''))
        tool = read_tool(path)
        cmd = build_command(tool, tool.resolve({"smh_weight": "0.5"}), engine=None)
        self.assertEqual(cmd[-4:], ["--smh-weight", "0.5", "--start", "2008-01-01"])
        # An empty optional setting is left out, so the script's own default applies.
        cmd = build_command(tool, tool.resolve({}), engine=None)
        self.assertNotIn("--smh-weight", cmd)
        bad = self.script("bad.py", label('[[tool.trapyze.settings]]\nkey = "x"\nflag = "x; rm"'))
        with self.assertRaises(LabelError):
            read_tool(bad)

    COMMAND_TOOL = label('''
        [[tool.trapyze.settings]]
        key = "db"
        type = "text"
        default = "{data}/pit.sqlite"
        flag = "--db"

        [[tool.trapyze.settings]]
        key = "verbose"
        type = "bool"
        switch = true
        flag = "-v"
        default = false

        [[tool.trapyze.settings]]
        key = "command"
        type = "choice"
        options = ["update", "asof"]
        positional = true
        required = true

        [[tool.trapyze.settings]]
        key = "day"
        label = "Date"
        type = "date"
        positional = true
        required = true
        only_for = { command = ["asof"] }

        [[tool.trapyze.settings]]
        key = "full"
        type = "bool"
        switch = true
        default = false
        only_for = { command = ["update"] }
    ''') + textwrap.dedent('''
        import sys, json, os
        open("args.json", "w").write(json.dumps(sys.argv[1:]))
        print(os.environ["TRAPYZE_SETTINGS"])
    ''')

    def test_commands_switches_and_only_for(self):
        tool = read_tool(self.script("pit.py", self.COMMAND_TOOL))
        places = {"data": "/D"}
        D_DB = os.path.join("/D", "pit.sqlite")  # file settings use this computer's path style
        v = tool.resolve({"command": "update", "full": "yes", "verbose": "on"}, places)
        self.assertEqual(v, {"db": D_DB, "verbose": True, "command": "update", "full": True})
        cmd = build_command(tool, v, engine=None)[2:]
        self.assertEqual(cmd, ["--db", D_DB, "-v", "update", "--full"])
        v = tool.resolve({"command": "asof", "day": "2009-06-05", "full": "yes"}, places)
        self.assertNotIn("full", v)  # belongs to update only, so it is dropped
        self.assertEqual(build_command(tool, v, engine=None)[2:], ["--db", D_DB, "asof", "2009-06-05"])
        with self.assertRaises(SettingError) as ctx:
            tool.resolve({"command": "asof"}, places)
        self.assertIn("Date needs a value.", str(ctx.exception))
        tool.resolve({"command": "update"}, places)  # the date is not needed for update
        with self.assertRaises(SettingError):
            tool.resolve({}, places)  # the command itself is required

    def test_placeholders_reach_the_script(self):
        self.script("pit.py", self.COMMAND_TOOL)
        result = run_tool(self.home, self.home.find("pit"), {"command": "update"}, engine=None)
        self.assertTrue(result.ok, result.cause)
        args = json.loads((Path(result.output_dir) / "args.json").read_text())
        self.assertEqual(args, ["--db", str(self.home.data.resolve() / "pit.sqlite"), "update"])

    def test_bad_only_for_is_caught(self):
        for body in (
            '[[tool.trapyze.settings]]\nkey = "x"\nonly_for = { nothing = ["a"] }',
            '[[tool.trapyze.settings]]\nkey = "c"\ntype = "choice"\noptions = ["a"]\n'
            '[[tool.trapyze.settings]]\nkey = "x"\nonly_for = { c = ["b"] }',
            '[[tool.trapyze.settings]]\nkey = "x"\ntype = "text"\nswitch = true',
            '[[tool.trapyze.settings]]\nkey = "x"\npositional = true\nflag = "--x"',
        ):
            with self.subTest(body=body):
                with self.assertRaises(LabelError):
                    read_tool(self.script("bad.py", label(body)))

    def test_warning_codes(self):
        self.script("alerts.py", label('[tool.trapyze]\nwarning_codes = [2]') + "print('3 alerts raised')\nraise SystemExit(2)\n")
        result = run_tool(self.home, self.home.find("alerts"), engine=None)
        self.assertEqual(result.status, "warning")
        self.assertTrue(result.ok)
        self.assertIn("3 alerts raised", result.cause)
        self.script("crash.py", label('[tool.trapyze]\nwarning_codes = [2]') + "raise SystemExit(3)\n")
        self.assertEqual(run_tool(self.home, self.home.find("crash"), engine=None).status, "failed")
        with self.assertRaises(LabelError):
            read_tool(self.script("bad.py", label('[tool.trapyze]\nwarning_codes = [0]')))

    def test_history_is_newest_first(self):
        tool = self.home.find("say_hello")
        for n in ("1", "2"):
            run_tool(self.home, tool, {"times": n}, engine=None)
        records = history(self.home)
        self.assertEqual([r["settings"]["times"] for r in records[:2]], [2, 1])


class LockTests(TempHome):
    def test_busy_while_owner_alive_and_stale_lock_taken_over(self):
        locks = Locks(self.home.locks)
        held = locks.acquire(["data/x.db"], owner="Tool A")
        with self.assertRaises(Busy) as ctx:
            locks.acquire(["data/x.db"], owner="Tool B")
        self.assertIn("Tool A", str(ctx.exception))
        # Pretend the owner died: rewrite the lock with a pid that can't exist.
        record = json.loads(held[0].read_text())
        record["pid"] = 999999999
        held[0].write_text(json.dumps(record))
        again = locks.acquire(["data/x.db"], owner="Tool B")
        self.assertEqual(len(again), 1)
        Locks.release(again)

    def test_all_or_nothing(self):
        locks = Locks(self.home.locks)
        held = locks.acquire(["b"], owner="A")
        with self.assertRaises(Busy):
            locks.acquire(["a", "b"], owner="B")
        self.assertEqual(len(list(self.home.locks.glob("*.lock"))), 1)
        Locks.release(held)

    def test_run_refuses_while_shared_data_is_busy(self):
        held = Locks(self.home.locks).acquire(["data/demo_prices.sqlite"], owner="Another run")
        with self.assertRaises(Busy):
            Run(self.home, self.home.find("demo price data"), engine=None).start()
        Locks.release(held)


class ExplainTests(unittest.TestCase):
    def test_messages(self):
        from trapyze.explain import explain

        cases = {
            "error: Failed to fetch: `https://pypi.org/simple/requests/`\n  Caused by: dns error":
                "packages this tool needs couldn't be downloaded",
            "requests.exceptions.ConnectionError: HTTPSConnectionPool": "couldn't connect",
            "ModuleNotFoundError: No module named 'pandas'": "'pandas'",
            "FileNotFoundError: [Errno 2] No such file or directory: 'input.csv'": "input.csv",
            "PermissionError: [Errno 13] Permission denied: 'report.xlsx'": "report.xlsx",
        }
        for tail, expected in cases.items():
            with self.subTest(tail=tail):
                self.assertIn(expected, explain(1, tail.splitlines()).cause)
        self.assertEqual(explain(None, [], cancelled=True).cause, "Stopped by you.")
        self.assertIn("last message was: boom", explain(1, ["x", "boom", ""]).cause)


class CliTests(TempHome):
    @unittest.skipIf(os.name == "nt", "sends a POSIX signal")
    def test_ctrl_c_stops_a_running_tool(self):
        import signal
        import subprocess

        self.script("slow.py", "import time\nfor i in range(60):\n    print(i, flush=True)\n    time.sleep(1)\n")
        env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
        proc = subprocess.Popen(
            [sys.executable, "-m", "trapyze", "--home", str(self.dir), "run", "slow"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env,
        )
        time.sleep(1.5)
        t0 = time.monotonic()
        proc.send_signal(signal.SIGINT)
        out, _ = proc.communicate(timeout=15)
        self.assertLess(time.monotonic() - t0, 8)
        self.assertIn("Stopping…", out)
        self.assertIn("Stopped by you.", out)
        self.assertEqual(history(self.home)[0]["status"], "stopped")

    def test_cli_round_trip(self):
        home = str(self.dir)
        self.assertEqual(cli_main(["--home", home, "list"]), 0)
        self.assertEqual(cli_main(["--home", home, "run", "say hello", "--set", "times=1", "--quiet"]), 0)
        self.assertEqual(cli_main(["--home", home, "run", "say hello", "--set", "times=99"]), 1)
        self.assertEqual(cli_main(["--home", home, "history"]), 0)


if __name__ == "__main__":
    unittest.main()

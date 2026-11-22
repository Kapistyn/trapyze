import os
os.environ.setdefault("TRAPYZE_NO_UPDATE_CHECK", "1")  # never ask GitHub during tests
import http.client
import json
import shutil
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trapyze import Home  # noqa: E402
from trapyze.web.server import make_server  # noqa: E402


class WebTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="tz-web-"))
        self.home = Home(self.dir)
        self.home.init()
        self.server, self.app = make_server(self.home, port=0)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        for live in list(self.app.runs.values()):
            live.run.cancel()
            live.run.wait(10)
        self.server.shutdown()
        self.server.server_close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def request(self, method, path, body=None, token=True, host=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        headers = {"Host": host or f"127.0.0.1:{self.port}", "Content-Type": "application/json"}
        if token:
            headers["X-Trapyze-Token"] = self.app.token
        conn.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers)
        res = conn.getresponse()
        raw = res.read()
        conn.close()
        try:
            return res.status, json.loads(raw)
        except ValueError:
            return res.status, raw.decode("utf-8", "replace")

    def wait_done(self, run_id, timeout=30):
        deadline = time.time() + timeout
        while time.time() < deadline:
            status, data = self.request("GET", f"/api/runs/{run_id}")
            if not data["running"] and data["result"]:
                return data["result"]
            time.sleep(0.1)
        self.fail("run did not finish")

    def test_safety_checks(self):
        self.assertEqual(self.request("GET", "/api/tools", token=False)[0], 403)
        self.assertEqual(self.request("GET", "/api/tools", host="evil.example:80")[0], 403)
        self.assertEqual(self.request("GET", "/", token=False)[0], 403)
        status, page = self.request("GET", f"/?t={self.app.token}", token=False)
        self.assertEqual(status, 200)
        self.assertIn(self.app.token, page)
        self.assertEqual(self.request("GET", "/static/../server.py")[0], 404)
        status, data = self.request("POST", "/api/open", {"path": "/etc/passwd"})
        self.assertEqual(status, 400)
        self.assertIn("only opens files inside", data["error"])

    def test_tools_list(self):
        status, data = self.request("GET", "/api/tools")
        self.assertEqual(status, 200)
        names = [t["name"] for t in data["tools"]]
        self.assertEqual(names, ["Demo price data", "Price report", "Say hello"])
        hello = data["tools"][2]
        self.assertEqual([s["key"] for s in hello["settings"]], ["name", "times", "shout"])
        self.assertIsNone(hello["last"])

    def test_run_stream_and_history(self):
        status, run = self.request("POST", "/api/runs", {"tool": "say_hello", "settings": {"times": "2", "name": "Ada"}})
        self.assertEqual(status, 201, run)
        # Follow the event stream to the end, like the browser does.
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        conn.request("GET", f"/api/runs/{run['run_id']}/events?t={self.app.token}", headers={"Host": f"127.0.0.1:{self.port}"})
        res = conn.getresponse()
        self.assertEqual(res.getheader("Content-Type"), "text/event-stream; charset=utf-8")
        events = []
        for raw in res:
            line = raw.decode("utf-8").strip()
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
        conn.close()
        kinds = [e["kind"] for e in events]
        self.assertEqual(kinds[0], "started")
        self.assertEqual(kinds[-1], "finished")
        self.assertEqual(events[-1]["result"]["status"], "done")
        self.assertEqual(events[-1]["result"]["files"], ["greeting.txt"])
        # The tool now shows its last run and remembers the chosen settings.
        tools = self.request("GET", "/api/tools")[1]["tools"]
        hello = next(t for t in tools if t["id"] == "say_hello")
        self.assertEqual(hello["last"]["status"], "done")
        self.assertEqual(hello["remembered"], {"times": "2", "name": "Ada"})
        runs = self.request("GET", "/api/history")[1]["runs"]
        self.assertEqual(runs[0]["tool_id"], "say_hello")
        log = self.request("GET", f"/api/runs/{run['run_id']}/log")[1]["log"]
        self.assertIn("Wrote 2 greetings", log)

    def test_late_joiner_gets_the_whole_story(self):
        run = self.request("POST", "/api/runs", {"tool": "say_hello", "settings": {"times": "1"}})[1]
        self.wait_done(run["run_id"])
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.request("GET", f"/api/runs/{run['run_id']}/events?t={self.app.token}&after=0", headers={"Host": f"127.0.0.1:{self.port}"})
        body = conn.getresponse().read().decode("utf-8")
        conn.close()
        self.assertIn('"kind": "started"', body)
        self.assertIn('"kind": "finished"', body)

    def test_bad_settings_are_listed(self):
        status, data = self.request("POST", "/api/runs", {"tool": "say_hello", "settings": {"times": "50", "shout": "maybe"}})
        self.assertEqual(status, 400)
        self.assertEqual(len(data["problems"]), 2)
        self.assertIn("How many greetings must be between 1 and 10.", data["problems"])

    def test_stop(self):
        (self.home.scripts / "slow.py").write_text("import time\nfor i in range(60):\n    print(i, flush=True)\n    time.sleep(1)\n")
        run = self.request("POST", "/api/runs", {"tool": "slow", "settings": {}})[1]
        time.sleep(0.8)
        self.assertEqual(self.request("GET", "/api/active")[1]["runs"][0]["run_id"], run["run_id"])
        self.assertEqual(self.request("POST", f"/api/runs/{run['run_id']}/stop")[0], 200)
        self.assertEqual(self.wait_done(run["run_id"], timeout=10)["status"], "stopped")

    def test_busy_shared_data(self):
        (self.home.scripts / "writer.py").write_text(
            '# /// script\n# [tool.trapyze]\n# writes = ["data/x.db"]\n# ///\nimport time\ntime.sleep(3)\n')
        first = self.request("POST", "/api/runs", {"tool": "writer", "settings": {}})
        self.assertEqual(first[0], 201)
        second = self.request("POST", "/api/runs", {"tool": "writer", "settings": {}})
        self.assertEqual(second[0], 409)
        self.assertIn("still writing", second[1]["error"])

    def test_scripts_browser_and_helper_gets_a_tile(self):
        prog = self.home.scripts / "rot"
        prog.mkdir()
        (prog / "rot.py").write_text('# /// script\n# [tool.trapyze]\n# name = "Rot"\n# ///\nimport helper_mod\nprint(1)\n')
        (prog / "helper_mod.py").write_text('def go():\n    import yfinance\n    return yfinance\n')
        (prog / "fair_test.py").write_text('"""Fair test of the rotation."""\nimport argparse\nimport rot\nimport helper_mod\n'
                                           'ap = argparse.ArgumentParser()\nap.add_argument("--csv", default="p.csv")\nif __name__ == "__main__":\n    ap.parse_args()\n')
        files = {f["file"]: f for fo in self.request("GET", "/api/scripts/files")[1]["folders"] if fo["folder"] == "rot" for f in fo["files"]}
        self.assertEqual(files["rot.py"]["status"], "tile")
        self.assertEqual(files["fair_test.py"]["status"], "helper")
        status, state = self.request("POST", "/api/scripts/make-tool", {"rel": "rot/fair_test.py"})
        self.assertEqual((status, state["name"]), (200, "Fair test"))
        text = (prog / "fair_test.py").read_text()
        self.assertIn("[tool.trapyze]", text)
        self.assertNotIn('"rot"', text)  # a sibling file is not a package
        self.assertIn("yfinance", text)  # but what the sibling needs is
        self.assertIn("fair_test", [t["id"].split(".")[-1] for t in state["tools"]])
        self.assertEqual(self.request("POST", "/api/scripts/make-tool", {"rel": "../outside.py"})[0], 400)

    def test_key_file_connection_reaches_the_tool_as_text(self):
        key = "-----BEGIN OPENSSH PRIVATE KEY-----\r\nAAAAB3Nza\r\n-----END OPENSSH PRIVATE KEY-----"
        (self.home.scripts / "needs_ssh.py").write_text(
            '# /// script\n# [tool.trapyze]\n# connections = ["oracle"]\n# ///\n'
            'import os\nt = os.environ["ORACLE_KEY"]\nprint("lines:", len(t.splitlines()), t.startswith("-----BEGIN"), "\\r" in t)\n')
        self.request("POST", "/api/vault/create", {"pin": "917364"})
        status, data = self.request("POST", "/api/connections/save", {"name": "oracle", "kind": "key_file",
                                    "values": {"ORACLE_KEY": "ssh-ed25519 AAAA public half"}, "secret": ["ORACLE_KEY"], "scheduled": True})
        self.assertEqual(status, 400)
        self.assertIn("public half", data["error"])
        status, data = self.request("POST", "/api/connections/save", {"name": "oracle", "kind": "key_file",
                                    "values": {"ORACLE_KEY": "hello"}, "secret": ["ORACLE_KEY"], "scheduled": True})
        self.assertEqual(status, 400)
        status, state = self.request("POST", "/api/connections/save", {"name": "oracle", "kind": "key_file",
                                     "values": {"ORACLE_KEY": key}, "secret": ["ORACLE_KEY"], "scheduled": True})
        self.assertEqual(status, 200)
        self.assertNotIn("AAAAB3Nza", json.dumps(state))
        status, run = self.request("POST", "/api/runs", {"tool": "needs_ssh", "settings": {}, "allow": True})
        self.assertEqual(status, 201, run)

    def test_pickers_start_in_downloads(self):
        from unittest import mock
        from trapyze.web import server as srv
        with mock.patch.object(srv, "downloads_folder", return_value=self.home.data), \
                mock.patch.object(srv.subprocess, "run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = '"x"'
            srv.pick_path("folder", "downloads")
        self.assertEqual(run.call_args[0][0][-1], str(self.home.data))

    def test_library_overview_over_the_api(self):
        f = self.home.scripts / "uses_pandas.py"
        f.write_text('# /// script\n# dependencies = ["pandas>=2"]\n# [tool.trapyze]\n# name = "Uses pandas"\n# ///\nprint(1)\n')
        status, lib = self.request("GET", "/api/library/state")
        self.assertEqual(status, 200)
        self.assertEqual([p["name"] for p in lib["packages"]], ["pandas"])
        self.assertIn("pandas", lib["common"])
        status, lib = self.request("POST", "/api/library/common", {"text": "polars, duckdb"})
        self.assertEqual(lib["common"], ["polars", "duckdb"])
        self.assertEqual(self.request("POST", "/api/library/common", {"text": "x;y"})[0], 400)

    def test_remove_tool_goes_to_bin_and_comes_back(self):
        f = self.home.scripts / "gone_soon.py"
        f.write_text('# /// script\n# [tool.trapyze]\n# name = "Gone soon"\n# ///\nprint("hi")\n')
        status, state = self.request("POST", "/api/bin/remove", {"tool": "gone_soon"})
        self.assertEqual(status, 200)
        self.assertFalse(f.exists())
        self.assertNotIn("gone_soon", [t["id"] for t in state["tools"]])
        items = self.request("GET", "/api/bin/list")[1]["items"]
        self.assertEqual([i["name"] for i in items], ["Gone soon"])
        self.assertEqual(items[0]["days_left"], 30)
        status, back = self.request("POST", "/api/bin/restore", {"id": items[0]["id"]})
        self.assertEqual((status, back["restored"]), (200, "Gone soon"))
        self.assertTrue(f.exists())
        self.assertEqual(self.request("GET", "/api/bin/list")[1]["items"], [])

    def test_bin_forgets_after_thirty_days(self):
        import json as _j, time as _t
        f = self.home.scripts / "old_one.py"
        f.write_text('# /// script\n# [tool.trapyze]\n# ///\nprint(1)\n')
        self.request("POST", "/api/bin/remove", {"tool": "old_one"})
        slot = next((self.home.internal / "bin").iterdir())
        info = _j.loads((slot / "info.json").read_text())
        info["removed"] = _t.time() - 31 * 86400
        (slot / "info.json").write_text(_j.dumps(info))
        self.assertEqual(self.request("GET", "/api/bin/list")[1]["items"], [])
        self.assertFalse(slot.exists())

    def test_env_file_sorted_into_services(self):
        env = self.home.scripts.parent / "all.env"
        env.write_text("TIINGO_API_KEY=tt-111\nFMP_API_KEY=ff-222\nTELEGRAM_BOT_TOKEN=bb-1\nTELEGRAM_HOME_CHANNEL=42\nTAVILY_API_KEY=tv-3\nYOUR_API_KEY=your_key\n")
        self.request("POST", "/api/vault/create", {"pin": "917364"})
        status, plan = self.request("POST", "/api/connections/env-plan", {"path": str(env)})
        self.assertEqual(status, 200)
        self.assertEqual({i["preset"] for i in plan["items"]}, {"tiingo", "fmp"})
        self.assertNotIn("tt-111", json.dumps(plan))
        self.assertEqual({g["name"] for g in plan["groups"]}, {"telegram", "tavily"})
        state = self.request("POST", "/api/connections/env-apply",
                             {"path": str(env), "chosen": ["TIINGO_API_KEY", "FMP_API_KEY", "g:telegram", "g:tavily"], "scheduled": True})[1]
        self.assertEqual(sorted(state["imported"]), ["fmp", "tavily", "telegram", "tiingo"])
        tg = {c["name"]: c for c in state["connections"]}["telegram"]
        self.assertEqual({v["name"]: v["secret"] for v in tg["variables"]}, {"TELEGRAM_BOT_TOKEN": True, "TELEGRAM_HOME_CHANNEL": False})
        names = {c["name"]: c for c in state["connections"]}
        self.assertEqual(names["tiingo"]["api"]["preset"], "tiingo")
        self.assertNotIn("tt-111", json.dumps(state))
        env.write_text("TIINGO_API_KEY=tt-999\n")
        plan = self.request("POST", "/api/connections/env-plan", {"path": str(env)})[1]
        self.assertEqual(plan["items"][0]["action"], "update")

    def test_vault_flow_unlock_allow_and_masking(self):
        (self.home.scripts / "uses_key.py").write_text(
            '# /// script\n# [tool.trapyze]\n# connections = ["fmp"]\n# ///\n'
            'import os\nprint("key:", os.environ["FMP_API_KEY"])\n')
        # No vault yet: a plain explanation.
        status, data = self.request("POST", "/api/runs", {"tool": "uses_key", "settings": {}})
        self.assertEqual(status, 400)
        self.assertIn("no vault yet", data["error"])
        self.assertEqual(self.request("POST", "/api/vault/create", {"pin": "123"})[0], 400)
        state = self.request("POST", "/api/vault/create", {"pin": "917364"})[1]
        self.assertTrue(state["exists"] and state["unlocked"])
        status, data = self.request("POST", "/api/runs", {"tool": "uses_key", "settings": {}})
        self.assertIn("isn't set up yet", data["error"])
        state = self.request("POST", "/api/connections/save", {
            "name": "fmp", "kind": "api_key", "values": {"FMP_API_KEY": "secret-value-123"},
            "secret": ["FMP_API_KEY"], "scheduled": True})[1]
        self.assertEqual(state["connections"][0]["variables"][0]["value"], None)  # never sent back
        # Locked: the browser is asked for the PIN.
        self.request("POST", "/api/vault/lock", {})
        status, data = self.request("POST", "/api/runs", {"tool": "uses_key", "settings": {}})
        self.assertEqual((status, data["need"]), (423, "unlock"))
        status, data = self.request("POST", "/api/vault/unlock", {"pin": "000000"})
        self.assertEqual(status, 403)
        self.assertEqual(self.request("POST", "/api/vault/unlock", {"pin": "917364"})[0], 200)
        # First use: permission needed, then allowed.
        status, data = self.request("POST", "/api/runs", {"tool": "uses_key", "settings": {}})
        self.assertEqual((status, data["need"], data["connections"]), (428, "allow", ["fmp"]))
        status, run = self.request("POST", "/api/runs", {"tool": "uses_key", "settings": {}, "allow": True})
        self.assertEqual(status, 201)
        result = self.wait_done(run["run_id"])
        self.assertEqual(result["status"], "done")
        log = self.request("GET", f"/api/runs/{run['run_id']}/log")[1]["log"]
        self.assertIn("key: ••••••", log)
        self.assertNotIn("secret-value-123", log)
        # Allowed now: no question the second time.
        self.assertEqual(self.request("POST", "/api/runs", {"tool": "uses_key", "settings": {}})[0], 201)
        connections = self.request("GET", "/api/vault")[1]["connections"]
        self.assertEqual(connections[0]["allowed"], ["uses_key"])

    def test_env_import(self):
        env = self.dir / "old.env"
        env.write_text("SERVICE_TOKEN=tok_abc_999\nREGION=eu\n")
        self.request("POST", "/api/vault/create", {"pin": "917364"})
        preview = self.request("POST", "/api/connections/preview-env", {"path": str(env)})[1]
        self.assertEqual(preview["variables"], [{"name": "SERVICE_TOKEN", "secret": True, "set": True}, {"name": "REGION", "secret": False, "set": True}])
        state = self.request("POST", "/api/connections/save", {
            "name": "old", "kind": "custom", "values": {"SERVICE_TOKEN": None, "REGION": None},
            "secret": ["SERVICE_TOKEN"], "scheduled": True, "import_path": str(env)})[1]
        variables = state["connections"][0]["variables"]
        self.assertEqual(variables[0], {"name": "SERVICE_TOKEN", "secret": True, "value": None, "set": True})
        self.assertEqual(variables[1]["value"], "eu")
        self.assertEqual(self.app.vault.values("old")["SERVICE_TOKEN"], "tok_abc_999")


if __name__ == "__main__":
    unittest.main()

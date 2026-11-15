"""The shared API gateway (tz.api), against a small fake web service on this computer."""

import json
import os
import shutil
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trapyze import Home, read_tool  # noqa: E402
from trapyze.apis import check_api, env_name, helper, run_config  # noqa: E402
from trapyze.runner import Run  # noqa: E402
from trapyze.vault import Vault, VaultError, secrets_for  # noqa: E402

KEY = "sk_test_7f3a9c1e5b"
gw = helper()


class Fake(BaseHTTPRequestHandler):
    seen: list = []
    flaky = {"n": 0}

    def log_message(self, *a):
        pass

    def do_GET(self):
        url = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        Fake.seen.append({"path": url.path, "query": q, "headers": dict(self.headers)})
        if url.path == "/v1/quote":
            return self.send(200, {"symbol": q.get("symbol"), "n": len(Fake.seen)})
        if url.path == "/v1/flaky":
            Fake.flaky["n"] += 1
            if Fake.flaky["n"] == 1:
                return self.send(429, {"error": "slow down"}, {"Retry-After": "0"})
            return self.send(200, {"ok": True})
        if url.path == "/v1/soft-daily":
            return self.send(200, {"Information": f"We have detected your API key as {KEY} and our standard API rate limit is 25 requests per day."})
        if url.path == "/v1/refused":
            return self.send(401, {"error": "bad key"})
        return self.send(404, {"error": "nope"})

    def send(self, status, body, headers=None):
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


class GatewayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}/v1"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="tz-gw-"))
        self.db = self.dir / "api.sqlite"
        Fake.seen.clear()
        Fake.flaky["n"] = 0

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def cfg(self, **more):
        return {"base": self.base, "key_in": "query", "key_name": "apikey", "key_var": "FAKE_API_KEY",
                "per_minute": 0, "per_day": 0, "cache_minutes": 10, **more}

    def test_key_added_and_cached_and_counted(self):
        r = gw.call("fake", self.cfg(), KEY, "quote", {"symbol": "AAPL"}, db=self.db)
        self.assertEqual(r.json()["symbol"], "AAPL")
        self.assertFalse(r.from_cache)
        self.assertEqual(Fake.seen[0]["query"]["apikey"], KEY)
        self.assertNotIn(KEY, r.url)  # the address a tool sees has no key
        again = gw.call("fake", self.cfg(), KEY, "quote", {"symbol": "AAPL"}, db=self.db)
        self.assertTrue(again.from_cache)
        self.assertEqual(len(Fake.seen), 1)
        fresh = gw.call("fake", self.cfg(), KEY, "quote", {"symbol": "AAPL"}, cache=False, db=self.db)
        self.assertFalse(fresh.from_cache)
        u = gw.usage(self.db)["fake"]
        self.assertEqual((u["calls"], u["cached"], u["errors"], u["stored"]), (2, 1, 0, 1))
        con = sqlite3.connect(self.db)
        self.assertNotIn(KEY.encode(), b"".join(str(row).encode() for row in con.execute("SELECT * FROM cache")))
        con.close()
        self.assertEqual(gw.clear_cache("fake", self.db), 1)

    def test_key_in_a_header(self):
        cfg = self.cfg(key_in="header", key_name="Authorization", key_prefix="Bearer ")
        gw.call("fake", cfg, KEY, "quote", {"symbol": "MSFT"}, db=self.db)
        self.assertEqual(Fake.seen[0]["headers"]["Authorization"], "Bearer " + KEY)
        self.assertNotIn("apikey", Fake.seen[0]["query"])

    def test_minute_limit_is_shared_and_waits(self):
        con = gw._connect(self.db)
        now = time.time()
        con.executemany("INSERT INTO calls VALUES ('fake', ?, 1)", [(now - 59.6,), (now - 59.5,)])
        con.close()
        started = time.time()
        with mock.patch.object(gw, "step") as told:
            gw.call("fake", self.cfg(per_minute=2), KEY, "quote", {"symbol": "A"}, cache=False, db=self.db)
        self.assertGreaterEqual(time.time() - started, 0.3)
        self.assertEqual(len(Fake.seen), 1)
        told.assert_not_called()  # short waits aren't worth a message

    def test_daily_allowance(self):
        gw.call("fake", self.cfg(per_day=1), KEY, "quote", {"symbol": "A"}, cache=False, db=self.db)
        with self.assertRaises(gw.ApiLimitReached) as caught:
            gw.call("fake", self.cfg(per_day=1), KEY, "quote", {"symbol": "B"}, cache=False, db=self.db)
        self.assertIn("1 calls a day", str(caught.exception))
        self.assertEqual(len(Fake.seen), 1)
        # An answer already in the cache still comes back.
        gw.call("fake", self.cfg(per_day=5), KEY, "quote", {"symbol": "C"}, db=self.db)
        self.assertTrue(gw.call("fake", self.cfg(per_day=2), KEY, "quote", {"symbol": "C"}, db=self.db).from_cache)

    def test_tools_at_the_same_moment_share_the_allowance(self):
        from concurrent.futures import ThreadPoolExecutor

        def one(i):
            try:
                gw.call("fake", self.cfg(per_day=3), KEY, "quote", {"symbol": f"S{i}"}, cache=False, db=self.db)
                return "ok"
            except gw.ApiLimitReached:
                return "limit"
        with ThreadPoolExecutor(8) as pool:
            got = sorted(pool.map(one, range(8)))
        self.assertEqual(got.count("ok"), 3)
        self.assertEqual(len(Fake.seen), 3)

    def test_too_many_requests_is_retried(self):
        with mock.patch.object(gw, "step"):
            r = gw.call("fake", self.cfg(), KEY, "flaky", cache=False, db=self.db)
        self.assertEqual(r.json(), {"ok": True})
        self.assertEqual(gw.usage(self.db)["fake"]["errors"], 1)

    def test_problems_in_plain_words_without_the_key(self):
        with self.assertRaises(gw.ApiError) as caught:
            gw.call("fake", self.cfg(), KEY, "refused", db=self.db)
        self.assertIn("refused", str(caught.exception))
        self.assertEqual(caught.exception.status, 401)
        with self.assertRaises(gw.ApiLimitReached) as caught:
            gw.call("fake", self.cfg(error_keys=["Information"]), KEY, "soft-daily", db=self.db)
        self.assertNotIn(KEY, str(caught.exception))
        self.assertIn("••••••", str(caught.exception))
        with self.assertRaises(gw.ApiError) as caught:
            gw.call("fake", self.cfg(), KEY, "https://evil.example.com/steal", db=self.db)
        self.assertIn("won't send the key", str(caught.exception))
        self.assertEqual(Fake.seen[-1]["path"], "/v1/soft-daily")  # nothing went to the other site

    def test_full_address_on_the_same_site(self):
        r = gw.call("fake", self.cfg(), KEY, self.base + "/quote?symbol=IBM", db=self.db)
        self.assertEqual(r.json()["symbol"], "IBM")

    def test_tz_api_reads_its_settings_from_the_run(self):
        env = {env_name("fake"): json.dumps(self.cfg()), "FAKE_API_KEY": KEY, "TRAPYZE_API_DB": str(self.db),
               "TRAPYZE_RUN_ID": "x"}
        with mock.patch.dict(os.environ, env):
            self.assertEqual(gw.api("fake", "quote", params={"symbol": "NVDA"}).json()["symbol"], "NVDA")
            with self.assertRaises(gw.ApiError) as caught:
                gw.api("other")
            self.assertIn('connections = ["other"]', str(caught.exception))


class ApiSettingsTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="tz-gwv-"))
        self.home = Home(self.dir)
        self.home.init()
        self.vault = Vault(self.home.internal)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_checks(self):
        ok = check_api({"preset": "fmp", "key_var": "FMP_API_KEY"}, ["FMP_API_KEY"])
        self.assertEqual((ok["base"], ok["key_name"], ok["per_day"]), ("https://financialmodelingprep.com/stable", "apikey", 250))
        for bad, words in (
            ({"preset": "fmp", "key_var": "NOPE"}, "which of this connection's values"),
            ({"preset": "other", "base": "http://example.com", "key_var": "K"}, "https://"),
            ({"preset": "fmp", "key_var": "K", "per_day": "lots"}, "whole number"),
            ({"preset": "fmp", "key_var": "K", "cache_minutes": 99999}, "at most a week"),
        ):
            with self.assertRaises(VaultError) as caught:
                check_api(bad, ["K"])
            self.assertIn(words, str(caught.exception))
        self.assertEqual(check_api({"preset": "other", "base": "http://127.0.0.1:8000", "key_in": "none"}, [])["key_in"], "none")

    def test_runs_get_the_settings_but_not_the_key_twice(self):
        self.vault.create("482915")
        self.vault.save_connection("fmp", "api_key", {"FMP_API_KEY": KEY}, ["FMP_API_KEY"], True,
                                   api={"preset": "fmp", "key_var": "FMP_API_KEY", "per_day": 300})
        self.vault.allow("ranker", ["fmp"])
        env, secrets = secrets_for(self.vault, "ranker", "Ranker", ["fmp"])
        cfg = json.loads(env["TRAPYZE_API_FMP"])
        self.assertEqual((cfg["per_day"], cfg["key_var"]), (300, "FMP_API_KEY"))
        self.assertNotIn(KEY, env["TRAPYZE_API_FMP"])
        self.assertNotIn("test", cfg)
        # Unattended: the away store carries the settings too.
        self.vault.lock()
        env, _ = secrets_for(Vault(self.home.internal), "ranker", "Ranker", ["fmp"], unattended=True)
        self.assertIn("TRAPYZE_API_FMP", env)
        self.assertEqual(self.vault.away_values("fmp")[2]["per_day"], 300)

    def test_helper_is_brought_up_to_date(self):
        target = self.home.lib / "trapyze_helper.py"
        target.write_text("# an old helper\n")
        self.home.init(with_examples=False)
        self.assertIn("def api(", target.read_text())


class ToolRunTests(unittest.TestCase):
    """A real tool run: the script calls tz.api() and gets its answer, the key never shows."""

    def test_tool_uses_tz_api(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_port}/v1"
        folder = Path(tempfile.mkdtemp(prefix="tz-gwr-"))
        try:
            home = Home(folder)
            home.init()
            (home.scripts / "asks.py").write_text(
                '# /// script\n# [tool.trapyze]\n# connections = ["fake"]\n# ///\n'
                "import os, trapyze_helper as tz\n"
                'r = tz.api("fake", "quote", params={"symbol": "ASML"})\n'
                'print("got", r.json()["symbol"], "from cache" if r.from_cache else "fresh")\n'
                'print("key is", os.environ["FAKE_API_KEY"])\n')
            vault = Vault(home.internal)
            vault.create("482915")
            vault.save_connection("fake", "api_key", {"FAKE_API_KEY": KEY}, ["FAKE_API_KEY"], False,
                                  api={"preset": "other", "base": base, "key_var": "FAKE_API_KEY", "cache_minutes": 5})
            vault.allow("asks", ["fake"])
            tool = read_tool(home.scripts / "asks.py")
            env, secrets = secrets_for(vault, "asks", tool.name, tool.connections)
            logs = []
            for _ in range(2):
                run = Run(home, tool, engine=None, extra_env=env, secrets=secrets).start()
                result = run.wait(60)
                self.assertEqual(result.status, "done", (run.run_dir / "log.txt").read_text())
                logs.append((run.run_dir / "log.txt").read_text())
            self.assertIn("got ASML fresh", logs[0])
            self.assertIn("got ASML from cache", logs[1])
            self.assertIn("key is ••••••", logs[0])
            self.assertNotIn(KEY, "".join(logs))
            self.assertEqual(gw.usage(home.internal / "api.sqlite")["fake"]["cached"], 1)
        finally:
            server.shutdown()
            server.server_close()
            shutil.rmtree(folder, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

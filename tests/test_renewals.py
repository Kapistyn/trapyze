import datetime as dt
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trapyze import Home  # noqa: E402
from trapyze.apis import PRESETS  # noqa: E402
from trapyze.vault import Vault, VaultError, renewal_info  # noqa: E402

PIN = "482915"


class RenewalTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="tz-renew-"))
        home = Home(self.dir)
        home.init()
        self.vault = Vault(home.internal)
        self.vault.create(PIN)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_counting(self):
        self.assertIsNone(renewal_info(None, 30))
        self.assertIsNone(renewal_info("2026-11-01T10:00:00", None))
        r = renewal_info("2026-11-01T10:00:00", 30, dt.date(2026, 11, 26))
        self.assertEqual((r["expires"], r["days_left"], r["due"]), ("2026-12-01", 5, True))
        self.assertFalse(renewal_info("2026-11-01", 30, dt.date(2026, 11, 25))["due"])
        self.assertEqual(renewal_info("2026-11-01", 30, dt.date(2026, 12, 3))["days_left"], -2)

    def test_clock_restarts_only_when_the_key_changes(self):
        v = self.vault
        v.save_connection("hfdata", "api_key", {"HFDATA_API_KEY": "hfd_one"}, ["HFDATA_API_KEY"], True, renew_days=30)
        conns = v._data["connections"]
        conns["hfdata"]["renewed"] = "2026-10-01T09:00:00"
        v._save()
        v.save_connection("hfdata", "api_key", {"HFDATA_API_KEY": None}, ["HFDATA_API_KEY"], True,
                          description="a new note", replace_from="hfdata", renew_days=30)
        self.assertEqual(conns["hfdata"]["renewed"], "2026-10-01T09:00:00")  # only the note changed
        v.save_connection("hfdata", "api_key", {"HFDATA_API_KEY": "hfd_two"}, ["HFDATA_API_KEY"], True,
                          replace_from="hfdata", renew_days=30)
        self.assertEqual(conns["hfdata"]["renewed"][:10], dt.date.today().isoformat())
        with self.assertRaises(VaultError):
            v.save_connection("x", "api_key", {"X_KEY": "1"}, ["X_KEY"], True, renew_days=0 or -1)

    def test_reminders_work_while_locked_and_hold_no_secrets(self):
        v = self.vault
        v.save_connection("hfdata", "api_key", {"HFDATA_API_KEY": "hfd_secret_value"}, ["HFDATA_API_KEY"], True, renew_days=30)
        v.save_connection("fmp", "api_key", {"FMP_API_KEY": "sk_other"}, ["FMP_API_KEY"], True)
        v._data["connections"]["hfdata"]["renewed"] = (dt.date.today() - dt.timedelta(days=27)).isoformat()
        v._save()
        text = v.renewals_path.read_text()
        self.assertNotIn("hfd_secret_value", text)
        self.assertEqual(list(json.loads(text)), ["hfdata"])
        v.lock()
        r = Vault(v.folder).renewals()
        self.assertEqual((r[0]["name"], r[0]["days_left"], r[0]["due"]), ("hfdata", 3, True))
        listed = None
        v.unlock(PIN)
        listed = next(c for c in v.connections() if c["name"] == "hfdata")
        self.assertEqual(listed["renewal"]["days_left"], 3)

    def test_an_older_hf_connection_gets_its_reminder(self):
        v = self.vault
        api = {"preset": "hfdata", "base": "https://api.hfdatalibrary.com/v1", "key_in": "header", "key_name": "X-API-Key",
               "per_minute": 100, "per_day": 0, "cache_minutes": 0, "key_var": "HFDATA_API_KEY"}
        v.save_connection("hfdata", "api_key", {"HFDATA_API_KEY": "hfd_x"}, ["HFDATA_API_KEY"], True, api=api)
        c = v._data["connections"]["hfdata"]
        c.pop("renew_days", None); c.pop("renewed", None); c["updated"] = "2026-11-17T10:00:00"
        v._save(); v.lock(); v.unlock(PIN)
        c = v._data["connections"]["hfdata"]
        self.assertEqual((c["renew_days"], c["renewed"]), (30, "2026-11-17T10:00:00"))

    def test_hf_preset(self):
        self.assertEqual(PRESETS["hfdata"]["renew_days"], 30)
        self.assertEqual(PRESETS["hfdata"]["per_minute"], 100)


if __name__ == "__main__":
    unittest.main()

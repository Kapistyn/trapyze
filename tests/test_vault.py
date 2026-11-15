import json
import shutil
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trapyze import Home, read_tool, run_tool  # noqa: E402
from trapyze.runner import Run  # noqa: E402
from trapyze.vault import (  # noqa: E402
    Locked, NeedsPermission, NeedsUnlock, Vault, VaultError, WrongPin, mask, parse_env_file, secrets_for,
)

PIN = "482915"


class VaultTests(unittest.TestCase):
    def test_a_new_vault_counts_as_just_used(self):
        # Before: the idle clock started at 0, so on a computer that had been on for a while
        # a new vault looked idle for hours and locked at the next click.
        self.vault.create(PIN)
        self.assertTrue(self.vault.unlocked)
        self.assertLess(self.vault.idle_seconds(), 5)

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="tz-vault-"))
        self.home = Home(self.dir)
        self.home.init()
        self.vault = Vault(self.home.internal)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def make(self):
        self.vault.create(PIN)
        self.vault.save_connection("fmp", "api_key", {"FMP_API_KEY": "sk_live_abcdef123456"}, ["FMP_API_KEY"], True)
        self.vault.save_connection("broker", "sensitive", {"BROKER_USER": "alex", "BROKER_PASSWORD": "hunter2hunter2"},
                                   ["BROKER_PASSWORD"], False)

    def test_create_unlock_and_nothing_in_plain_text(self):
        self.make()
        raw = self.vault.path.read_text() + self.vault.away_path.read_text()
        for secret in ("sk_live_abcdef123456", "hunter2hunter2", "FMP_API_KEY", "alex"):
            self.assertNotIn(secret, raw)
        fresh = Vault(self.home.internal)
        with self.assertRaises(Locked):
            fresh.connections()
        with self.assertRaises(WrongPin):
            fresh.unlock("000111")
        fresh.unlock(PIN)
        names = [c["name"] for c in fresh.connections()]
        self.assertEqual(names, ["broker", "fmp"])
        listed = {c["name"]: c for c in fresh.connections()}
        # Secret values never leave the vault through the listing; plain ones do.
        self.assertIsNone(listed["fmp"]["variables"][0]["value"])
        self.assertEqual(listed["broker"]["variables"][0], {"name": "BROKER_USER", "secret": False, "value": "alex", "set": True})

    def test_vault_file_alone_is_useless(self):
        self.make()
        # Another computer: same vault file and PIN, but a different device key.
        other = Path(tempfile.mkdtemp(prefix="tz-other-"))
        try:
            shutil.copy(self.vault.path, other / "vault.json")
            with self.assertRaises(WrongPin):
                Vault(other).unlock(PIN)
        finally:
            shutil.rmtree(other, ignore_errors=True)

    def test_weak_pins_refused(self):
        for pin in ("123", "111111", "123456", "654321"):
            with self.subTest(pin=pin), self.assertRaises(VaultError):
                Vault(self.home.internal).create(pin)

    def test_edit_keeps_secret_when_left_empty_and_rename_moves_permissions(self):
        self.make()
        self.vault.allow("ranker", ["fmp"])
        self.vault.save_connection("fmp2", "api_key", {"FMP_API_KEY": None}, ["FMP_API_KEY"], True, replace_from="fmp")
        self.assertEqual(self.vault.values("fmp2"), {"FMP_API_KEY": "sk_live_abcdef123456"})
        self.assertEqual(self.vault.allowed("ranker"), {"fmp2"})
        with self.assertRaises(VaultError):
            self.vault.save_connection("broker", "login", {"X": "1"}, [], True)  # name taken

    def test_change_pin(self):
        self.make()
        self.vault.change_pin(PIN, "correct horse battery")
        fresh = Vault(self.home.internal)
        with self.assertRaises(WrongPin):
            fresh.unlock(PIN)
        fresh.unlock("correct horse battery")
        self.assertEqual(fresh.values("fmp")["FMP_API_KEY"], "sk_live_abcdef123456")

    def test_away_store_only_has_scheduled_connections(self):
        self.make()
        fresh = Vault(self.home.internal)  # locked: nobody typed a PIN
        self.assertEqual(fresh.away_values("fmp")[0], {"FMP_API_KEY": "sk_live_abcdef123456"})
        self.assertIsNone(fresh.away_values("broker"))
        env, secret = secrets_for(fresh, "t", "Tool", ["fmp"], unattended=True)
        self.assertEqual(env, {"FMP_API_KEY": "sk_live_abcdef123456"})
        with self.assertRaises(VaultError):
            secrets_for(fresh, "t", "Tool", ["broker"], unattended=True)

    def test_secrets_for_asks_unlock_then_permission(self):
        self.make()
        fresh = Vault(self.home.internal)
        with self.assertRaises(NeedsUnlock):
            secrets_for(fresh, "ranker", "Ranker", ["fmp"])
        fresh.unlock(PIN)
        with self.assertRaises(NeedsPermission) as ctx:
            secrets_for(fresh, "ranker", "Ranker", ["fmp"])
        self.assertEqual(ctx.exception.names, ["fmp"])
        fresh.allow("ranker", ["fmp"])
        env, secret = secrets_for(fresh, "ranker", "Ranker", ["fmp"])
        self.assertEqual(env, {"FMP_API_KEY": "sk_live_abcdef123456"})
        self.assertEqual(secret, ["sk_live_abcdef123456"])
        with self.assertRaises(VaultError) as ctx:
            secrets_for(fresh, "ranker", "Ranker", ["nothing"])
        self.assertIn("isn't set up yet", str(ctx.exception))

    def test_run_gets_the_key_and_logs_never_show_it(self):
        self.make()
        self.vault.allow("leaky", ["fmp"])
        (self.home.scripts / "leaky.py").write_text(textwrap.dedent('''\
            # /// script
            # [tool.trapyze]
            # connections = ["fmp"]
            # ///
            import os
            key = os.environ["FMP_API_KEY"]
            print("got a key of length", len(key))
            print("the key is", key)
            open("out.txt", "w").write("ok")
        '''))
        tool = read_tool(self.home.scripts / "leaky.py")
        env, secret = secrets_for(self.vault, tool.id, tool.name, tool.connections)
        events = []
        run = Run(self.home, tool, engine=None, extra_env=env, secrets=secret).start(events.append)
        result = run.wait(30)
        self.assertTrue(result.ok, result.cause)
        lines = [e.line for e in events if e.kind == "output"]
        self.assertIn("got a key of length 20", lines)
        self.assertIn("the key is ••••••", lines)
        log = Path(result.log).read_text()
        self.assertNotIn("sk_live_abcdef123456", log)
        record = (self.home.runs / result.run_id / "record.json").read_text()
        self.assertNotIn("sk_live_abcdef123456", record)

    def test_env_file_import(self):
        path = self.dir / "price.env"
        path.write_text('# comment\nDATA_SOURCE=yfinance\nexport EODHD_KEY="abc123def"\nBAD LINE\n1BAD=x\n')
        self.assertEqual(parse_env_file(path), {"DATA_SOURCE": "yfinance", "EODHD_KEY": "abc123def"})

    def test_mask(self):
        self.assertEqual(mask("token=abcd1234 and abcd1234", ["abcd1234"]), "token=•••••• and ••••••")

    def test_reset(self):
        self.make()
        self.vault.reset()
        self.assertFalse(self.vault.exists())
        self.assertFalse(self.vault.unlocked)


if __name__ == "__main__":
    unittest.main()

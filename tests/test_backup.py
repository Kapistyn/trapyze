import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from trapyze import backup  # noqa: E402
from trapyze.home import Home  # noqa: E402


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Home(self.tmp.name)
        self.home.scripts.mkdir(parents=True, exist_ok=True)
        (self.home.scripts / "tool.py").write_text("print(1)\n")
        prog = self.home.scripts / "prog"
        prog.mkdir()
        (prog / "main.py").write_text("print(2)\n")
        (prog / "big.sqlite").write_text("data")
        (prog / ".env").write_text("KEY=secret")
        (prog / "my.key").write_text("x")
        (self.home.scripts / "_replaced").mkdir()
        (self.home.scripts / "_replaced" / "old.py").write_text("old")

    def tearDown(self):
        self.tmp.cleanup()

    def files(self):
        out = subprocess.run(["git", "ls-files"], cwd=self.home.scripts, capture_output=True, text=True).stdout.split()
        return set(out)

    def test_backs_up_code_only_and_keeps_history(self):
        done = backup.run(self.home)
        self.assertTrue(done["ok"])
        self.assertEqual(self.files() - {".gitignore"}, {"tool.py", "prog/main.py"})
        self.assertEqual(done["commits"], 1)
        again = backup.run(self.home)
        self.assertIn("Nothing had changed", again["note"])
        (self.home.scripts / "tool.py").write_text("print(3)\n")
        self.assertEqual(backup.run(self.home)["commits"], 2)

    def test_a_private_key_in_a_script_is_held_back(self):
        (self.home.scripts / "oops.py").write_text('K = """-----BEGIN OPENSSH PRIVATE KEY-----\nabc"""\n')
        done = backup.run(self.home)
        self.assertNotIn("oops.py", self.files())
        self.assertIn("oops.py", done["note"])

    def test_remote_address_is_checked(self):
        for bad in ("--upload-pack=x", "https://me:pw@github.com/a/b.git", "not a url", "ftp://x/y"):
            with self.assertRaises(backup.BackupProblem):
                backup.check_remote(bad)
        self.assertEqual(backup.check_remote("git@github.com:me/s.git"), "git@github.com:me/s.git")
        self.assertEqual(backup.check_remote(""), "")

    def test_push_to_a_remote_and_a_failed_push_is_explained(self):
        remote = Path(self.tmp.name) / "remote.git"
        subprocess.run(["git", "init", "--bare", "-b", "main", str(remote)], capture_output=True, check=True)
        settings = backup.read(self.home)
        settings["remote"] = str(remote)
        backup._write(self.home, settings)
        done = backup.run(self.home)
        self.assertIn("sent to your remote", done["note"])
        self.assertTrue(subprocess.run(["git", "--git-dir", str(remote), "log", "--oneline"], capture_output=True, text=True).stdout.strip())
        settings["remote"] = str(Path(self.tmp.name) / "missing.git")
        backup._write(self.home, settings)
        with self.assertRaises(backup.BackupProblem) as ctx:
            backup.run(self.home)
        self.assertIn("Saved here", str(ctx.exception))

    def test_due_only_when_switched_on(self):
        self.assertFalse(backup.due(self.home))
        backup.change(self.home, {"auto": True})
        self.assertTrue(backup.due(self.home))
        backup.run(self.home)
        self.assertFalse(backup.due(self.home))


if __name__ == "__main__":
    unittest.main()

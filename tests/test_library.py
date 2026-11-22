import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from trapyze.home import Home  # noqa: E402
from trapyze.packages import Packages, PackageProblem, common_list, holds_version, save_common


def tool_file(home, name, deps, extra=""):
    p = home.scripts / f"{name}.py"
    d = ", ".join(f'"{x}"' for x in deps)
    p.write_text(f'# /// script\n# dependencies = [{d}]\n# [tool.trapyze]\n# name = "{name}"\n# ///\nprint(1)\n')
    return p


class FakeUv:
    """Records the calls and writes a lock when asked, like uv would."""
    def __init__(self):
        self.calls = []

    def __call__(self, cmd, **kw):
        import subprocess
        self.calls.append(cmd[1:])
        cwd = Path(kw.get("cwd", "."))
        if cmd[1:3] == ["lock", "--script"]:
            script = cwd / cmd[3]
            lock = cwd / (script.name + ".lock")
            n = "2.3.0" if "--upgrade" in cmd else "2.2.0"
            lock.write_text(f'[[package]]\nname = "pandas"\nversion = "{n}"\n')
        return subprocess.CompletedProcess(cmd, 0, "traPYze package test: ok", "")


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Home(self.tmp.name)
        self.home.init(with_examples=False)

    def tearDown(self):
        self.tmp.cleanup()

    def test_overview_groups_versions_and_keeps_asked_versions(self):
        a = tool_file(self.home, "a", ["pandas>=2"])
        b = tool_file(self.home, "b", ["pandas==1.5.3", "requests"])
        a.with_name("a.py.lock").write_text('[[package]]\nname = "pandas"\nversion = "2.2.0"\n')
        b.with_name("b.py.lock").write_text('[[package]]\nname = "pandas"\nversion = "1.5.3"\n')
        pk = Packages(self.home, run=FakeUv(), engine="uv")
        lib = pk.library(self.home.tools()[0])
        pandas = next(p for p in lib["packages"] if p["name"] == "pandas")
        self.assertEqual({v["version"] for v in pandas["versions"]}, {"2.2.0", "1.5.3"})  # both coexist
        fixed = {t["name"]: t["fixed"] for t in pandas["tools"]}
        self.assertEqual(fixed, {"a": False, "b": True})
        self.assertTrue(holds_version("x==1") and holds_version("x<2") and not holds_version("x>=2"))

    def test_update_all_updates_pinned_tools_and_skips_running(self):
        a = tool_file(self.home, "a", ["pandas"])
        b = tool_file(self.home, "b", ["pandas"])
        for p in (a, b):
            p.with_name(p.name + ".lock").write_text('[[package]]\nname = "pandas"\nversion = "2.2.0"\n')
        pk = Packages(self.home, run=FakeUv(), engine="uv")
        seen = []
        res = pk.update_all(self.home.tools()[0], {"b"}, seen.append)
        by = {r["tool"]: r["status"] for r in res}
        self.assertEqual(by, {"a": "updated", "b": "skipped"})
        self.assertIn("2.3.0", a.with_name("a.py.lock").read_text())
        self.assertIn("2.2.0", b.with_name("b.py.lock").read_text())

    def test_common_list_and_warm(self):
        self.assertIn("pandas", common_list(self.home))
        self.assertEqual(save_common(self.home, ["polars", " duckdb ", "polars", ""]), ["polars", "duckdb"])
        with self.assertRaises(PackageProblem):
            save_common(self.home, ["bad;rm -rf"])
        uv = FakeUv()
        Packages(self.home, run=uv, engine="uv").warm(common_list(self.home))
        self.assertEqual(uv.calls[0][:2], ["pip", "install"])
        self.assertIn("polars", uv.calls[0])


if __name__ == "__main__":
    unittest.main()

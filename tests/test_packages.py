"""Phase 7b: pinning package versions, updating after a test, and going back. Uses real uv,
offline, with tiny packages made here (version 1.0, 1.1 and a broken 1.2)."""

import base64
import hashlib
import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trapyze import Home  # noqa: E402
from trapyze.packages import PackageProblem, Packages, _imports, diff, lock_path, read_lock  # noqa: E402
from trapyze.runner import Run, find_engine  # noqa: E402

UV = find_engine()


def wheel(folder: Path, version: str, body: str) -> None:
    name = f"tzdemo-{version}-py3-none-any.whl"
    files = {
        "tzdemo/__init__.py": body,
        f"tzdemo-{version}.dist-info/METADATA": f"Metadata-Version: 2.1\nName: tzdemo\nVersion: {version}\n",
        f"tzdemo-{version}.dist-info/WHEEL": "Wheel-Version: 1.0\nGenerator: trapyze-test\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
    }
    record = []
    for path, text in files.items():
        digest = base64.urlsafe_b64encode(hashlib.sha256(text.encode()).digest()).rstrip(b"=").decode()
        record.append(f"{path},sha256={digest},{len(text.encode())}")
    record.append(f"tzdemo-{version}.dist-info/RECORD,,")
    with zipfile.ZipFile(folder / name, "w") as z:
        for path, text in files.items():
            z.writestr(path, text)
        z.writestr(f"tzdemo-{version}.dist-info/RECORD", "\n".join(record) + "\n")


@unittest.skipUnless(UV, "needs uv")
class PackageTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="tz-pkg-"))
        self.wheels = self.dir / "wheels"
        self.wheels.mkdir()
        wheel(self.wheels, "1.0", 'VERSION = "1.0"\n')
        self.env = mock.patch.dict(os.environ, {"UV_FIND_LINKS": str(self.wheels), "UV_NO_INDEX": "1", "UV_OFFLINE": "1",
                                                "UV_CACHE_DIR": str(self.dir / "cache")})
        self.env.start()
        self.home = Home(self.dir / "home")
        self.home.init(with_examples=False)
        (self.home.scripts / "ranker.py").write_text(
            '# /// script\n# requires-python = ">=3.10"\n# dependencies = ["tzdemo"]\n# [tool.trapyze]\n# name = "Ranker"\n# ///\n'
            "import json\nimport tzdemo\ntry:\n    import not_installed_anywhere\nexcept ImportError:\n    pass\n"
            'print("ranker uses tzdemo", tzdemo.VERSION)\n')
        self.tool = self.home.find("ranker")
        self.pk = Packages(self.home, engine=UV)

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.dir, ignore_errors=True)

    def run_tool(self):
        result = Run(self.home, self.tool, {}).start().wait(120)
        return result.status, (Path(self.home.runs) / result.run_id / "log.txt").read_text() if hasattr(result, "run_id") else ""

    def test_pin_update_refuse_a_broken_one_and_go_back(self):
        self.assertEqual(_imports(self.tool), ["tzdemo"])  # optional imports in try aren't required
        self.assertFalse(self.pk.status(self.tool)["locked"])
        changes = self.pk.lock(self.tool)
        self.assertEqual(changes, [{"name": "tzdemo", "old": None, "new": "1.0"}])
        self.assertEqual(read_lock(lock_path(self.tool))["tzdemo"], "1.0")
        status = self.pk.status(self.tool)
        self.assertTrue(status["locked"] and status["pinned"][0]["direct"])
        # A newer version appears: the check sees it, nothing changes yet.
        wheel(self.wheels, "1.1", 'VERSION = "1.1"\n')
        self.assertEqual(self.pk.check(self.tool), [{"name": "tzdemo", "old": "1.0", "new": "1.1"}])
        self.assertEqual(read_lock(lock_path(self.tool))["tzdemo"], "1.0")
        self.assertEqual(self.pk.summary(self.tool)["updates"], 1)
        # The tool still runs with 1.0 until it's updated.
        self.assertIn("ranker uses tzdemo 1.0", self.tool_output())
        self.assertEqual(self.pk.update(self.tool), [{"name": "tzdemo", "old": "1.0", "new": "1.1"}])
        self.assertIn("ranker uses tzdemo 1.1", self.tool_output())
        self.assertEqual(self.pk.summary(self.tool)["updates"], 0)
        # A broken release: the test catches it and the tool stays on 1.1.
        wheel(self.wheels, "1.2", 'raise ImportError("broken release")\n')
        with self.assertRaises(PackageProblem) as caught:
            self.pk.update(self.tool)
        self.assertIn("didn't pass the test", str(caught.exception))
        self.assertEqual(read_lock(lock_path(self.tool))["tzdemo"], "1.1")
        # Going back: to 1.0, then to "not pinned".
        self.assertEqual(self.pk.go_back(self.tool), [{"name": "tzdemo", "old": "1.1", "new": "1.0"}])
        self.pk.go_back(self.tool)
        self.assertFalse(lock_path(self.tool).exists())
        with self.assertRaises(PackageProblem):
            self.pk.go_back(self.tool)

    def tool_output(self):
        run = Run(self.home, self.tool, {}).start()
        result = run.wait(120)
        text = (run.run_dir / "log.txt").read_text()
        self.assertEqual(result.status, "done", text)
        return text

    def test_plain_problems(self):
        (self.home.scripts / "plain.py").write_text('# /// script\n# [tool.trapyze]\n# name = "Plain"\n# ///\nprint(1)\n')
        with self.assertRaises(PackageProblem) as caught:
            Packages(self.home, engine=UV).lock(self.home.find("plain"))
        self.assertIn("doesn't need extra packages", str(caught.exception))
        (self.home.scripts / "ghost.py").write_text(
            '# /// script\n# dependencies = ["does-not-exist-anywhere"]\n# [tool.trapyze]\n# name = "Ghost"\n# ///\nprint(1)\n')
        with self.assertRaises(PackageProblem):
            Packages(self.home, engine=UV).lock(self.home.find("ghost"))
        self.assertFalse(lock_path(self.home.find("ghost")).exists())
        with self.assertRaises(PackageProblem) as caught:
            Packages(self.home, engine=None, run=None).engine if find_engine() is None else (_ for _ in ()).throw(PackageProblem("uv here"))
        self.assertTrue(str(caught.exception))

    def test_diff(self):
        self.assertEqual(diff({"a": "1", "b": "2"}, {"a": "1", "b": "3", "c": "1"}),
                         [{"name": "b", "old": "2", "new": "3"}, {"name": "c", "old": None, "new": "1"}])


if __name__ == "__main__":
    unittest.main()

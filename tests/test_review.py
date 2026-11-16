"""0.14: a look before the first run, AI-written tools, the shared prompt, and zip safety."""
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trapyze import ai  # noqa: E402
from trapyze.importer import _unpack  # noqa: E402

try:
    import test_web as _web
except ImportError:  # run from the project root
    from tests import test_web as _web

SCRIPT = '''# /// script
# requires-python = ">=3.11"
# dependencies = []
#
# [tool.trapyze]
# name = "Folder sizes"
# description = "Lists the biggest folders."
# icon = "chart"
# color = "teal"
# version = "0.1.0"
# ///
import shutil
import urllib.request
import trapyze_helper as tz

tz.progress(1, "Done")
shutil.rmtree(str(tz.output_path("old")), ignore_errors=True)
print("ok")
'''
ANSWER = "It lists the biggest folders.\n\n```python\n" + SCRIPT + "```\n"


class PromptTests(unittest.TestCase):
    def test_docs_carry_the_same_prompt_as_the_app(self):
        # One set of rules: the guide and AGENTS.md hold exactly what traPYze copies for you.
        for name in ("docs/guide.md", "AGENTS.md"):
            text = (ROOT / name).read_text(encoding="utf-8")
            block = text.split("<!-- prompt:start -->")[1].split("<!-- prompt:end -->")[0]
            self.assertIn(ai.write_prompt(), block, f"{name} is out of date: run python tools/sync_prompt.py")

    def test_build_new(self):
        q = ai.build_new("  List my biggest folders  ")
        self.assertTrue(q["text"].endswith("The tool I want:\nList my biggest folders"))
        self.assertIn("ONE Python file", q["system"])
        with self.assertRaises(ai.AIError):
            ai.build_new("hi")

    def test_check_new(self):
        tmp = Path(tempfile.mkdtemp(prefix="tz-new-"))
        try:
            tool, problems = ai.check_new(SCRIPT, tmp)
            self.assertEqual((tool.name, problems), ("Folder sizes", []))
            tool, problems = ai.check_new("print(1)\n", tmp)
            self.assertTrue(any("label" in p for p in problems))
            tool, problems = ai.check_new("def x(:\n", tmp)
            self.assertTrue(any("can't read" in p for p in problems))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class ZipTests(unittest.TestCase):
    def test_a_crafted_zip_cannot_write_outside_its_folder(self):
        tmp = Path(tempfile.mkdtemp(prefix="tz-zip-"))
        try:
            z = tmp / "evil.zip"
            with zipfile.ZipFile(z, "w") as f:
                f.writestr("tool/main.py", "print(1)\n")
                f.writestr("../escaped.py", "x")
                f.writestr("tool/../../escaped2.py", "x")
                f.writestr("/abs/escaped3.py", "x")
                f.writestr("C:/escaped4.py", "x")
                f.writestr("tool\\..\\..\\escaped5.py", "x")
            root = _unpack(z)
            try:
                top = root if root.name != "tool" else root.parent
                names = sorted(p.name for p in top.rglob("*") if p.is_file())
                self.assertEqual(names, ["main.py"])
                self.assertEqual(list(top.parent.glob("escaped*")), [])
                self.assertEqual(list(top.parent.parent.glob("escaped*")), [])
            finally:
                shutil.rmtree(top, ignore_errors=True)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class ReviewWebTests(_web.WebTests):
    def test_ai_written_tool_waits_for_a_look(self):
        self.request("GET", "/api/tools")  # the desktop is arranged, as on a computer in use
        status, data = self.request("POST", "/api/ai/write-prompt", {})
        self.assertEqual(data["prompt"], ai.write_prompt())
        status, data = self.request("POST", "/api/ai/new-prompt", {"description": "List my biggest folders"})
        self.assertIn("List my biggest folders", data["prompt"])
        status, data = self.request("POST", "/api/ai/new-proposal", {"answer": "no code here"})
        self.assertEqual(status, 400)
        status, data = self.request("POST", "/api/ai/new-proposal", {"answer": ANSWER})
        self.assertEqual(status, 200, data)
        p = data["proposal"]
        self.assertEqual((p["name"], p["problems"]), ("Folder sizes", []))
        self.assertIn("Delete files or folders", p["wants"])
        self.assertTrue(any(w.startswith("Use the internet") for w in p["wants"]))

        status, data = self.request("POST", "/api/ai/new-save", {"code": p["code"]})
        self.assertEqual(status, 200, data)
        tid = data["result"]["id"]
        self.assertTrue((self.home.scripts / "folder_sizes.py").exists())
        tool = next(t for t in data["tools"] if t["id"] == tid)
        self.assertTrue(tool["review"])
        self.assertIn(f"tool:{tid}", data["layout"]["new"])

        # It doesn't run, can't be planned and can't be chained until someone has looked.
        status, data = self.request("POST", "/api/runs", {"tool": tid, "settings": {}})
        self.assertEqual((status, data["need"]), (428, "review"))
        self.assertEqual(data["review"]["origin"], "An AI wrote it")
        self.assertIn("Delete files or folders", data["review"]["wants"])
        status, data = self.request("POST", "/api/schedules/save", {"target_kind": "tool", "target": tid, "name": "x",
                                                                    "when": {"kind": "weekly", "days": [0], "times": ["08:00"]}})
        self.assertEqual(status, 400)
        self.assertIn("first", data["error"])

        status, data = self.request("POST", "/api/review/accept", {"tool": tid})
        self.assertFalse(next(t for t in data["tools"] if t["id"] == tid)["review"])
        status, data = self.request("POST", "/api/runs", {"tool": tid, "settings": {}})
        self.assertEqual(status, 201, data)

        # Templates and your own scripts never ask.
        status, data = self.request("POST", "/api/new-tool", {"name": "Mine", "kind": "maintain"})
        self.assertFalse(next(t for t in data["tools"] if t["id"] == data["result"]["id"])["review"])

    def test_built_in_ai_writes_a_tool(self):
        self.app.vault.create("plum-fjord-77")
        with mock.patch.object(ai, "models", return_value=["gemini-3.8-flash"]):
            self.request("POST", "/api/ai/key", {"provider": "gemini", "key": "k" * 20})
        with mock.patch.object(ai, "ask", return_value=ANSWER) as asked:
            status, data = self.request("POST", "/api/ai/new-ask", {"description": "List my biggest folders"})
        self.assertEqual(status, 200, data)
        self.assertIn("ONE Python file", asked.call_args[0][3])
        self.assertEqual(data["proposal"]["name"], "Folder sizes")


class ImportReviewTests(unittest.TestCase):
    setUp = _web.WebTests.setUp
    tearDown = _web.WebTests.tearDown
    request = _web.WebTests.request

    def test_imported_tool_waits_for_a_look(self):
        src = Path(tempfile.mkdtemp(prefix="tz-imprev-")) / "hello_there.py"
        src.write_text("print('hi')\n")
        status, data = self.request("POST", "/api/import/apply", {"path": str(src), "choices": {}})
        self.assertEqual(status, 200, data)
        new = [t for t in data["tools"] if t["review"]]
        self.assertEqual(len(new), 1)
        status, data = self.request("POST", "/api/runs", {"tool": new[0]["id"], "settings": {}})
        self.assertEqual((status, data["review"]["origin"]), (428, "It was imported"))
        shutil.rmtree(src.parent, ignore_errors=True)


for name in [n for n in dir(_web.WebTests) if n.startswith("test_")]:
    setattr(ReviewWebTests, name, None)

if __name__ == "__main__":
    unittest.main()

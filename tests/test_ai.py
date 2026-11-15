"""0.12: AI help (prompts, masking, answers, providers) without touching the internet."""
import io
import json
import shutil
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trapyze import ai  # noqa: E402
from trapyze.label import read_tool  # noqa: E402

try:
    from test_web import WebTests
except ImportError:
    from tests.test_web import WebTests

SCRIPT = ('# /// script\n# dependencies = []\n# [tool.trapyze]\n# name = "Ranker"\n# description = "Ranks"\n# ///\n'
          'import os\nAPI_KEY = "abcd1234efgh5678"\nprint("vault-value-xyz")\n')


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def opener_for(payload, seen):
    def opener(req, timeout=None):
        seen.append(req)
        return FakeResponse(json.dumps(payload).encode())
    return opener


class AITests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="tz-ai-"))
        self.path = self.dir / "ranker.py"
        self.path.write_text(SCRIPT)
        self.tool = read_tool(self.path)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_mask(self):
        text, n = ai.mask(SCRIPT + 'tok = "ghp_' + "b" * 36 + '"\npassword = "your_password"\n', ["vault-value-xyz"])
        self.assertNotIn("abcd1234", text)
        self.assertNotIn("vault-value-xyz", text)
        self.assertNotIn("ghp_bbbb", text)
        self.assertIn('password = "your_password"', text)  # a placeholder isn't a secret
        self.assertEqual(n, 3)

    def test_build(self):
        q = ai.build("explain", self.tool, SCRIPT, secrets=["vault-value-xyz"])
        self.assertIn("Explain what this script does", q["user"])
        self.assertNotIn("abcd1234", q["text"])
        self.assertEqual(q["masked"], 2)
        self.assertNotIn("COMPLETE new script", q["system"])
        q = ai.build("change", self.tool, SCRIPT, request="add  a\nsetting")
        self.assertIn("Change the script as follows: add a setting", q["user"])
        self.assertIn("COMPLETE new script", q["system"])
        with self.assertRaises(ai.AIError):
            ai.build("change", self.tool, SCRIPT, request=" ")
        with self.assertRaises(ai.AIError):
            ai.build("why", self.tool, SCRIPT)
        q = ai.build("why", self.tool, SCRIPT, run={"status": "failed", "exit_code": 1, "settings": {"pw": "vault-value-xyz"},
                                                   "cause": "It stopped."}, log="Traceback\nKeyError: 'x'", secrets=["vault-value-xyz"])
        self.assertIn("KeyError", q["user"])
        self.assertIn("It stopped.", q["user"])
        self.assertNotIn("vault-value-xyz", q["text"])

    def test_extract_and_check(self):
        answer = "- added a setting\n\n```python\n" + SCRIPT.replace("Ranks", "Ranks better") + "```\nshort:\n```\nx=1\n```"
        code = ai.extract_code(answer)
        self.assertIn("Ranks better", code)
        self.assertEqual(ai.check_proposal(code, self.tool, self.dir / "scratch"), [])
        self.assertIsNone(ai.extract_code("no code here"))
        problems = ai.check_proposal("def x(:\n", self.tool, self.dir / "scratch")
        self.assertTrue(any("can't read" in p for p in problems))
        problems = ai.check_proposal(SCRIPT.replace("abcd1234efgh5678", ai.MASK), self.tool, self.dir / "scratch")
        self.assertTrue(any("••••" in p for p in problems))
        bad_label = SCRIPT.replace('# name = "Ranker"', "# name = ")
        self.assertTrue(any("label" in p for p in ai.check_proposal(bad_label, self.tool, self.dir / "scratch")))

    def test_pick_model(self):
        self.assertEqual(ai.pick_model("openrouter", ["a/b", "openrouter/free", "x:free"]), "openrouter/free")
        self.assertEqual(ai.pick_model("gemini", ["gemini-3.6-flash", "gemini-3.8-flash", "gemini-3.8-flash-lite", "gemini-3.9-pro"]), "gemini-3.8-flash")
        self.assertEqual(ai.pick_model("anthropic", ["claude-haiku-5-5", "claude-sonnet-5-5", "claude-sonnet-4-5"]), "claude-sonnet-5-5")
        self.assertEqual(ai.pick_model("openai", ["gpt-5.5", "chat-latest"]), "chat-latest")
        self.assertEqual(ai.pick_model("openai", ["gpt-5.5", "gpt-5.6-mini", "gpt-5.6"]), "gpt-5.6")
        self.assertEqual(ai.pick_model("gemini", []), "")

    def test_ask_openai_style_and_anthropic(self):
        seen = []
        text = ai.ask("gemini", "k", "gemini-x", "sys", "hi", opener=opener_for({"choices": [{"message": {"content": "Hello"}}]}, seen))
        self.assertEqual(text, "Hello")
        req = seen[0]
        self.assertTrue(req.full_url.endswith("/v1beta/openai/chat/completions"))
        self.assertEqual(req.get_header("Authorization"), "Bearer k")
        self.assertEqual(json.loads(req.data)["messages"][0], {"role": "system", "content": "sys"})
        seen = []
        text = ai.ask("anthropic", "k", "claude-x", "sys", "hi", opener=opener_for({"content": [{"type": "text", "text": "Hi"}]}, seen))
        self.assertEqual(text, "Hi")
        self.assertEqual(seen[0].get_header("X-api-key"), "k")
        self.assertEqual(json.loads(seen[0].data)["system"], "sys")

    def test_models_and_errors(self):
        ids = ai.models("gemini", "k", opener=opener_for({"data": [{"id": "models/gemini-3.8-flash"}, {"id": "models/text-embedding-9"}]}, []))
        self.assertEqual(ids, ["gemini-3.8-flash"])

        def refuse(code):
            def opener(req, timeout=None):
                raise urllib.error.HTTPError(req.full_url, code, "x", {}, io.BytesIO(b'{"error": {"message": "nope"}}'))
            return opener
        for code, words in ((401, "refused the key"), (429, "limit"), (404, "doesn't know that model"), (402, "credit")):
            with self.assertRaises(ai.AIError) as ctx:
                ai.ask("openai", "k", "m", "s", "u", opener=refuse(code))
            self.assertIn(words, str(ctx.exception))
        with self.assertRaises(ai.AIError):
            ai.ask("openai", "k", "", "s", "u")


class AIWebTests(WebTests):
    def test_ai_endpoints(self):
        status, data = self.request("POST", "/api/new-tool", {"name": "Fetch AEX", "kind": "collect"})
        tid = data["result"]["id"]
        path = Path(next(t for t in data["tools"] if t["id"] == tid)["path"])

        status, info = self.request("GET", "/api/ai")
        self.assertFalse(info["ready"])
        self.assertIn("copilot", info["chat_sites"])
        status, data = self.request("POST", "/api/ai/prompt", {"tool": tid, "task": "explain"})
        self.assertEqual(status, 200)
        self.assertIn("Fetch AEX", data["prompt"])
        status, data = self.request("POST", "/api/ai/ask", {"tool": tid, "task": "explain"})
        self.assertEqual(status, 400)  # no key yet

        new = path.read_text().replace("Downloading", "Fetching")
        status, data = self.request("POST", "/api/ai/proposal", {"tool": tid, "answer": f"Changed a word.\n```python\n{new}```"})
        self.assertEqual(status, 200)
        self.assertEqual(data["proposal"]["problems"], [])
        self.assertTrue(any(l["kind"] == "add" and "Fetching" in l["text"] for l in data["proposal"]["lines"]))
        status, data = self.request("POST", "/api/ai/proposal", {"tool": tid, "answer": "no code"})
        self.assertEqual(status, 400)
        status, data = self.request("POST", "/api/ai/apply", {"tool": tid, "code": new, "task": "change"})
        self.assertEqual(status, 200)
        self.assertIn("Fetching", path.read_text())
        status, data = self.request("GET", f"/api/versions/{tid}")
        self.assertEqual(data["versions"][0]["reason"], "AI: Change it")
        self.assertGreaterEqual(len(data["versions"]), 2)  # the version before is kept (not twice if unchanged)

        # A key: the vault must be open; then the key is checked, stored and used.
        status, data = self.request("POST", "/api/ai/key", {"provider": "gemini", "key": "k" * 20})
        self.assertIn(status, (400, 423))
        self.app.vault.create("plum-fjord-77")
        with mock.patch.object(ai, "models", return_value=["gemini-3.8-flash", "gemini-3.8-flash-lite"]):
            status, data = self.request("POST", "/api/ai/key", {"provider": "gemini", "key": "k" * 20})
        self.assertEqual(status, 200, data)
        self.assertEqual((data["model"], data["ready"]), ("gemini-3.8-flash", True))
        self.assertIn("ai-gemini", [c["name"] for c in self.app.vault.connections()])
        reply = f"Sure.\n```python\n{new.replace('Fetching', 'Getting')}```"
        with mock.patch.object(ai, "ask", return_value=reply + " " + "k" * 20) as asked:
            status, data = self.request("POST", "/api/ai/ask", {"tool": tid, "task": "change", "request": "say getting"})
        self.assertEqual(status, 200, data)
        self.assertEqual(asked.call_args[0][:3], ("gemini", "k" * 20, "gemini-3.8-flash"))
        self.assertNotIn("k" * 20, data["answer"])  # the key never comes back to the page
        self.assertTrue(any("Getting" in l["text"] for l in data["proposal"]["lines"]))
        self.app.vault.lock()
        status, data = self.request("POST", "/api/ai/ask", {"tool": tid, "task": "explain"})
        self.assertEqual((status, data.get("need")), (423, "unlock"))
        status, data = self.request("POST", "/api/open-url", {"url": "https://evil.example/"})
        self.assertEqual(status, 400)


for name in [n for n in dir(WebTests) if n.startswith("test_")]:
    setattr(AIWebTests, name, None)

if __name__ == "__main__":
    unittest.main()

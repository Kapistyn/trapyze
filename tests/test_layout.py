import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trapyze.label import Tool  # noqa: E402
from trapyze.layout import Layout, suggest, topics  # noqa: E402
from trapyze.store import StoreError  # noqa: E402

try:
    import test_web as _web
except ImportError:  # run from the project root
    from tests import test_web as _web


def tool(name, desc="", deps=(), conns=(), writes=(), reads=None, source=""):
    return Tool(path=Path(f"/x/{name.lower().replace(' ', '_')}.py"), id=name.lower().replace(" ", "-"), name=name,
                description=desc, dependencies=list(deps), connections=list(conns), writes=list(writes),
                reads=reads or {}), source


class SuggestTests(unittest.TestCase):
    def check(self, expected, *args, **kw):
        t, src = tool(*args, **kw)
        self.assertEqual(suggest(t, src), expected, t.name)

    def test_by_what_it_does(self):
        self.check("collect", "Price updater", "Downloads daily prices", deps=["yfinance"], writes=["prices.csv"])
        self.check("analyse", "NDX100 ranker", "Ranks stocks", deps=["pandas"], reads={"prices.csv": "1td"})
        self.check("share", "Morning report", "Mails the top ten", conns=["Gmail"], source="import smtplib")
        self.check("maintain", "Backup outputs", source="shutil.make_archive(x)")
        self.check("maintain", "Hello")  # nothing to go on

    def test_mail_beats_reading(self):
        self.check("share", "Signals mail", reads={"ranks.csv": None}, conns=["gmail"])


class TopicTests(unittest.TestCase):
    def test_recurring_words(self):
        found = topics({"tool:a": "AEX scanner", "tool:b": "AEX mailer", "tool:c": "NDX100 ranker",
                        "tool:d": "ndx100 mood", "tool:e": "Backup"})
        self.assertEqual(sorted(t["name"] for t in found), ["AEX", "NDX100"])  # not "Ndx" next to NDX100
        self.assertEqual(next(t for t in found if t["name"] == "AEX")["items"], ["tool:a", "tool:b"])

    def test_plain_words_need_three(self):
        texts = {"tool:a": "Crypto prices", "tool:b": "Crypto ranker", "tool:c": "Backup", "tool:d": "Mail"}
        self.assertEqual(topics(texts), [])
        texts["tool:e"] = "Crypto mood"
        self.assertEqual([t["name"] for t in topics(texts)], ["Crypto"])

    def test_generic_words_and_everything_words_skipped(self):
        self.assertEqual(topics({"tool:a": "Price updater", "tool:b": "Volume updater"}), [])
        self.assertEqual(topics({"tool:a": "Acme one", "tool:b": "Acme two"}), [])  # in all items: no use as a filter


class LayoutTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="tz-lay-"))
        self.lay = Layout(self.dir)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def shelf(self, view, sid):
        return next(s for s in view["shelves"] if s["id"] == sid)

    def test_first_sorting_then_new(self):
        v = self.lay.arrange({"tool:a": "collect", "tool:b": "share"})
        self.assertEqual(self.shelf(v, "collect")["items"], ["tool:a"])
        self.assertEqual(self.shelf(v, "share")["items"], ["tool:b"])
        self.assertEqual(v["new"], [])
        v = self.lay.arrange({"tool:a": "collect", "tool:b": "share", "tool:c": "analyse"})
        self.assertEqual(v["new"], ["tool:c"])
        self.lay.seen("tool:c", "analyse")
        v = self.lay.arrange({"tool:a": "collect", "tool:b": "share", "tool:c": "analyse"})
        self.assertEqual(v["new"], [])
        self.assertEqual(self.shelf(v, "analyse")["items"], ["tool:c"])

    def test_move_favourite_and_gone_items(self):
        s = {"tool:a": "collect", "tool:b": "collect"}
        self.lay.arrange(s)
        self.lay.move("tool:b", "collect", before="tool:a")
        self.lay.move("tool:a", "share")
        self.lay.favourite("tool:a", True)
        v = self.lay.arrange(s)
        self.assertEqual(self.shelf(v, "collect")["items"], ["tool:b"])
        self.assertEqual(self.shelf(v, "share")["items"], ["tool:a"])
        self.assertEqual(v["favourites"], ["tool:a"])
        v = self.lay.arrange({"tool:b": "collect"})  # tool a was removed
        self.assertEqual(v["favourites"], [])
        self.assertEqual(self.shelf(v, "share")["items"], [])

    def test_shelves(self):
        self.lay.arrange({"tool:a": "maintain"})
        sid = self.lay.add_shelf("  AEX   tools ")
        self.assertEqual(sid, "aex-tools")
        with self.assertRaises(StoreError):
            self.lay.add_shelf("aex tools")
        self.lay.move("tool:a", sid)
        self.lay.rename_shelf(sid, "Research")
        self.lay.move_shelf(sid, -10)
        self.lay.fold_shelf(sid, True)
        v = self.lay.arrange({"tool:a": "maintain"})
        self.assertEqual(v["shelves"][0]["name"], "Research")
        self.assertTrue(v["shelves"][0]["folded"])
        self.lay.delete_shelf(sid)
        v = self.lay.arrange({"tool:a": "maintain"})
        self.assertEqual(v["shelves"][0]["items"], ["tool:a"])  # moved to the first remaining shelf
        self.lay.resort({"tool:a": "maintain"})
        v = self.lay.arrange({"tool:a": "maintain"})
        self.assertEqual(self.shelf(v, "maintain")["items"], ["tool:a"])

    def test_view(self):
        self.lay.set_view("list")
        self.assertEqual(self.lay.arrange({})["view"], "list")
        with self.assertRaises(StoreError):
            self.lay.set_view("tiles")


class LayoutWebTests(_web.WebTests):
    """The /api/layout endpoints on a real server (borrowing WebTests' setup)."""

    def test_layout_endpoints(self):
        status, data = self.request("GET", "/api/tools")
        self.assertEqual(status, 200)
        lay = data["layout"]
        self.assertEqual([s["id"] for s in lay["shelves"]], ["collect", "analyse", "share", "maintain", "apps"])
        keys = {k for s in lay["shelves"] for k in s["items"]}
        self.assertEqual(keys, {f"tool:{t['id']}" for t in data["tools"] if not t["hidden"]})
        key = next(iter(keys))
        status, data = self.request("POST", "/api/layout/favourite", {"key": key, "on": True})
        self.assertEqual(data["layout"]["favourites"], [key])
        status, data = self.request("POST", "/api/layout/move", {"key": key, "shelf": "share"})
        self.assertIn(key, next(s for s in data["layout"]["shelves"] if s["id"] == "share")["items"])
        status, data = self.request("POST", "/api/layout/shelf-add", {"name": "Research"})
        self.assertEqual(data["layout"]["shelves"][-1]["name"], "Research")
        status, data = self.request("POST", "/api/layout/view", {"view": "nope"})
        self.assertEqual(status, 400)
        status, data = self.request("POST", "/api/layout/explode", {})
        self.assertEqual(status, 400)


for name in [n for n in dir(_web.WebTests) if n.startswith("test_")]:
    setattr(LayoutWebTests, name, None)  # run only the layout test here, not WebTests' own again

if __name__ == "__main__":
    unittest.main()

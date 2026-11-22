import json
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from trapyze import storage  # noqa: E402
from trapyze.bin import Bin  # noqa: E402
from trapyze.home import Home  # noqa: E402


def make_run(home, tool, days_ago, status="ok", with_output=True, size=1000):
    started = datetime.now() - timedelta(days=days_ago)
    run_id = f"{started:%Y-%m-%d_%H-%M-%S-%f}_{tool}"
    run_dir = home.runs / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "log.txt").write_text("x" * 100)
    out = None
    if with_output:
        out = home.outputs / tool / f"{started:%Y-%m-%d_%H-%M-%S}"
        out.mkdir(parents=True)
        (out / "result.csv").write_text("y" * size)
    (run_dir / "record.json").write_text(json.dumps({"run_id": run_id, "tool_id": tool, "tool_name": tool.title(), "status": status,
                                                    "started": started.isoformat(timespec="seconds"), "output_dir": str(out) if out else None}))
    return run_id, out, run_dir


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Home(self.tmp.name)
        self.home.init(with_examples=False)
        self.bin = Bin(self.home)

    def tearDown(self):
        self.tmp.cleanup()

    def test_old_runs_go_to_the_bin_but_the_newest_stay(self):
        ids = [make_run(self.home, "maps", d) for d in (90, 60, 45, 10, 1)]
        s = storage.read(self.home)
        s["keep_last"] = 2
        old = {c["run_id"] for c in storage.candidates(self.home, s)}
        self.assertEqual(old, {ids[0][0], ids[1][0], ids[2][0]})  # 90, 60, 45 days; not the newest two
        res = storage.tidy(self.home, self.bin, s)
        self.assertEqual(res["moved"], 3)
        self.assertFalse(ids[0][1].exists() or ids[0][2].exists())
        self.assertTrue(ids[4][1].exists() and ids[3][2].exists())
        self.assertEqual(len(self.bin.items()), 3)

    def test_keep_last_wins_over_age_and_pins_and_running_are_kept(self):
        a = make_run(self.home, "t", 100)
        b = make_run(self.home, "t", 99)
        c = make_run(self.home, "t", 98, status="running")
        s = storage.read(self.home)          # keep_last 5: nothing may go
        self.assertEqual(storage.candidates(self.home, s), [])
        s["keep_last"] = 1
        s["pins"] = [a[0]]
        self.assertEqual({x["run_id"] for x in storage.candidates(self.home, s)}, {b[0]})  # a pinned, c running/newest

    def test_per_tool_days(self):
        make_run(self.home, "fast", 10)
        make_run(self.home, "fast", 9)
        make_run(self.home, "slow", 10)
        make_run(self.home, "slow", 9)
        s = storage.change(self.home, {"keep_last": 1})
        storage.change(self.home, {"tool": "fast", "tool_days": 5})
        self.assertEqual({c["tool_id"] for c in storage.candidates(self.home, storage.read(self.home))}, {"fast"})

    def test_put_back_from_the_bin(self):
        rid, out, run_dir = make_run(self.home, "maps", 90)
        make_run(self.home, "maps", 1)
        s = storage.read(self.home)
        s["keep_last"] = 1
        storage.tidy(self.home, self.bin, s)
        self.assertFalse(out.exists())
        item = self.bin.items()[0]
        self.assertEqual(item["kind"], "results")
        self.bin.restore(item["id"])
        self.assertTrue((out / "result.csv").exists() and (run_dir / "record.json").exists())

    def test_scan_sizes_and_validation(self):
        make_run(self.home, "maps", 90, size=5000)
        (self.home.data / "db.sqlite").write_bytes(b"z" * 2048)
        sc = storage.scan(self.home, self.bin, None)
        self.assertGreaterEqual(sc["areas"]["results"], 5000)
        self.assertEqual(sc["data"][0]["name"], "db.sqlite")
        self.assertEqual(sc["tools"][0]["id"], "maps")
        with self.assertRaises(ValueError):
            storage.change(self.home, {"days": 0})
        self.assertFalse(storage.due(self.home) is False)  # auto is on and nothing ran yet: due


if __name__ == "__main__":
    unittest.main()

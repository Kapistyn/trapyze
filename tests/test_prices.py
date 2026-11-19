"""The shared price cache (tz.prices), against a fake Yahoo Finance on this computer."""

import os
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

try:
    import numpy as np
    import pandas as pd
except ImportError:  # the tests run with pandas (see AGENTS.md); without it, say so instead of failing
    raise unittest.SkipTest("tz.prices() tests need pandas") from None

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trapyze.apis import helper  # noqa: E402

tz = helper()
NY = "America/New_York"


class FakeYahoo:
    """Holds a price history per ticker and answers like yfinance.Ticker(...).history()."""

    def __init__(self):
        self.world: dict[str, pd.DataFrame] = {}
        self.calls: list[tuple] = []
        self.down = False
        self.module = types.ModuleType("yfinance")
        self.module.Ticker = lambda t: _FakeTicker(self, t)

    def daily(self, ticker, days=300, end="2026-11-18"):
        idx = pd.bdate_range(end=end, periods=days, tz=NY)
        c = 100 * np.exp(np.cumsum(np.random.default_rng(len(ticker)).normal(0, 0.01, days)))
        self.world[ticker] = pd.DataFrame({"Open": c * 0.999, "High": c * 1.01, "Low": c * 0.99, "Close": c,
                                           "Adj Close": c, "Volume": np.full(days, 1e6)}, index=idx)

    def hourly(self, ticker, start, hours):
        idx = pd.date_range(start, periods=hours, freq="1h", tz=NY)
        c = np.linspace(400, 410, hours)
        self.world[ticker] = pd.DataFrame({"Open": c, "High": c + 1, "Low": c - 1, "Close": c, "Adj Close": c,
                                           "Volume": np.full(hours, 5e5)}, index=idx)


class _FakeTicker:
    def __init__(self, yahoo, ticker):
        self.y, self.t = yahoo, ticker

    def history(self, period=None, start=None, interval="1d", **kw):
        self.y.calls.append((self.t, interval, start))
        if self.y.down:
            raise ConnectionError("no internet")
        df = self.y.world.get(self.t)
        if df is None:
            return pd.DataFrame()
        if start is not None:
            df = df[df.index >= pd.Timestamp(start, tz=df.index.tz)]
        return df.copy()


class PriceCacheTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="tz-prices-"))
        self.env = mock.patch.dict(os.environ, {"TRAPYZE_DATA_DIR": str(self.dir)})
        self.env.start()
        self.y = FakeYahoo()
        self.mods = mock.patch.dict(sys.modules, {"yfinance": self.y.module})
        self.mods.start()
        self.y.daily("SPY")

    def tearDown(self):
        self.mods.stop()
        self.env.stop()
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_downloads_once_and_reads_the_rest_from_the_cache(self):
        a = tz.prices("SPY", start="2026-01-01")
        b = tz.prices("spy", start="2026-01-01")
        self.assertEqual(len(self.y.calls), 1)
        pd.testing.assert_frame_equal(a, b)
        self.assertEqual(a.index.name, "Date")
        self.assertIsNone(a.index.tz)
        self.assertEqual(list(a.columns), ["Open", "High", "Low", "Close", "Adj Close", "Volume"])
        self.assertTrue((self.dir / "trapyze_prices.sqlite").exists())
        self.assertAlmostEqual(a["Close"].iloc[-1], self.y.world["SPY"]["Close"].iloc[-1])

    def test_older_history_is_added_once(self):
        tz.prices("SPY", start="2026-06-01")
        full = tz.prices("SPY", start="2025-01-01")
        tz.prices("SPY", start="2025-01-01")
        self.assertEqual(len(self.y.calls), 2)
        self.assertEqual(len(full), len(self.y.world["SPY"][self.y.world["SPY"].index >= pd.Timestamp("2025-01-01", tz=NY)]))
        # asking for everything there is, after a partial start, downloads the rest once
        everything = tz.prices("SPY")
        tz.prices("SPY")
        self.assertEqual(len(self.y.calls), 3)
        self.assertEqual(len(everything), len(self.y.world["SPY"]))

    def test_stale_prices_are_updated_with_a_short_download(self):
        tz.prices("SPY", start="2026-01-01")
        self.y.daily("SPY", days=301, end="2026-11-19")    # one new day
        got = tz.prices("SPY", start="2026-01-01", refresh_hours=0)
        ticker, _, start = self.y.calls[-1]
        self.assertGreaterEqual(pd.Timestamp(start), pd.Timestamp("2026-11-08"))   # only the last days again
        self.assertEqual(str(got.index[-1].date()), "2026-11-19")

    def test_a_dividend_rescales_the_older_adjusted_closes(self):
        tz.prices("SPY")
        w = self.y.world["SPY"]
        w.loc[w.index < w.index[-3], "Adj Close"] *= 0.99   # ex-dividend three days ago
        got = tz.prices("SPY", refresh_hours=0)
        np.testing.assert_allclose(got["Adj Close"].to_numpy(), w["Adj Close"].to_numpy(), rtol=1e-9)
        np.testing.assert_allclose(got["Close"].to_numpy(), w["Close"].to_numpy(), rtol=1e-9)
        adj = tz.prices("SPY", adjusted=True)
        self.assertNotIn("Adj Close", adj.columns)
        np.testing.assert_allclose(adj["Close"].to_numpy(), w["Adj Close"].to_numpy(), rtol=1e-9)

    def test_a_split_rescales_prices_and_volume(self):
        tz.prices("SPY")
        w = self.y.world["SPY"]
        old = w.index < w.index[-2]
        for c in ("Open", "High", "Low", "Close", "Adj Close"):
            w.loc[old, c] /= 4
        w.loc[old, "Volume"] *= 4
        got = tz.prices("SPY", refresh_hours=0)
        np.testing.assert_allclose(got["Close"].to_numpy(), w["Close"].to_numpy(), rtol=1e-9)
        np.testing.assert_allclose(got["Volume"].to_numpy(), w["Volume"].to_numpy(), rtol=1e-9)

    def test_without_internet_the_saved_prices_are_used(self):
        saved = tz.prices("SPY")
        self.y.down = True
        again = tz.prices("SPY", refresh_hours=0)
        pd.testing.assert_frame_equal(saved, again)
        with self.assertRaises(tz.PriceError) as e:
            tz.prices("QQQ")
        self.assertIn("internet", str(e.exception))

    def test_unknown_ticker_in_plain_words(self):
        with self.assertRaises(tz.PriceError) as e:
            tz.prices("NOPE")
        self.assertIn("Check the ticker spelling", str(e.exception))

    def test_broker_bars_are_kept_apart_and_read_back(self):
        bars = self.y.world["SPY"].iloc[-20:].drop(columns=["Adj Close"])
        self.assertEqual(tz.save_prices("SPY", bars, interval="1d", source="lynx"), 20)
        got = tz.prices("SPY", source="lynx")
        self.assertEqual(len(got), 20)
        self.assertEqual(self.y.calls, [])                  # never downloads for another source
        self.assertEqual(tz.price_range("SPY", source="lynx")["last"], "2026-11-18")
        self.assertIsNone(tz.price_range("SPY"))
        with self.assertRaises(tz.PriceError):
            tz.prices("QQQ", source="lynx")
        with self.assertRaises(tz.PriceError):
            tz.save_prices("SPY", bars, source="yahoo")

    def test_intraday_bars_are_kept_after_yahoo_drops_them(self):
        start = pd.Timestamp.now(tz=NY).normalize() - pd.Timedelta(days=20)
        self.y.hourly("ES=F", start, 24 * 10)
        first = tz.prices("ES=F", interval="1h")
        self.assertEqual(str(first.index.tz), NY)
        self.assertEqual(first.index.name, "Datetime")
        # Yahoo moves its window on: only the newest bars are offered now
        self.y.world["ES=F"] = self.y.world["ES=F"].iloc[-48:]
        later = tz.prices("ES=F", interval="1h", refresh_hours=0)
        self.assertEqual(len(later), len(first))
        self.assertEqual(later.index[0], first.index[0])

    def test_missing_yfinance_is_explained(self):
        with mock.patch.dict(sys.modules, {"yfinance": None}):
            with self.assertRaises(tz.PriceError) as e:
                tz.prices("DIA")
        self.assertIn('"yfinance"', str(e.exception))


if __name__ == "__main__":
    unittest.main()

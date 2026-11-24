"""Breakout rules, score, liquidity, intraday rules, base rates, scenarios and the chart writer (all on FAKE series)."""

import os
import re
import unittest

from _load import TempData, series
import breakout as B
import chart as CH


def base_then_break(n_trend=60, base=20, mult=3.0):
    """FAKE: steady uptrend, a tight base around 100, then a high-volume close above it."""
    up = [60 + 40.0 * i / n_trend for i in range(n_trend)]
    flat = [99.0 + (i % 2) for i in range(base)]
    c = up + flat + [104.0]
    v = [100000] * (len(c) - 1) + [int(100000 * mult)]
    dp = [40.0] * (len(c) - 1) + [60.0]
    h = [x * 1.005 for x in c]
    l = [x * 0.995 for x in c]
    return series(c, v, h, l, dp=dp)


class Rules(unittest.TestCase):
    def test_tight_base_volume_highs(self):
        s = base_then_break()
        hits = B.rules(s, len(s["c"]) - 1)
        for k in ("hi20", "hi50", "base", "vol", "deliv"):
            self.assertIn(k, hits, k)
        r = B.score(s)
        self.assertEqual(r["setup"], "hi50")
        self.assertEqual(r["rules"], ["base", "deliv", "gap", "hi20", "hi50", "vol"])  # opens at 104 > prior high 100.5: gap held
        self.assertEqual(r["score"], 20 + 15 + 15 + 5 + 6)  # hi50 (max of the highs) + base + vol + deliv + gap; no EMA200 yet
        self.assertEqual(r["level"], 100.0)
        self.assertAlmostEqual(r["pct_above"], 4.0)
        self.assertEqual(r["rvol"], 3.0)

    def test_no_trigger_returns_none(self):
        s = series([100.0] * 40)
        self.assertIsNone(B.score(s))

    def test_gap_and_inside(self):
        c = [100.0] * 30 + [100.0, 100.0, 104.0]
        o = list(c)
        h = [101.0] * 30 + [102.0, 101.0, 106.0]   # bar -2 inside bar -3
        l = [99.0] * 30 + [98.0, 99.5, 103.0]      # last bar low 103 > previous high 101 -> gap held
        o[-1] = 103.5
        s = series(c, highs=h, lows=l, opens=o)
        hits = B.rules(s, len(c) - 1)
        self.assertEqual(hits["gap"][0], 101.0)
        self.assertEqual(hits["inside"][0], 101.0)

    def test_retest(self):
        c = [100.0] * 30 + [101.0, 103.0, 104.0, 105.0, 104.0, 103.0, 102.0, 101.5, 100.9, 101.2, 101.6]
        l = [x * 0.995 for x in c]
        s = series(c, lows=l)
        hits = B.rules(s, len(c) - 1)
        self.assertIn("retest", hits)
        self.assertEqual(hits["retest"][0], 100.0)

    def test_liquidity(self):
        s = base_then_break()
        self.assertIn("turnover ₹3.1 Cr", B.liquid(s, B.DEFAULTS, {}))   # 104 x 300000 = ₹312 lakh = ₹3.1 Cr < ₹5 Cr
        s["t"][-1] = 600.0
        self.assertIsNone(B.liquid(s, B.DEFAULTS, {}))
        self.assertEqual(B.liquid(s, B.DEFAULTS, {"etf": True}), "ETF")
        s["series"] = "BE"
        self.assertIn("series BE", B.liquid(s, B.DEFAULTS, {}))
        s["series"], s["c"][-1] = "EQ", 10.0
        self.assertIn("price", B.liquid(s, B.DEFAULTS, {}))

    def test_intraday(self):
        bars = [["2026-11-23T09:%02d:00+05:30" % m, 100, 101, 99, 100.5, 1000] for m in (15, 20, 25)]
        bars += [["2026-11-23T09:30:00+05:30", 100.5, 102, 100.4, 101.8, 3000]]
        x = B.intraday(bars, prev_high=101.5, avg_daily_vol=20000, or_minutes=15, elapsed_frac=0.1)
        self.assertEqual((x["or_high"], x["or_low"]), (101, 99))
        self.assertTrue(x["orb"])
        self.assertTrue(x["pdh_break"])
        self.assertEqual(x["rvol"], 3.0)  # 6000 / (20000 * 0.1)


class History(unittest.TestCase):
    def _repeating(self, cycles=12):
        """FAKE: the same 25-bar pattern repeated: a base, a breakout, then a 5-bar drift."""
        c = []
        for k in range(cycles):
            b = 100.0 + k
            c += [b + 0.2 * (i % 2) for i in range(18)] + [b + 1.5] + [b + 1.5 + 0.3 * i for i in range(1, 7)]
        return series(c)

    def test_base_rates(self):
        s = self._repeating()
        r = B.base_rates(s, "base", horizons=(1, 5), start=20)
        self.assertGreaterEqual(r["events"], 8)
        h1 = r["horizons"][1]
        self.assertEqual(h1["held_pct"], 100.0)
        self.assertGreater(h1["median_pct"], 0)

    def test_scenarios(self):
        s = self._repeating()
        sc = B.scenarios(s, "base", horizon=5, min_n=5, start=20)
        self.assertTrue(sc["ok"])
        self.assertEqual(sc["bull"]["prob"] + sc["base"]["prob"] + sc["bear"]["prob"], 100)
        few = B.scenarios(s, "base", horizon=5, min_n=500, start=20)
        self.assertFalse(few["ok"])
        self.assertIn("no probabilities", few["why"])


class Chart(unittest.TestCase):
    def test_writes_self_contained_svg(self):
        s = base_then_break()
        with TempData() as d:
            p = CH.write_chart(os.path.join(d, "FAKE.html"), s["d"], s["o"], s["h"], s["l"], s["c"], s["v"], "FAKE daily", "synthetic",
                               {"EMA20": [None] * 10 + s["c"][10:]}, [(100.0, "breakout")], [(s["d"][-5], "fake event")])
            with open(p, encoding="utf-8") as f:
                html = f.read()
        self.assertIn("<svg", html)
        self.assertEqual(html.count("<rect"), 2 * len(s["c"]))
        self.assertIn("polyline", html)
        self.assertIn("breakout 100.00", html)
        self.assertIn("fake event", html)
        self.assertIn("prefers-color-scheme:dark", html)
        self.assertIsNone(re.search(r"<script|src=|href=\"http", html))


if __name__ == "__main__":
    unittest.main()

"""Indicators against values computed by hand (the arithmetic is in the comments)."""

import unittest

import _load  # noqa: F401  (puts lib/ on the path)
import indicators as I


class Indicators(unittest.TestCase):
    def test_sma_ema(self):
        self.assertEqual(I.sma([1, 2, 3, 4], 2), [None, 1.5, 2.5, 3.5])
        # seed = mean(1,2,3) = 2; k = 0.5: 4*.5+2*.5 = 3; 5*.5+3*.5 = 4
        self.assertEqual(I.ema([1, 2, 3, 4, 5], 3), [None, None, 2.0, 3.0, 4.0])
        self.assertEqual(I.ema([None, 1, 2, 3], 3), [None, None, None, 2.0])

    def test_rsi_wilder(self):
        # changes +1 +1 -1 +2; n=2: idx2 ag=1 al=0 -> 100; idx3 ag=.5 al=.5 -> 50; idx4 ag=1.25 al=.25 -> 100-100/6
        r = I.rsi([1, 2, 3, 2, 4], 2)
        self.assertEqual(r[:2], [None, None])
        self.assertEqual(r[2], 100.0)
        self.assertAlmostEqual(r[3], 50.0)
        self.assertAlmostEqual(r[4], 83.3333333, 5)

    def test_atr(self):
        # TR = [1, 1.5, 2]; first = mean(1, 1.5) = 1.25; next = (1.25 + 2)/2 = 1.625
        self.assertEqual(I.atr([10, 11, 12], [9, 10, 10], [9.5, 10.5, 11.5], 2), [None, 1.25, 1.625])

    def test_macd_flat_is_zero(self):
        line, sig, hist = I.macd([100.0] * 40)
        self.assertAlmostEqual(line[-1], 0.0)
        self.assertAlmostEqual(sig[-1], 0.0)
        self.assertAlmostEqual(hist[-1], 0.0)
        self.assertIsNone(line[24])
        self.assertIsNotNone(line[25])

    def test_bollinger_width(self):
        # mean 2, population sd sqrt(2/3) = 0.81650; width = 4*sd/2*100 = 163.299
        self.assertAlmostEqual(I.bb_width([1, 2, 3], 3)[-1], 163.2993, 3)

    def test_adx(self):
        # TR 1,1.5,2,2.5,3; +DM 0,1,1,0,2; -DM 0,0,0,1,0. n=2:
        # i2: sTR 3.5 s+ 2 s- 0 -> DX 100; i3: sTR 4.25 s+ 1 s- 1 -> DX 0; i4: sTR 5.125 s+ 2.5 s- .5 -> +DI 48.78 -DI 9.76 DX 66.667
        # ADX[3] = mean(100, 0) = 50; ADX[4] = (50 + 66.667)/2 = 58.333
        ax, p, m = I.adx([10, 11, 12, 11, 13], [9, 10, 10, 9, 11], [9.5, 10.5, 11.5, 10, 12], 2)
        self.assertAlmostEqual(ax[3], 50.0)
        self.assertAlmostEqual(ax[4], 58.3333, 3)
        self.assertAlmostEqual(p[4], 48.7805, 3)
        self.assertAlmostEqual(m[4], 9.7561, 3)

    def test_obv_vwap_pivots(self):
        self.assertEqual(I.obv([1, 2, 2, 1], [10, 20, 30, 40]), [0.0, 20.0, 20.0, -20.0])
        # typical 2 (v10) and 5 (v30): (20 + 150) / 40 = 4.25
        self.assertEqual(I.vwap([["t", 0, 3, 1, 2, 10], ["t", 0, 6, 4, 5, 30]]), [2.0, 4.25])
        self.assertEqual(I.pivots(12, 8, 10), {"P": 10, "R1": 12, "S1": 8, "R2": 14, "S2": 6, "R3": 16, "S3": 4})

    def test_fractals_structure_sr(self):
        h = [1, 2, 5, 2, 1, 3, 6, 3, 1]
        l = [0, 1, 4, 1, 0.5, 2, 5, 2, 0.8]
        hi, lo = I.fractals(h, l, 2)
        self.assertEqual(hi, [(2, 5), (6, 6)])
        self.assertEqual(lo, [(4, 0.5)])
        self.assertEqual(I.structure(h, l, 2)[0], "unclear")  # only one swing low
        h2 = [5, 6, 8, 6, 5, 7, 9, 7, 6, 8, 10, 8, 7]
        l2 = [4, 3, 6, 4, 2, 5, 7, 5, 3, 6, 8, 6, 5]
        self.assertEqual(I.structure(h2, l2, 2)[0], "uptrend")
        self.assertEqual(I.support_resistance(h2, l2, 9.5, 2), (3, 10))

    def test_relative_strength_weekly_stats(self):
        self.assertAlmostEqual(I.rel_strength([100, 110], [100, 105], 1), 4.7619, 3)
        w = I.weekly(["2026-11-16", "2026-11-17", "2026-11-23"], [1, 2, 3], [5, 6, 7], [0.5, 1, 2], [2, 3, 4], [10, 20, 30])
        self.assertEqual(w, {"d": ["2026-11-17", "2026-11-23"], "o": [1, 3], "h": [6, 7], "l": [0.5, 2], "c": [3, 4], "v": [30, 30]})
        self.assertEqual(I.median([3, 1, 2, None]), 2)
        self.assertEqual(I.percentile([1, 2, 3, 4, 5], 0.5), 3)
        self.assertAlmostEqual(I.percentile([0, 10], 0.25), 2.5)
        a, b = I.align(["d1", "d2", "d3"], [1, 2, 3], ["d2", "d3"], [20, 30])
        self.assertEqual((a, b), ([2, 3], [20, 30]))


if __name__ == "__main__":
    unittest.main()

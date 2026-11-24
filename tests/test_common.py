"""Core library: money, ticks, Kite login/expiry, calendar, limiter, cache, EOD store round trip."""

import datetime as dt
import os
import unittest

from _load import TempData, fx, load
import nse_common as C
import nse_parsers as P


class Money(unittest.TestCase):
    def test_inr(self):
        self.assertEqual(C.inr(1234567.891), "₹12,34,567.89")
        self.assertEqual(C.inr(999), "₹999.00")
        self.assertEqual(C.inr(-1000.5), "-₹1,000.50")
        self.assertEqual(C.inr(123456789, 0), "₹12,34,56,789")
        self.assertEqual(C.inr_short(4.5e12), "₹4,50,000 Cr")
        self.assertEqual(C.inr_short(250000), "₹2.50 L")

    def test_ticks(self):
        self.assertEqual(C.round_tick(1103.43, 0.1, "down"), 1103.4)
        self.assertEqual(C.round_tick(1103.41, 0.1, "up"), 1103.5)
        self.assertEqual(C.round_tick(358.327, 0.05, "down"), 358.3)
        self.assertEqual(float(C.tick_for(120)), 0.01)   # fallback table when the instrument's tick is unknown
        self.assertEqual(float(C.tick_for(800)), 0.05)
        self.assertEqual(float(C.tick_for(800, 0.1)), 0.1)

    def test_kite_checksum(self):
        # SHA-256 of the concatenation "abc" (api_key "a" + request_token "b" + api_secret "c"), FIPS 180-2 test vector
        self.assertEqual(C.kite_checksum("a", "b", "c"), "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")


class Calendar(unittest.TestCase):
    hol = {"2026-11-24", "2026-12-25"}

    def test_days(self):
        self.assertFalse(C.is_trading_day(dt.date(2026, 11, 24), self.hol))  # holiday
        self.assertFalse(C.is_trading_day(dt.date(2026, 11, 22), self.hol))  # Sunday
        self.assertEqual(C.prev_trading_day(dt.date(2026, 11, 25), self.hol), dt.date(2026, 11, 23))
        self.assertEqual(C.trading_days_back(dt.date(2026, 11, 25), 3, self.hol),
                         [dt.date(2026, 11, 20), dt.date(2026, 11, 23), dt.date(2026, 11, 25)])

    def test_status(self):
        t = lambda s: C.now_ist(s)
        self.assertEqual(C.market_status(t("2026-11-25 09:05"), self.hol)["state"], "pre-open")
        self.assertEqual(C.market_status(t("2026-11-25 09:15"), self.hol)["state"], "open")
        self.assertEqual(C.market_status(t("2026-11-25 15:30"), self.hol)["state"], "closed")
        self.assertEqual(C.market_status(t("2026-11-24 11:00"), self.hol)["why"], "holiday")
        self.assertEqual(C.last_completed_session(t("2026-11-25 12:00"), self.hol), dt.date(2026, 11, 23))
        self.assertEqual(C.last_completed_session(t("2026-11-25 18:30"), self.hol), dt.date(2026, 11, 25))


class Infra(unittest.TestCase):
    def test_limiter_spaces_calls(self):
        clock, slept = [0.0], []

        def sleep(s):
            slept.append(round(s, 3))
            clock[0] += s
        lim = C.Limiter([(3, 1.0), (5, 10.0)], sleep=sleep, clock=lambda: clock[0])
        for _ in range(6):
            lim.wait()
        self.assertEqual(slept[0], 1.0)          # 4th call waits for the 3/s window
        self.assertAlmostEqual(sum(slept), 10.0)  # 6th call waits for the 5/10 s window

    def test_cache_ttl(self):
        with TempData():
            calls = []
            f = lambda: calls.append(1) or {"x": len(calls)}
            p = C.path("cache", "t.json")
            now = C.now_ist("2026-11-23 10:00")
            self.assertEqual(C.cached(p, "day", f, now)[0], {"x": 1})
            self.assertTrue(C.cached(p, "day", f, C.now_ist("2026-11-23 15:00"))[2])
            self.assertEqual(C.cached(p, "day", f, C.now_ist("2026-11-24 09:00"))[0], {"x": 2})
            self.assertEqual(C.cached(p, 60, f, C.now_ist("2026-11-24 09:00"))[0], {"x": 2})
            self.assertEqual(C.cached(p, 60, f, C.now_ist("2026-11-24 09:02"))[0], {"x": 3})

    def test_require(self):
        with self.assertRaises(C.FieldError) as e:
            C.require({"a": 1, "b": 2}, ["a", "z"], "thing")
        self.assertIn("missing z; fields found: a, b", str(e.exception))

    def test_eod_store_round_trip(self):
        with TempData():
            rows = P.parse_bhavcopy(fx("fake_bhavcopy.csv"))
            idx = P.parse_index_close(fx("fake_ind_close_all.csv"))
            for d in ("2026-11-20", "2026-11-23"):
                C.write_json(C.eod_file(dt.date.fromisoformat(d)), {"date": d, "rows": rows, "indices": idx}, compact=True)
            dates, ser, ind = C.eod_load(10, ["FAKEA"])
            self.assertEqual(dates, ["2026-11-20", "2026-11-23"])
            self.assertEqual(list(ser), ["FAKEA"])
            self.assertEqual(ser["FAKEA"]["c"], [104.9, 104.9])
            self.assertEqual(ser["FAKEA"]["dp"], [50.0, 50.0])
            self.assertEqual(ind["NIFTY 50"]["c"], [20050.0, 20050.0])

    def test_kite_creds_and_daily_expiry(self):
        with TempData() as d:
            saved = {k: os.environ.pop(k, None) for k in ("KITE_API_KEY", "KITE_ACCESS_TOKEN")}
            old = C.CRED_FILE
            C.CRED_FILE = os.path.join(d, "kite.json")
            try:
                self.assertIsNone(C.kite_creds())
                C.write_json(C.CRED_FILE, {"api_key": "FAKEKEY", "access_token": "FAKETOKEN", "token_at": "2026-11-25T08:00:00+05:30"})
                self.assertEqual(C.kite_creds(C.now_ist("2026-11-25 12:00"))["access_token"], "FAKETOKEN")
                self.assertEqual(C.kite_creds(C.now_ist("2026-11-26 05:59"))["access_token"], "FAKETOKEN")
                self.assertIsNone(C.kite_creds(C.now_ist("2026-11-26 06:00")))          # reset at 06:00 IST
                C.write_json(C.path("config.json"), {"data_source": "free"})
                self.assertIsNone(C.kite_creds(C.now_ist("2026-11-25 12:00")))          # forced free sources
            finally:
                C.CRED_FILE = old
                for k, v in saved.items():
                    if v is not None:
                        os.environ[k] = v

    def test_kite_login_parses_redirect(self):
        kl = load("lib", "kite_login")
        self.assertEqual(kl.request_token_from("https://example.invalid/cb?action=login&request_token=FAKE1234abcd&status=success"), "FAKE1234abcd")
        self.assertEqual(kl.request_token_from(" FAKE1234abcd \n"), "FAKE1234abcd")
        with self.assertRaises(ValueError):
            kl.request_token_from("not a token!")


if __name__ == "__main__":
    unittest.main()

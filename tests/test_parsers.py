"""Every parser against SYNTHETIC fixtures shaped like the live sources (tests/fixtures/README.md)."""

import json
import unittest

from _load import fx
import nse_parsers as P


class Parsers(unittest.TestCase):
    def test_equity_l(self):
        rows = P.parse_equity_l(fx("fake_EQUITY_L.csv"))
        self.assertEqual(rows[0], {"symbol": "FAKEA", "name": "Fake Alpha Limited", "series": "EQ", "listed": "2008-10-06",
                                   "isin": "INFAKE00001", "face_value": 5.0})
        self.assertEqual(len(rows), 5)

    def test_kite_instruments(self):
        m = P.parse_kite_instruments(fx("fake_kite_NSE.csv"))
        self.assertEqual(m["eq"]["FAKEA"], {"token": "900001", "tick": 0.05, "series": "EQ", "name": "FAKE ALPHA", "ksym": "FAKEA"})
        self.assertEqual((m["eq"]["FAKEBE"]["series"], m["eq"]["FAKEBE"]["ksym"]), ("BE", "FAKEBE-BE"))
        self.assertEqual(m["eq"]["FAKESME"]["series"], "SM")
        self.assertNotIn("FAKEBOND", m["eq"])           # -N0 bonds are not equities
        self.assertEqual(m["indices"], {"NIFTY 50": "256265"})
        self.assertEqual(P.parse_kite_fo(fx("fake_kite_NFO.csv")), {"FAKEA": ["2026-12-29", "2027-01-25"]})
        with self.assertRaises(P.FieldError) as e:
            P.parse_kite_instruments("instrument_token,symbol\n1,X\n")
        self.assertIn("fields found", str(e.exception))

    def test_holidays(self):
        self.assertEqual(P.parse_holidays(json.loads(fx("fake_holidays.json"))), {"2026-11-24", "2026-12-25"})

    def test_bhavcopy(self):
        b = P.parse_bhavcopy(fx("fake_bhavcopy.csv"))
        self.assertEqual(b["FAKEA"], ["EQ", 101.0, 105.5, 100.5, 104.9, 120000, 123.84, 50.0])
        self.assertIsNone(b["FAKEB"][7])  # '-' delivery
        self.assertIn("FAKEBE", b)
        self.assertNotIn("FAKEN", b)  # non-equity series dropped

    def test_bhavcopy_changed_columns_fail_with_fields_found(self):
        with self.assertRaises(P.FieldError) as e:
            P.parse_bhavcopy("SYMBOL,SERIES,CLOSE\nX,EQ,1\n")
        self.assertIn("fields found: SYMBOL, SERIES, CLOSE", str(e.exception))

    def test_index_close(self):
        self.assertEqual(P.parse_index_close(fx("fake_ind_close_all.csv"))["Nifty IT"], [30000.0, 30300.0, 29800.0, 30200.0])

    def test_quote(self):
        q = P.parse_quote(json.loads(fx("fake_getquote.json")))
        self.assertEqual((q["ltp"], q["prev_close"], q["band_low"], q["band_high"], q["tick"]), (104.9, 100.0, 90.0, 110.0, 0.05))
        self.assertEqual((q["pe"], q["sector_pe"], q["sector_index"]), (15.2, 20.5, "NIFTY IT"))
        self.assertEqual((q["year_high"], q["year_high_date"], q["deliv_pct"]), (120.0, "2026-02-03", 50.0))
        self.assertEqual(q["updated"], "2026-11-23T16:00:00+05:30")

    def test_quote_shape_change(self):
        with self.assertRaises(P.FieldError) as e:
            P.parse_quote({"data": []})
        self.assertIn("fields found: data", str(e.exception))

    def test_kite_quote_and_candles(self):
        qs = {q["symbol"]: q for q in P.parse_kite_quote(json.loads(fx("fake_kite_quote.json"))["data"])}
        q = qs["FAKEA"]
        self.assertEqual((q["ltp"], q["prev_close"], q["band_high"], q["bid"], q["ask"], q["volume"]), (104.9, 100.0, 110.0, 104.85, 104.95, 120000.0))
        self.assertEqual((qs["FAKEBE"]["ksym"], qs["FAKEBE"]["band_high"]), ("FAKEBE-BE", None))
        c = P.parse_kite_candles(json.loads(fx("fake_kite_candles.json"))["data"])
        self.assertEqual(c[1], ["2026-11-23T09:20:00+05:30", 101.5, 103.0, 101.0, 102.8, 7000])
        with self.assertRaises(P.FieldError):
            P.parse_kite_candles({"bars": []})

    def test_yahoo_chart_skips_empty_bars(self):
        b = P.parse_yahoo_chart(json.loads(fx("fake_yahoo_chart.json")))
        self.assertEqual(len(b), 2)
        self.assertTrue(b[0][0].endswith("+05:30"))

    def test_announcements(self):
        a = P.parse_announcements(json.loads(fx("fake_announcements.json")))
        self.assertEqual(a[0]["time"], "2026-11-18T22:10:55+05:30")
        self.assertEqual(a[0]["pdf"], "https://example.invalid/f.pdf")
        self.assertIsNone(a[1]["pdf"])

    def test_events(self):
        e = P.parse_event_calendar(json.loads(fx("fake_event_calendar.json")))
        self.assertEqual(e[0]["date"], "2026-11-30")
        b = P.parse_board_meetings(json.loads(fx("fake_board_meetings.json")))
        self.assertEqual(b[0]["what"], "Financial Results")
        a = P.parse_corp_actions(json.loads(fx("fake_corp_actions.json")))
        self.assertEqual([(x["date"], x["kind"]) for x in a], [("2026-12-05", "dividend"), ("2026-01-01", "bonus")])
        self.assertIsNone(a[1]["record_date"])

    def test_results(self):
        r = P.parse_results_cmp(json.loads(fx("fake_results_cmp.json")))
        self.assertEqual([q["end"] for q in r][0], "2023-12-31")
        self.assertEqual((r[-1]["revenue"], r[-1]["net_profit"], r[-1]["eps"]), (1100.0, 110.0, 1.1))
        i = P.parse_integrated(json.loads(fx("fake_integrated.json")))
        self.assertEqual(i[-1]["end"], "2026-09-30")
        self.assertEqual({x["basis"] for x in i}, {"Consolidated", "Standalone"})

    def test_shareholding_pit_deals_fiidii_52w(self):
        s = P.parse_shareholding(json.loads(fx("fake_shareholding.json")))
        self.assertEqual([(x["date"], x["promoter"]) for x in s], [("2026-06-30", 60.2), ("2026-09-30", 60.1)])
        p = P.parse_pit(json.loads(fx("fake_pit.json")))[0]
        self.assertEqual((p["type"], p["qty"], p["date"], p["category"]), ("Sell", 1000.0, "2026-11-13", "Promoter Group"))
        d = P.parse_deals_csv(fx("fake_deals_bulk.csv"), "bulk")
        self.assertEqual((d[0]["symbol"], d[0]["side"], d[0]["qty"], d[0]["date"]), ("FAKEA", "BUY", 1000000.0, "2026-11-23"))
        f = P.parse_fiidii(json.loads(fx("fake_fiidii.json")))
        self.assertEqual(f[0]["net_cr"], -250.5)
        w = P.parse_52w(json.loads(fx("fake_52w.json")))
        self.assertEqual(w[0]["level"], 105.5)

    def test_rss(self):
        r = P.parse_rss(fx("fake_gnews.xml", "rb"))
        self.assertEqual(r[0]["title"], "Fake Alpha Q2 results: net profit rises 12%")
        self.assertEqual(r[0]["source"], "Fake Times")
        self.assertEqual(r[0]["time"], "2026-11-23T10:30:00+00:00")
        self.assertIn("&", r[1]["title"])
        with self.assertRaises(P.FieldError):
            P.parse_rss(b"<html><body>blocked</body>")

    def test_dates(self):
        for s, want in (("23-Nov-2026", "2026-11-23"), ("30-SEP-2026", "2026-09-30"), ("23-11-2026", "2026-11-23"),
                        ("29DEC2026", "2026-12-29"), ("30 Sep 2026", "2026-09-30"), ("-", None), ("", None)):
            self.assertEqual(P.nse_date(s), want, s)


if __name__ == "__main__":
    unittest.main()

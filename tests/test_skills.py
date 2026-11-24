"""Skill scripts' pure logic on FAKE inputs: scan, entry, exit, time machine, budget, risk, ticket, alerts, track, news, research."""

import datetime as dt
import json
import unittest

from _load import TempData, load, series, fx
import nse_common as C
import nse_research as R
import nse_parsers as P

scan = load("trader-scanner", "scan")
entry = load("trader-entry", "entry")
exitp = load("trader-exit", "exit")
tm = load("trader-timemachine", "timemachine")
size = load("trader-budget", "size")
risk = load("trader-risk", "check")
ticket = load("trader-ticket", "ticket")
alerts = load("trader-alerts", "alerts")
track = load("trader-track", "track")
news = load("trader-news", "news")

HOL = {"2026-11-24", "2026-12-25"}
C._HOL = HOL  # tests never hit the network for the calendar
DAY = "2026-11-25"


def bars5(closes, day=DAY, start=(9, 15), vol=1000, spread=0.3):
    out, t = [], dt.datetime(2026, 1, 1, *start)
    for i, c in enumerate(closes):
        ts = "%sT%02d:%02d:00+05:30" % (day, t.hour, t.minute)
        out.append([ts, c, c + spread, c - spread, c, vol])
        t += dt.timedelta(minutes=5)
    return out


class Scan(unittest.TestCase):
    def test_rank_and_filter(self):
        up = [60 + i * 0.5 for i in range(80)] + [101.0]
        a = series(up, [100000] * 80 + [400000])
        a["t"] = [700.0] * len(up)
        b = series([100.0] * 81)
        b["t"] = [700.0] * 81
        etf = series(up)
        etf["t"] = [700.0] * len(up)
        rows, skipped = scan.scan_store({"FAKEA": a, "FAKEB": b, "FAKEETF": etf, "NOPE": a},
                                        {"FAKEA": {"name": "A"}, "FAKEB": {}, "FAKEETF": {"etf": True}}, dict(scan.B.DEFAULTS))
        self.assertEqual([r["symbol"] for r in rows], ["FAKEA"])
        self.assertEqual(skipped, {"not in universe": 1, "ETF": 1})
        self.assertIn("FAKEA", scan.line(rows[0]))


class Entry(unittest.TestCase):
    def test_orb_states(self):
        b = bars5([100, 100.2, 100.1, 100.0, 100.6, 101.0])  # OR = first 3 bars, high 100.5
        now = lambda hm: C.now_ist("%s %s" % (DAY, hm))
        self.assertEqual(entry.evaluate(b, now("09:20"))["status"], "waiting")
        r = entry.evaluate(b, now("09:36"))
        self.assertEqual((r["status"], r["or_high"]), ("waiting", 100.5))
        r = entry.evaluate(b, now("09:41"))
        self.assertEqual((r["status"], r["entry"], r["time"]), ("triggered", 100.6, "09:40"))
        self.assertEqual(entry.evaluate(b, now("08:50"))["status"], "not open")
        self.assertEqual(entry.evaluate(b, C.now_ist("2026-11-24 10:00"))["status"], "not open")  # holiday

    def test_expired_and_volume_filter(self):
        b = bars5([100, 100.2, 100.1] + [100.0] * 70)
        self.assertEqual(entry.evaluate(b, C.now_ist(DAY + " 15:00"))["status"], "expired")
        b = bars5([100, 100.2, 100.1, 100.9])
        b[3][5] = 500  # below 1.5x the OR average volume
        self.assertEqual(entry.evaluate(b, C.now_ist(DAY + " 09:40"), vol_mult=1.5)["status"], "waiting")
        r = entry.evaluate(b, C.now_ist(DAY + " 09:40"), setup="level", level=100.8)
        self.assertEqual(r["status"], "triggered")


class Exit(unittest.TestCase):
    def test_or_mid_and_2r(self):
        p = exitp.compute(364.18, "or-mid", "2R", 362.18, 354.47, tick=0.05)
        self.assertEqual(p["stop"], 358.3)          # (362.18+354.47)/2 = 358.325 -> down to tick
        self.assertEqual(p["risk_per_share"], 5.88)
        self.assertEqual(p["target"], 375.9)        # 364.18 + 11.76 = 375.94 -> down to 375.90
        self.assertAlmostEqual(p["r_multiple"], 1.99)

    def test_refusals(self):
        for args in ((100, "101", "2R"), (100, "99.99", "2R"), (100, "98", "99")):
            with self.assertRaises(exitp.PlanError):
                exitp.compute(*args, tick=0.01)
        with self.assertRaises(exitp.PlanError):
            exitp.compute(100, "or-mid", "2R")
        p = exitp.compute(100, "pct:1", "1.5R", tick=0.05)
        self.assertEqual((p["stop"], p["target"]), (99.0, 101.5))


class TimeMachine(unittest.TestCase):
    def _days(self):
        out = []
        for k in range(20):
            d = (dt.date(2026, 10, 1) + dt.timedelta(days=k)).isoformat()
            closes = [100 + 0.1 * (i % 3) for i in range(3)] + [100 + 0.15 * i for i in range(1, 72)]
            out += bars5(closes, d, spread=0.05)
        return out

    def test_deterministic_and_history(self):
        plan = {"symbol": "FAKEA", "entry": 100.3, "stop": 99.8, "target": 101.3, "risk_per_share": 0.5, "r_multiple": 2.0,
                "flat_by": "15:10", "entry_time": "09:35", "date": DAY}
        a, b = tm.run(plan, self._days(), 500, 7), tm.run(plan, self._days(), 500, 7)
        self.assertEqual(a, b)
        self.assertEqual(a["sim"]["target_first"], 100.0)  # the FAKE days only ever go up
        self.assertEqual(a["history"]["fired"], 20)
        self.assertEqual(a["history"]["target"], 20)
        self.assertEqual(tm.slot_of("2026-11-25T09:15:00+05:30"), 0)
        self.assertEqual(tm.slot_of("2026-11-25T15:25:00+05:30"), 74)

    def test_same_bar_counts_stop(self):
        lib = [[(0.0, 0.05, -0.05, 0.0)] for _ in range(75)]
        r = tm.simulate(lib, 100, 99, 101, 0, 75, sims=10, seed=1)
        self.assertEqual(r["stop_first"], 100.0)


class Budget(unittest.TestCase):
    plan = {"symbol": "FAKEA", "entry": 846.5, "stop": 838.5, "target": 862.5, "flat_by": "15:10"}

    def test_deciders(self):
        s = size.size_trade(self.plan, {"capital": 100000, "max_loss_per_trade": 500, "max_position_pct": 25, "max_order_value": 50000, "cash_buffer_pct": 10})
        self.assertEqual((s["qty"], s["decided_by"], s["max_loss"]), (29, "position cap", 232.0))  # 25000/846.5 = 29.5
        s = size.size_trade(self.plan, {"capital": 1000000, "max_loss_per_trade": 200, "max_position_pct": 100, "max_order_value": 1e7})
        self.assertEqual((s["qty"], s["decided_by"]), (25, "max loss per trade"))                   # 200/8 = 25
        s = size.size_trade(self.plan, {"capital": 1000000, "max_loss_per_trade": 200}, price=850.5)
        self.assertEqual(s["qty"], 16)                                                            # risk from fresh 850.5: 200/12

    def test_refuses_not_shrinks(self):
        with self.assertRaises(size.SizeError) as e:
            size.size_trade(self.plan, {"max_loss_per_trade": 5})
        self.assertIn("too far", str(e.exception))
        o = size.ticket(self.plan, size.size_trade(self.plan, {}), C.now_ist(DAY + " 10:00"))
        self.assertEqual((o["side"], o["exchange"], o["product"]), ("BUY", "NSE", "MIS"))
        self.assertEqual(len(o["id"]), 12)


class Risk(unittest.TestCase):
    cfg = dict(risk.DEFAULTS)
    day0 = {"realized": 0.0, "entries": 0, "approved_risk": 0.0, "approved_ids": set(), "orders_today": 0}
    o = {"id": "x1", "symbol": "FAKEA", "side": "BUY", "qty": 29, "product": "MIS", "entry": 846.5, "stop": 838.5, "target": 862.5, "max_loss": 232.0}
    now = C.now_ist(DAY + " 10:00")
    live = {"price": 846.5, "band_high": 930.0, "event_today": []}

    def v(self, o=None, now=None, day=None, meta=None, live="default"):
        return risk.check(o or self.o, self.cfg, now or self.now, day or dict(self.day0), meta or {"series": "EQ", "tick": 0.05},
                          self.live if live == "default" else live)

    def test_pass(self):
        self.assertEqual(self.v()[0], "PASS")
        self.assertIn("offline", " ".join(self.v(live=None)[2]))

    def test_blocks(self):
        cases = [
            (dict(self.o, stop=0), None, None, None, None, "a stop is required"),
            (dict(self.o, qty=100), None, None, None, None, "over your max loss"),
            (dict(self.o, target=850.0), None, None, None, None, "reward:risk"),
            (None, C.now_ist(DAY + " 14:45"), None, None, None, "outside your entry window"),
            (None, C.now_ist("2026-11-24 10:00"), None, None, None, "market is closed"),
            (None, None, dict(self.day0, entries=3), None, None, "already 3 entries"),
            (None, None, dict(self.day0, realized=-1400.0), None, None, "daily limit"),
            (None, None, dict(self.day0, approved_ids={"x1"}), None, None, "duplicate"),
            (None, None, None, {"series": "BE", "tick": 0.05}, None, "trade-for-trade"),
            (dict(self.o, entry=846.53), None, None, None, None, "not a multiple of the tick"),
            (None, None, None, None, dict(self.live, band_high=860.0), "upper circuit"),
            (None, None, None, None, dict(self.live, event_today=[{"what": "Financial Results"}]), "event today"),
        ]
        for o, now, day, meta, lv, want in cases:
            verdict, bad, _ = self.v(o, now, day, meta, lv if lv is not None else "default")
            self.assertEqual(verdict, "BLOCK", want)
            self.assertIn(want, " | ".join(bad), want)

    def test_exit_never_blocked(self):
        o = dict(self.o, side="SELL", stop=0, target=0)
        verdict, bad, warn = self.v(o, C.now_ist(DAY + " 15:20"), dict(self.day0, realized=-99999.0, entries=9))
        self.assertEqual(verdict, "PASS")

    def test_day_state(self):
        j = {"fills": [{"date": DAY, "side": "BUY", "pnl": None}, {"date": DAY, "side": "SELL", "pnl": -300.0}]}
        r = {"verdicts": [{"id": "a", "date": DAY, "verdict": "PASS", "side": "BUY", "max_loss": 200}]}
        d = risk.day_state(j, r, DAY)
        self.assertEqual((d["realized"], d["entries"], d["approved_risk"], d["approved_ids"]), (-300.0, 1, 200, {"a"}))


class Ticket(unittest.TestCase):
    o = {"symbol": "FAKEA", "qty": 29}

    def test_yes(self):
        self.assertTrue(ticket.parse_yes("yes buy 29 FAKEA", self.o)[0])
        for reply in ("yes", "ok buy 29 FAKEA", "yes buy 30 FAKEA", "yes but wait 29 FAKEA", "yes 29 FAKEA?", "yes buy 29 FAKEB"):
            self.assertFalse(ticket.parse_yes(reply, self.o)[0], reply)

    def test_fills(self):
        j, now = {}, C.now_ist(DAY + " 10:00")
        ticket.apply_fill(j, "FAKEA", "BUY", 10, 100.0, now)
        ticket.apply_fill(j, "FAKEA", "BUY", 10, 110.0, now)
        self.assertEqual(j["positions"]["FAKEA"], {"qty": 20, "avg": 105.0})
        self.assertEqual(ticket.apply_fill(j, "FAKEA", "SELL", 20, 100.0, now), -100.0)
        self.assertNotIn("FAKEA", j["positions"])
        with self.assertRaises(ValueError):
            ticket.apply_fill(j, "FAKEA", "SELL", 1, 100.0, now)

    def test_no_order_api(self):
        with open(ticket.__file__, encoding="utf-8") as f:
            self.assertIn("never sends", f.read())


class Alerts(unittest.TestCase):
    def test_ring_once(self):
        doc = {"rules": [], "rang": {}}
        for r in alerts.rules_from_plan({"symbol": "FAKEA", "stop": 99.0, "target": 103.0, "flat_by": "15:10"}):
            alerts.add(doc, r)
        alerts.add(doc, {"type": "pct_up", "symbol": "FAKEA", "level": 2.0})
        alerts.add(doc, {"type": "opening_bell"})
        self.assertEqual(len(doc["rules"]), 5)
        q = {"FAKEA": {"ltp": 103.2, "prev_close": 100.0}}
        rang = alerts.evaluate(doc["rules"], q, C.now_ist(DAY + " 10:00"), doc["rang"])
        self.assertEqual(sorted(r["type"] for r, _ in rang), ["opening_bell", "pct_up", "target"])
        self.assertEqual(alerts.evaluate(doc["rules"], q, C.now_ist(DAY + " 10:05"), doc["rang"]), [])
        late = alerts.evaluate(doc["rules"], q, C.now_ist(DAY + " 15:11"), doc["rang"])
        self.assertEqual([r["type"] for r, _ in late], ["time"])
        fresh = {"rules": [], "rang": {}}
        alerts.add(fresh, {"type": "above", "symbol": "FAKEA", "level": 100.0})
        self.assertEqual(alerts.evaluate(fresh["rules"], q, C.now_ist("2026-11-24 10:00"), fresh["rang"]), [])  # holiday: stale quote


class Track(unittest.TestCase):
    def test_bar_builder(self):
        b = track.BarBuilder()
        t = lambda hm: C.now_ist(DAY + " " + hm)
        b.update(t("09:15"), 100.0, 1000)
        b.update(t("09:15"), 101.0, 1500)
        b.update(t("09:16"), 99.5, 1600)
        self.assertEqual(b.bars, [[DAY + "T09:15:00+05:30", 100.0, 101.0, 100.0, 101.0, 500], [DAY + "T09:16:00+05:30", 99.5, 99.5, 99.5, 99.5, 100]])
        agg = track.aggregate(b.bars, 5)
        self.assertEqual(agg, [[DAY + "T09:15:00+05:30", 100.0, 101.0, 99.5, 99.5, 600]])

    def test_structure_and_events(self):
        b1 = []
        for i in range(60):
            p = 100 + (0.05 * i if i < 40 else 2 - 0.1 * (i - 40))
            b1.append(["%sT%02d:%02d:00+05:30" % (DAY, 9 + (15 + i) // 60, (15 + i) % 60), p, p + 0.02, p - 0.02, p, 100])
        b1[-1][5] = 1000
        now = C.now_ist(DAY + " 10:15")
        s = track.structure(b1, now, 100.1, level=101.0, prev_day=(102, 98, 100), quote={"band_high": 102.0, "band_low": 90.0})
        self.assertEqual(s["breakout"], "failed")
        self.assertEqual(s["orb"], "inside")  # last 5m close 100.1 is back inside the 09:15-09:30 range
        self.assertTrue(s["vol_spike"])
        self.assertEqual(s["pivots"]["P"], 100.0)
        ev = dict(track.events({"breakout": "confirmed"}, s, {"stop": 100.5, "target": 103}, {"near_circuit_pct": 2.0}))
        self.assertIn("failed", ev)
        self.assertIn("stop", ev)
        self.assertIn("circuit_up", ev)
        self.assertTrue(any(k.startswith("volspike:") for k in ev))


class NewsAndResearch(unittest.TestCase):
    def test_new_only(self):
        items = [{"title": "a", "link": "https://example.invalid/1"}, {"title": "b", "link": None}]
        st, now = {}, C.now_ist(DAY + " 10:00")
        self.assertEqual(len(news.select(items, st)), 2)
        news.remember(items, st, now)
        self.assertEqual(news.select(items, st), [])
        self.assertEqual(len(news.select(items, st, show_all=True)), 2)

    def test_tags(self):
        for title, want in (("Fake Alpha Q2 results: net profit rises", "results"), ("Fake Infra bags order worth Rs 500 cr", "order win"),
                            ("SEBI slaps penalty on Fake Co", "regulatory"), ("CRISIL upgrades Fake Co", "rating"),
                            ("Promoter pledges shares of Fake Co", "pledge"), ("Fake Co to acquire stake in Fake2", "deal"),
                            ("Fake Co CEO resigns", "management"), ("Block deal: 2% equity changes hands", "block deal"),
                            ("Fake Co hosts a fake picnic", "other")):
            self.assertIn(want, R.tag(title), title)

    def test_results_summary(self):
        qs = [q for q in P.parse_integrated(json.loads(fx("fake_integrated.json"))) if q["basis"] == "Consolidated"]
        r = R.results_summary(qs, dt.date(2026, 11, 25))
        self.assertEqual(r["latest"]["end"], "2026-09-30")
        self.assertAlmostEqual(r["rev_qoq"], 1200 / 1100 * 100 - 100)
        self.assertAlmostEqual(r["rev_yoy"], 20.0)
        self.assertAlmostEqual(r["pat_yoy"], 20.0)
        self.assertEqual(r["ttm"]["net_profit"], 120 + 100 + 90 + 90)
        self.assertAlmostEqual(r["margin"], 10.0)
        self.assertFalse(r["stale"])
        old = R.results_summary(P.parse_results_cmp(json.loads(fx("fake_results_cmp.json"))), dt.date(2026, 11, 25))
        self.assertTrue(old["stale"])
        self.assertAlmostEqual(old["rev_yoy"], 1100 / 800 * 100 - 100)

    def test_deals_accumulate(self):
        with TempData():
            for r in P.parse_deals_csv(fx("fake_deals_bulk.csv"), "bulk"):
                C.write_json(C.path("cache", "deals", "%s_bulk.json" % r["date"]), [r])
            self.assertEqual(len(R.deals_for("FAKEB", "2026-11-01")), 1)
            self.assertEqual(R.deals_for("FAKEB", "2026-11-24"), [])


if __name__ == "__main__":
    unittest.main()

"""Test helpers: load a skill script (folder names have hyphens), find fixtures, isolate the data dir."""

import importlib.util
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "tests", "fixtures")
sys.path.insert(0, os.path.join(ROOT, "lib"))


def load(folder, name):
    path = os.path.join(ROOT, folder, name + ".py")
    spec = importlib.util.spec_from_file_location("nse_" + name.replace("-", "_"), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fx(name, mode="r"):
    with open(os.path.join(FIX, name), mode, **({} if "b" in mode else {"encoding": "utf-8"})) as f:
        return f.read()


class TempData(object):
    """Point NSE_TRADER_DIR at a fresh temp folder for the test, restore afterwards."""

    def __enter__(self):
        self.old = os.environ.get("NSE_TRADER_DIR")
        self.dir = tempfile.mkdtemp(prefix="nse-test-")
        os.environ["NSE_TRADER_DIR"] = self.dir
        return self.dir

    def __exit__(self, *a):
        if self.old is None:
            os.environ.pop("NSE_TRADER_DIR", None)
        else:
            os.environ["NSE_TRADER_DIR"] = self.old
        shutil.rmtree(self.dir, ignore_errors=True)


def series(closes, vols=None, highs=None, lows=None, opens=None, dp=None, start="2026-01-01"):
    """A synthetic daily series dict (FAKE data) for the breakout rules."""
    import datetime as dt
    n = len(closes)
    d0 = dt.date.fromisoformat(start)
    return {"d": [(d0 + dt.timedelta(days=i)).isoformat() for i in range(n)], "series": "EQ",
            "o": list(opens or closes), "h": list(highs or [c * 1.005 for c in closes]), "l": list(lows or [c * 0.995 for c in closes]),
            "c": list(closes), "v": list(vols or [100000] * n), "t": [c * v / 1e5 for c, v in zip(closes, vols or [100000] * n)],
            "dp": list(dp or [40.0] * n)}

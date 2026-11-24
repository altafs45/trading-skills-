"""Indicators on plain lists. Each returns a list as long as its input, None until it has enough data.
Conventions (Wilder smoothing for RSI/ATR/ADX, SMA-seeded EMA) are stated so results can be hand-checked."""

import datetime as dt
import math


def sma(x, n):
    out, s = [None] * len(x), 0.0
    for i, v in enumerate(x):
        s += v
        if i >= n:
            s -= x[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def ema(x, n):
    """EMA seeded with the SMA of the first n values; k = 2/(n+1). Skips leading None."""
    out = [None] * len(x)
    start = next((i for i, v in enumerate(x) if v is not None), len(x))
    if len(x) - start < n:
        return out
    k, e = 2.0 / (n + 1), sum(x[start:start + n]) / n
    out[start + n - 1] = e
    for i in range(start + n, len(x)):
        e = x[i] * k + e * (1 - k)
        out[i] = e
    return out


def _wilder(vals, n, first_index):
    """Wilder average of vals: first = mean(vals[first_index-n+1 .. first_index]), then (prev*(n-1)+v)/n."""
    out = [None] * len(vals)
    if len(vals) <= first_index:
        return out
    a = sum(vals[first_index - n + 1:first_index + 1]) / n
    out[first_index] = a
    for i in range(first_index + 1, len(vals)):
        a = (a * (n - 1) + vals[i]) / n
        out[i] = a
    return out


def rsi(c, n=14):
    out = [None] * len(c)
    if len(c) <= n:
        return out
    g = [0.0] + [max(c[i] - c[i - 1], 0) for i in range(1, len(c))]
    l = [0.0] + [max(c[i - 1] - c[i], 0) for i in range(1, len(c))]
    ag, al = _wilder(g, n, n), _wilder(l, n, n)
    for i in range(n, len(c)):
        out[i] = 100.0 if al[i] == 0 else 100 - 100 / (1 + ag[i] / al[i])
    return out


def macd(c, fast=12, slow=26, sig=9):
    f, s = ema(c, fast), ema(c, slow)
    line = [a - b if a is not None and b is not None else None for a, b in zip(f, s)]
    signal = ema(line, sig)
    hist = [a - b if a is not None and b is not None else None for a, b in zip(line, signal)]
    return line, signal, hist


def true_range(h, l, c):
    return [h[0] - l[0]] + [max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])) for i in range(1, len(c))]


def atr(h, l, c, n=14):
    """Wilder ATR; first value = mean of TR[0..n-1] (TR[0] = high-low)."""
    return _wilder(true_range(h, l, c), n, n - 1)


def bb_width(c, n=20, k=2.0):
    """Bollinger band width in % of the middle band (population stdev)."""
    out, m = [None] * len(c), sma(c, n)
    for i in range(n - 1, len(c)):
        w = c[i - n + 1:i + 1]
        sd = math.sqrt(sum((v - m[i]) ** 2 for v in w) / n)
        out[i] = 2 * k * sd / m[i] * 100 if m[i] else None
    return out


def adx(h, l, c, n=14):
    """Wilder ADX. +DM/-DM/TR smoothed from bar 1; DX from bar n; ADX = mean of first n DX, then Wilder. -> (adx, +di, -di)"""
    L = len(c)
    pdi, mdi, ax = [None] * L, [None] * L, [None] * L
    if L < 2 * n + 1:
        return ax, pdi, mdi
    tr = true_range(h, l, c)
    pdm, mdm = [0.0] * L, [0.0] * L
    for i in range(1, L):
        up, dn = h[i] - h[i - 1], l[i - 1] - l[i]
        pdm[i] = up if up > dn and up > 0 else 0.0
        mdm[i] = dn if dn > up and dn > 0 else 0.0
    st, sp, sm = sum(tr[1:n + 1]), sum(pdm[1:n + 1]), sum(mdm[1:n + 1])
    dx = [None] * L
    for i in range(n, L):
        if i > n:
            st, sp, sm = st - st / n + tr[i], sp - sp / n + pdm[i], sm - sm / n + mdm[i]
        pdi[i], mdi[i] = (100 * sp / st, 100 * sm / st) if st else (0.0, 0.0)
        tot = pdi[i] + mdi[i]
        dx[i] = 100 * abs(pdi[i] - mdi[i]) / tot if tot else 0.0
    a = sum(dx[n:2 * n]) / n
    ax[2 * n - 1] = a
    for i in range(2 * n, L):
        a = (a * (n - 1) + dx[i]) / n
        ax[i] = a
    return ax, pdi, mdi


def obv(c, v):
    out = [0.0]
    for i in range(1, len(c)):
        out.append(out[-1] + (v[i] if c[i] > c[i - 1] else -v[i] if c[i] < c[i - 1] else 0))
    return out


def vwap(bars):
    """Session VWAP per bar from [t,o,h,l,c,v] bars of ONE session; typical price (h+l+c)/3."""
    out, pv, vv = [], 0.0, 0.0
    for b in bars:
        pv += (b[2] + b[3] + b[4]) / 3 * b[5]
        vv += b[5]
        out.append(pv / vv if vv else (b[2] + b[3] + b[4]) / 3)
    return out


def pivots(h, l, c):
    """Classic floor pivots from one prior session's high, low, close."""
    p = (h + l + c) / 3
    return {"P": p, "R1": 2 * p - l, "S1": 2 * p - h, "R2": p + (h - l), "S2": p - (h - l),
            "R3": h + 2 * (p - l), "S3": l - 2 * (h - p)}


def fractals(h, l, k=2):
    """Swing highs/lows: bar i is a swing high if h[i] > the k highs before it and >= the k highs after it."""
    hi, lo = [], []
    for i in range(k, len(h) - k):
        if h[i] > max(h[i - k:i]) and h[i] >= max(h[i + 1:i + k + 1]):
            hi.append((i, h[i]))
        if l[i] < min(l[i - k:i]) and l[i] <= min(l[i + 1:i + k + 1]):
            lo.append((i, l[i]))
    return hi, lo


def structure(h, l, k=2):
    """'uptrend' (higher high AND higher low), 'downtrend' (lower high AND lower low) or 'range', from the last two swings."""
    hi, lo = fractals(h, l, k)
    if len(hi) < 2 or len(lo) < 2:
        return "unclear", hi, lo
    hh, hl = hi[-1][1] > hi[-2][1], lo[-1][1] > lo[-2][1]
    lh, ll = hi[-1][1] < hi[-2][1], lo[-1][1] < lo[-2][1]
    return ("uptrend" if hh and hl else "downtrend" if lh and ll else "range"), hi, lo


def support_resistance(h, l, price, k=2):
    """Nearest swing low below price and swing high above it (None if none)."""
    hi, lo = fractals(h, l, k)
    sup = max((v for _, v in lo if v < price), default=None)
    res = min((v for _, v in hi if v > price), default=None)
    return sup, res


def rel_strength(s, i, n):
    """% out- (+) or under- (-) performance of series s vs index i over the last n points (both aligned, oldest first)."""
    if len(s) <= n or len(i) <= n or not s[-1 - n] or not i[-1 - n]:
        return None
    return ((s[-1] / s[-1 - n]) / (i[-1] / i[-1 - n]) - 1) * 100


def align(dates_a, vals_a, dates_b, vals_b):
    m = dict(zip(dates_b, vals_b))
    pairs = [(a, m[d]) for d, a in zip(dates_a, vals_a) if d in m and m[d] is not None]
    return [p[0] for p in pairs], [p[1] for p in pairs]


def weekly(d, o, h, l, c, v):
    """Resample daily (ISO date strings) to ISO weeks -> dict of lists."""
    out = {"d": [], "o": [], "h": [], "l": [], "c": [], "v": []}
    key = None
    for i, ds in enumerate(d):
        y, w, _ = dt.date.fromisoformat(ds).isocalendar()
        if (y, w) != key:
            key = (y, w)
            for f, x in zip("dohlcv", (ds, o[i], h[i], l[i], c[i], v[i])):
                out[f].append(x)
        else:
            out["d"][-1] = ds
            out["h"][-1] = max(out["h"][-1], h[i])
            out["l"][-1] = min(out["l"][-1], l[i])
            out["c"][-1] = c[i]
            out["v"][-1] += v[i]
    return out


def median(x):
    x = sorted(v for v in x if v is not None)
    if not x:
        return None
    m = len(x) // 2
    return x[m] if len(x) % 2 else (x[m - 1] + x[m]) / 2


def percentile(x, q):
    x = sorted(x)
    if not x:
        return None
    k = (len(x) - 1) * q
    f = int(k)
    return x[f] if f + 1 >= len(x) else x[f] + (x[f + 1] - x[f]) * (k - f)

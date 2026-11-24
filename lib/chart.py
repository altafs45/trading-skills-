"""Self-contained HTML/SVG candlestick chart (no external libraries): candles, volume, EMAs, levels, event markers."""

import html

CSS = """:root{--bg:#fbfaf7;--fg:#1f2328;--mut:#6b7280;--grid:#e6e3dc;--up:#1a7f5a;--dn:#c2412d;--e1:#2f6fdb;--e2:#b7791f;--e3:#7c3aed;--lv:#0f766e;--ev:#9333ea}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#15171a;--fg:#e8e6e1;--mut:#9aa0a6;--grid:#2a2d31;--up:#3fb68b;--dn:#ef6b55;--e1:#6ea8fe;--e2:#e0b453;--e3:#b197fc;--lv:#2dd4bf;--ev:#d8b4fe}}
:root[data-theme="dark"]{--bg:#15171a;--fg:#e8e6e1;--mut:#9aa0a6;--grid:#2a2d31;--up:#3fb68b;--dn:#ef6b55;--e1:#6ea8fe;--e2:#e0b453;--e3:#b197fc;--lv:#2dd4bf;--ev:#d8b4fe}
body{margin:0;padding:16px;background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,-apple-system,Segoe UI,sans-serif}
h1{font-size:18px;margin:0 0 4px}p{margin:0 0 12px;color:var(--mut)}svg{width:100%;height:auto;display:block}
.k{display:flex;flex-wrap:wrap;gap:12px;font-size:12px;color:var(--mut)}.k i{display:inline-block;width:14px;height:3px;margin-right:4px;vertical-align:middle}
text{fill:var(--mut);font-size:11px}"""


def write_chart(path, d, o, h, l, c, v, title, note="", emas=None, levels=None, events=None, last=120):
    """d: ISO dates; emas: {'EMA20': [...]} aligned to d; levels: [(price, label)]; events: [(iso_date, label)]."""
    n0 = max(0, len(c) - last)
    d, o, h, l, c, v = d[n0:], o[n0:], h[n0:], l[n0:], c[n0:], v[n0:]
    W, PH, VH, PAD, R = 1000, 380, 90, 8, 64
    n = len(c)
    lv = [p for p, _ in (levels or []) if p]
    hi, lo = max(h + lv), min(l + lv)
    span = (hi - lo) or 1
    hi, lo = hi + span * 0.04, lo - span * 0.04
    cw = (W - R - PAD) / max(n, 1)
    x = lambda i: PAD + cw * (i + 0.5)
    y = lambda p: PAD + (hi - p) / (hi - lo) * (PH - 2 * PAD)
    vmax = max(v) or 1
    vy = lambda q: PH + 10 + VH - q / vmax * VH
    g = []
    for k in range(5):
        p = lo + (hi - lo) * k / 4
        g.append('<line x1="%d" x2="%d" y1="%.1f" y2="%.1f" stroke="var(--grid)"/><text x="%d" y="%.1f">%.2f</text>'
                 % (PAD, W - R, y(p), y(p), W - R + 6, y(p) + 4, p))
    for i in range(0, n, max(1, n // 6)):
        g.append('<text x="%.1f" y="%d" text-anchor="middle">%s</text>' % (x(i), PH + VH + 26, d[i][5:]))
    for i in range(n):
        col = "var(--up)" if c[i] >= o[i] else "var(--dn)"
        bw = max(1.0, cw * 0.62)
        top, bot = y(max(o[i], c[i])), y(min(o[i], c[i]))
        g.append('<g><title>%s O %.2f H %.2f L %.2f C %.2f V %d</title><line x1="%.1f" x2="%.1f" y1="%.1f" y2="%.1f" stroke="%s"/>'
                 '<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s"/>'
                 '<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s" opacity=".45"/></g>'
                 % (d[i], o[i], h[i], l[i], c[i], v[i], x(i), x(i), y(h[i]), y(l[i]), col, x(i) - bw / 2, top, bw,
                    max(1.0, bot - top), col, x(i) - bw / 2, vy(v[i]), bw, PH + 10 + VH - vy(v[i]), col))
    keys = []
    for (name, ser), var in zip((emas or {}).items(), ("--e1", "--e2", "--e3")):
        ser = ser[n0:]
        pts = " ".join("%.1f,%.1f" % (x(i), y(p)) for i, p in enumerate(ser) if p is not None)
        if pts:
            g.append('<polyline fill="none" stroke="var(%s)" stroke-width="1.5" points="%s"/>' % (var, pts))
            keys.append('<span><i style="background:var(%s)"></i>%s</span>' % (var, html.escape(name)))
    for p, lab in levels or []:
        if p:
            g.append('<line x1="%d" x2="%d" y1="%.1f" y2="%.1f" stroke="var(--lv)" stroke-dasharray="5 4"/>'
                     '<text x="%d" y="%.1f" style="fill:var(--lv)">%s %.2f</text>' % (PAD, W - R, y(p), y(p), PAD + 4, y(p) - 4, html.escape(lab), p))
    pos = {ds: i for i, ds in enumerate(d)}
    for ds, lab in events or []:
        i = pos.get(ds)
        if i is None:
            i = next((j for j, dd in enumerate(d) if dd >= ds), None)
            if i is None:
                continue
        g.append('<g><title>%s: %s</title><path d="M%.1f %d l5 9 h-10z" fill="var(--ev)"/></g>' % (ds, html.escape(lab), x(i), PH - 12))
    if events:
        keys.append('<span><i style="background:var(--ev)"></i>events (hover)</span>')
    if levels:
        keys.append('<span><i style="background:var(--lv)"></i>levels</span>')
    svg = '<svg viewBox="0 0 %d %d" role="img" aria-label="%s">%s</svg>' % (W, PH + VH + 34, html.escape(title), "".join(g))
    doc = ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
           '<title>%s</title><style>%s</style></head><body><h1>%s</h1><p>%s</p>%s<div class="k">%s</div></body></html>'
           % (html.escape(title), CSS, html.escape(title), html.escape(note), svg, "".join(keys)))
    with open(path, "w", encoding="utf-8") as f:
        f.write(doc)
    return path

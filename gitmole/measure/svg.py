"""Line charts as plain SVG, no plotting library: releases along the x axis, a line per series with an
optional interval band, and a crashed release drawn at the bottom of the chart as a red cross. The same
input gives the same bytes."""
from __future__ import annotations

from xml.sax.saxutils import escape

WIDTH, HEIGHT = 900, 300
LEFT, RIGHT, TOP, BOTTOM = 56, 16, 40, 56
INK, GRID, CRASH = "#1f2328", "#d0d7de", "#cf222e"
PALETTE = ["#0969da", "#8250df", "#1a7f37", "#bf8700", "#57606a"]


def _fmt(v: float, unit: str) -> str:
    if unit == "%":
        return f"{v * 100:.0f}%"
    return f"{v:,.0f}" if abs(v) >= 10 else f"{v:.2f}".rstrip("0").rstrip(".")


def _nice_top(v: float) -> float:
    if v <= 0:
        return 1.0
    for step in (1, 2, 2.5, 5, 10):
        mag = 10 ** (len(str(int(v))) - 1)
        if step * mag >= v:
            return step * mag
    return v


def chart(title: str, labels: list, series: list, crashed: list = (), y_range=None, unit: str = "", note: str = "") -> str:
    """labels: the releases, oldest first. series: [{"label", "values", "band": [(lo, hi) | None], "dashed"}].
    crashed: indexes of crashed releases. y_range: (low, high) or None for 0 to a round top."""
    values = [v for s in series for v in s["values"] if v is not None] + [x for s in series for b in (s.get("band") or []) if b for x in b]
    lo, hi = y_range if y_range else (0.0, _nice_top(max(values) if values else 1.0))
    if hi <= lo:
        hi = lo + 1
    w, h = WIDTH - LEFT - RIGHT, HEIGHT - TOP - BOTTOM
    n = max(len(labels), 2)
    x = lambda i: LEFT + w * i / (n - 1)   # noqa: E731
    y = lambda v: TOP + h * (1 - (max(lo, min(hi, v)) - lo) / (hi - lo))   # noqa: E731
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" font-family="-apple-system,Segoe UI,Helvetica,Arial,sans-serif" font-size="12">',
           f'<rect width="{WIDTH}" height="{HEIGHT}" fill="#ffffff"/>',
           f'<text x="{LEFT}" y="22" font-size="15" font-weight="600" fill="{INK}">{escape(title)}</text>']
    for k in range(5):
        v = lo + (hi - lo) * k / 4
        out.append(f'<line x1="{LEFT}" y1="{y(v):.1f}" x2="{WIDTH - RIGHT}" y2="{y(v):.1f}" stroke="{GRID}" stroke-width="1"/>')
        out.append(f'<text x="{LEFT - 6}" y="{y(v) + 4:.1f}" text-anchor="end" fill="{INK}">{escape(_fmt(v, unit))}</text>')
    step = max(1, round(len(labels) / 12))
    for i, lab in enumerate(labels):
        if i % step == 0 or i == len(labels) - 1:
            out.append(f'<text x="{x(i):.1f}" y="{HEIGHT - BOTTOM + 16}" text-anchor="middle" fill="{INK}" font-size="10">{escape(lab)}</text>')
    for si, s in enumerate(series):
        color = s.get("color") or PALETTE[si % len(PALETTE)]
        band = s.get("band") or []
        segs, cur = [], []
        for i, b in enumerate(band):
            if b and None not in b and i not in crashed:
                cur.append((i, b))
            elif cur:
                segs.append(cur)
                cur = []
        if cur:
            segs.append(cur)
        for seg in segs:
            pts = [f"{x(i):.1f},{y(b[1]):.1f}" for i, b in seg] + [f"{x(i):.1f},{y(b[0]):.1f}" for i, b in reversed(seg)]
            out.append(f'<polygon points="{" ".join(pts)}" fill="{color}" fill-opacity="0.12" stroke="none"/>')
        line, lines = [], []
        for i, v in enumerate(s["values"]):
            if v is None or i in crashed:
                if line:
                    lines.append(line)
                line = []
                continue
            line.append(f"{x(i):.1f},{y(v):.1f}")
        if line:
            lines.append(line)
        dash = ' stroke-dasharray="5 4"' if s.get("dashed") else ""
        for pts in lines:
            if len(pts) == 1:
                cx, cy = pts[0].split(",")
                out.append(f'<circle cx="{cx}" cy="{cy}" r="2.5" fill="{color}"/>')
            else:
                out.append(f'<polyline points="{" ".join(pts)}" fill="none" stroke="{color}" stroke-width="2"{dash}/>')
    for i in crashed:
        cx, cy = x(i), TOP + h
        out.append(f'<path d="M{cx - 5:.1f},{cy - 5:.1f} L{cx + 5:.1f},{cy + 5:.1f} M{cx - 5:.1f},{cy + 5:.1f} L{cx + 5:.1f},{cy - 5:.1f}" stroke="{CRASH}" stroke-width="2"/>')
    lx = LEFT
    for si, s in enumerate(series):
        color = s.get("color") or PALETTE[si % len(PALETTE)]
        dash = ' stroke-dasharray="5 4"' if s.get("dashed") else ""
        out.append(f'<line x1="{lx}" y1="{HEIGHT - 18}" x2="{lx + 22}" y2="{HEIGHT - 18}" stroke="{color}" stroke-width="2"{dash}/>')
        out.append(f'<text x="{lx + 28}" y="{HEIGHT - 14}" fill="{INK}">{escape(s["label"])}</text>')
        lx += 36 + 7 * len(s["label"])
    if crashed:
        out.append(f'<path d="M{lx:.1f},{HEIGHT - 23} L{lx + 10:.1f},{HEIGHT - 13} M{lx:.1f},{HEIGHT - 13} L{lx + 10:.1f},{HEIGHT - 23}" stroke="{CRASH}" stroke-width="2"/>')
        out.append(f'<text x="{lx + 16}" y="{HEIGHT - 14}" fill="{INK}">crashed</text>')
        lx += 80
    if note:
        out.append(f'<text x="{WIDTH - RIGHT}" y="{HEIGHT - 14}" text-anchor="end" fill="#57606a" font-size="11">{escape(note)}</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"

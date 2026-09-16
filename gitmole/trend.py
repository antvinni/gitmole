#!/usr/bin/env python3
"""Complexity over time for the top hotspots: scc on each file's contents at sampled commits.

Runs as a pipeline step: `python -m gitmole.trend OUT_DIR [--repo DIR] [--samples N] [--top N]`,
from inside the repository (or with --repo). Reads size.json and maat-revisions.csv the earlier
steps wrote, picks the top hotspots still in the tree, and writes trend.json:
{"samples": [DATE, ...], "files": {PATH: [[DATE, complexity, code], ...]}}.

The pure helpers below are also what the renderer and the findings use."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile

from . import hotspots, load, filetypes

BLOCKS = "▁▂▃▄▅▆▇█"


def sample_dates(first: str, last: str, n: int) -> list:
    a, b = dt.date.fromisoformat(first), dt.date.fromisoformat(last)
    if b <= a:
        return [last]
    span = (b - a).days
    n = max(2, min(n, span // 28 + 1))
    out, seen = [], set()
    for i in range(n):
        d = (a + dt.timedelta(days=round(span * i / (n - 1)))).isoformat()
        if i not in (0, n - 1) and d[:7] in seen:
            continue   # at most one interior sample per month; the two ends always stay
        seen.add(d[:7])
        out.append(d)
    out[-1] = last
    return out


def change_over_year(series: list, last_date: str) -> str:
    if len(series) < 2:
        return "-"
    from .maat import months_before
    year_ago = months_before(last_date, 12)
    before = [s for s in series if s[0] <= year_ago]
    base = before[-1] if before else series[0]
    then, now = base[1], series[-1][1]
    if not then:
        return "-"
    pct = round(100 * (now - then) / then)
    if abs(pct) < 10:
        return "="
    return f"{pct:+d}%"


def sparkline(series: list) -> str:
    values = [s[1] for s in series]
    if not values:
        return ""
    lo, hi = min(values), max(values)
    if hi == lo:
        return BLOCKS[0] * len(values)
    return "".join(BLOCKS[int((v - lo) / (hi - lo) * (len(BLOCKS) - 1))] for v in values)

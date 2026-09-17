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

from . import filetypes, hotspots, load, maat

BLOCKS = "▁▂▃▄▅▆▇█"


def sample_dates(first: str, last: str, n: int) -> list:
    a, b = dt.date.fromisoformat(first), dt.date.fromisoformat(last)
    if b <= a:
        return [last]
    span = (b - a).days
    n = max(2, min(n, span // 28 + 1))
    out = [(a + dt.timedelta(days=round(span * i / (n - 1)))).isoformat() for i in range(n)]
    out[-1] = last
    return out


GROWTH_FLOOR = 25   # percent in a year: below it a hotspot's complexity is not said to be growing


def change_over_year(series: list, last_date: str) -> str:
    if len(series) < 2:
        return "-"
    year_ago = maat.months_before(last_date, 12)
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
    """One block per sample, scaled between the smallest and the largest. Fewer than two samples
    draw nothing: a single block would read as a flat trend nobody measured."""
    values = [s[1] for s in series]
    if len(values) < 2:
        return ""
    lo, hi = min(values), max(values)
    if hi == lo:
        return BLOCKS[0] * len(values)
    return "".join(BLOCKS[int((v - lo) / (hi - lo) * (len(BLOCKS) - 1))] for v in values)


def rev_before(repo: str, date: str, end_of_day: bool = True):
    """The last commit at or before `date` by committer date, or None when there is none.

    The two callers want different edges of the day. A trend sample is "the code as it stood on
    that date", so it takes everything committed during the day (T23:59:59). The backtest asks
    "what did we know before T", so it must stop as the day begins (T00:00:00) and leave the
    commits made on T itself to the future it is being scored against.

    Raises RuntimeError with git's own message when git fails: an unreadable repository is not
    the same answer as a history that does not reach back that far."""
    bound = f"{date}T23:59:59" if end_of_day else f"{date}T00:00:00"
    proc = subprocess.run(["git", "rev-list", "-1", f"--before={bound}", "HEAD"], cwd=repo, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or "").strip().splitlines()[0] if (proc.stderr or "").strip()
                           else f"git rev-list --before={bound} exited {proc.returncode}")
    return proc.stdout.strip() or None


def measure(repo: str, rev: str, files: list, out_dir: str) -> dict:
    """{path: (complexity, code)} for the files that exist at rev, from one scc run over their contents.

    The copies go under `out_dir`, not the system temp directory, so a SIGKILL leaves them where
    the next run's clear_outputs finds them instead of filling /tmp."""
    out = {}
    with tempfile.TemporaryDirectory(dir=out_dir, prefix=".trend-") as tmp:
        present = []
        for path in files:
            proc = subprocess.run([*filetypes.GIT, "show", f"{rev}:{path}"], cwd=repo, capture_output=True)
            if proc.returncode != 0:
                continue
            target = os.path.join(tmp, path)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "wb") as fh:
                fh.write(proc.stdout)
            present.append(path)
        if not present:
            return out
        scc = subprocess.run(["scc", "--by-file", "--format", "json"], cwd=tmp, capture_output=True, text=True)
        if scc.returncode != 0:
            return out
        for path, info in load.parse_scc(scc.stdout)["files"].items():
            out[path] = (info["complexity"], info["code"])
    return out


def top_files(out_dir: str, n: int) -> list:
    meta = json.loads(load._read(out_dir, "meta.json") or "{}")
    size = load.parse_scc(load._read(out_dir, "size.json"), filetypes.parse(meta["file_types"]) if "file_types" in meta else None)
    revisions = load.parse_maat_csv(load._read(out_dir, "maat-revisions.csv"))
    ranked = hotspots.ranked({"size": size, "revisions": revisions})
    return [h["entity"] for h in ranked if h["code"] is not None][:n]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("out")
    p.add_argument("--repo", default=".")
    p.add_argument("--samples", type=int, default=12)
    p.add_argument("--top", type=int, default=10)
    args = p.parse_args(argv)
    meta = json.loads(load._read(args.out, "meta.json") or "{}")
    if not (meta.get("first_date") and meta.get("last_date") and os.path.exists(os.path.join(args.out, "size.json"))
            and os.path.exists(os.path.join(args.out, "maat-revisions.csv"))):
        print("trend: meta.json with dates, size.json and maat-revisions.csv are needed", file=sys.stderr)
        return 2
    files = top_files(args.out, args.top)
    dates = sample_dates(meta["first_date"], meta["last_date"], args.samples)
    series = {f: [] for f in files}
    for date in dates:
        try:
            rev = rev_before(args.repo, date)
        except RuntimeError as e:
            print(f"trend: {e}", file=sys.stderr)
            return 2
        if not rev:
            continue
        for path, (cplx, code) in measure(args.repo, rev, files, args.out).items():
            series[path].append([date, cplx, code])
    data = {"samples": dates, "files": series}
    fd, tmp = tempfile.mkstemp(dir=args.out, prefix=".trend-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        os.replace(tmp, os.path.join(args.out, "trend.json"))
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Duplicated blocks from jscpd, over the tracked text files only.

gitmole runs this as the duplicates step: `python3 duplicates.py REPO OUT [--procs N] [--ignore GLOB]... [--types SPEC]`.
jscpd walks the working tree and reports every pair of matching fragments. This wrapper keeps the pairs
whose two sides are both tracked files inside the analysed types, folds the pairs of one fragment into
a block with all its places, measures the duplicated share over the kept files, and writes
duplicates.json. jscpd's own report quotes every fragment, so it is written to a temporary directory
under OUT and removed before this returns: no source text lands in the output directory. With --then
DATE the tree at the last commit before that date is exported under OUT, measured the same way and
removed, so the rate has a direction: GitClear's longitudinal data shows duplication is where the
change is, and one number without the year before it says little. Standalone, like maat.py and blame.py.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

try:
    from . import blame, filetypes
except ImportError:  # run as a script: the package directory is sys.path[0]
    import blame
    import filetypes

REPORT = "jscpd-report.json"
GIT_DIR = ".git/**"   # walked otherwise: the hook samples in .git/hooks are bash to jscpd
BLOCKS_KEPT = 1000   # the finding names three; the JSON export carries the largest thousand


def select_files(repo: str, ignore=(), types_spec: str = None) -> list:
    """Tracked code files, as hotspots and coupling select them: the built-in source list without
    --file-types, the given list with it, everything with `all`. Data files are left out on purpose: a
    locale file copied per language or a fixture pasted twice is not duplicated code."""
    return blame.code_files(repo, ignore, filetypes.parse(types_spec))


def _rel(name: str) -> str:
    return name[2:] if name.startswith("./") else name


def fold(clones: list, keep: set) -> list:
    """jscpd's pairs -> blocks: one entry per distinct fragment with every place it appears, both sides
    tracked, largest block first. A fragment copied three times comes back from jscpd as two pairs that
    share a side; hashing the fragment text joins them, and the text itself is dropped."""
    blocks = {}
    for c in clones:
        places = []
        for side in ("firstFile", "secondFile"):
            f = c.get(side) or {}
            name = _rel(f.get("name") or "")
            if name not in keep:
                places = []
                break
            places.append((name, int(f.get("start") or 0), int(f.get("end") or 0)))
        if not places:
            continue
        key = hashlib.sha1((c.get("fragment") or "").encode("utf-8", "surrogateescape")).hexdigest()
        block = blocks.setdefault(key, {"lines": int(c.get("lines") or 0), "places": set()})
        block["places"].update(places)
    out = [{"lines": b["lines"], "places": sorted(b["places"])} for b in blocks.values()]
    out.sort(key=lambda b: (-b["lines"], b["places"]))
    return out


def _line_count(path: str) -> int:
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError:
        return 0
    return data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0)


def rate(blocks: list, repo: str, files: list) -> float:
    """Share of the kept files' lines that sit inside a duplicated block, in percent. A line covered by
    two blocks counts once."""
    covered = {}
    for b in blocks:
        for path, start, end in b["places"]:
            covered.setdefault(path, []).append((start, end))
    duplicated = 0
    for path, ranges in covered.items():
        ranges.sort()
        last = 0
        for start, end in ranges:
            start = max(start, last + 1)
            if end >= start:
                duplicated += end - start + 1
                last = end
    total = sum(_line_count(os.path.join(repo, f)) for f in files)
    return round(100.0 * duplicated / total, 2) if total else 0.0


def run_jscpd(repo: str, out: str, procs: int, ignore=()) -> tuple:
    """(returncode, report dict or None). The report goes to a temporary directory under `out`."""
    tmp = tempfile.mkdtemp(prefix=".jscpd-", dir=out)
    try:
        globs = [GIT_DIR] + [g for g in ignore if "," not in g]   # jscpd takes a comma list; a pattern with a comma is left to the filter
        # --silent keeps the progress off stderr; the ignore globs only save work, the tracked-file filter decides
        argv = ["jscpd", "--reporters", "json", "--output", tmp, "--silent", "--no-tips", "--ignore", ",".join(globs),
                "--workers", str(max(1, procs)), "."]
        proc = subprocess.run(argv, cwd=repo, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        sys.stderr.write(proc.stderr.decode("utf-8", "replace"))
        if proc.returncode != 0:
            sys.stderr.write(proc.stdout.decode("utf-8", "replace"))
            return proc.returncode, None
        path = os.path.join(tmp, REPORT)
        if not os.path.isfile(path):
            print("duplicates.py: jscpd wrote no report", file=sys.stderr)
            return 1, None
        with open(path, encoding="utf-8", errors="replace") as fh:
            return 0, json.load(fh)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def rev_before(repo: str, date: str):
    out = subprocess.run(["git", "rev-list", "-1", f"--before={date}T00:00:00", "HEAD"], cwd=repo, capture_output=True, text=True)
    return out.stdout.strip() or None


def files_at(repo: str, rev: str, ignore=(), types_spec: str = None) -> list:
    """The tracked text files of the tree at `rev`, in the analysed types, as select_files lists HEAD's."""
    import fnmatch
    proc = subprocess.run([*filetypes.GIT, "grep", "-I", "--name-only", "-z", "-e", "", rev], cwd=repo, capture_output=True)
    types = filetypes.parse(types_spec)
    paths = sorted(p.decode("utf-8", "surrogateescape").split(":", 1)[1] for p in proc.stdout.split(b"\0") if p)
    return [f for f in paths if filetypes.matches(f, types) and not any(fnmatch.fnmatch(f, g) for g in ignore)]


def rate_at(repo: str, out: str, rev: str, procs: int, ignore=(), types_spec: str = None):
    """The duplicated share of the tree at `rev`: the tree exported through a temporary index under
    `out` (as the backtest exports its cut-off), jscpd over it, the same fold and rate as HEAD's."""
    tmp = tempfile.mkdtemp(prefix=".dup-then-", dir=out)
    try:
        tree = os.path.join(tmp, "tree")
        os.makedirs(tree)
        env = dict(os.environ, GIT_INDEX_FILE=os.path.join(tmp, "index"))
        subprocess.run(["git", "read-tree", rev], cwd=repo, env=env, check=True, capture_output=True)
        subprocess.run(["git", "checkout-index", "-a", f"--prefix={tree}/"], cwd=repo, env=env, check=True, capture_output=True)
        files = files_at(repo, rev, ignore, types_spec)
        rc, report = run_jscpd(tree, out, procs, ignore)
        if rc != 0:
            return None
        blocks = fold(report.get("duplicates") or [], set(files))
        return {"files": len(files), "rate": rate(blocks, tree, files)}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def write(result: dict, target: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(target)), prefix=".duplicates-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=1)
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("repo")
    p.add_argument("out")
    p.add_argument("--procs", type=int, default=1)
    p.add_argument("--ignore", action="append", default=[])
    p.add_argument("--types", default=None, help="file types spec as for gitmole --file-types")
    p.add_argument("--then", metavar="YYYY-MM-DD", help="also measure the tree at the last commit before this date, for the direction")
    args = p.parse_args(argv)
    repo, out = os.path.abspath(args.repo), os.path.abspath(args.out)
    files = select_files(repo, args.ignore, args.types)
    rc, report = run_jscpd(repo, out, args.procs, args.ignore)
    if rc != 0:
        return rc
    blocks = fold(report.get("duplicates") or [], set(files))
    result = {"tool": "jscpd", "files": len(files), "clones": sum(len(b["places"]) - 1 for b in blocks),
              "rate": rate(blocks, repo, files), "blocks": blocks[:BLOCKS_KEPT]}
    if args.then:
        rev = rev_before(repo, args.then)
        measured = rate_at(repo, out, rev, args.procs, args.ignore, args.types) if rev else None
        if measured:
            result["then"] = {"date": args.then, "rev": rev[:12], **measured}
    write(result, os.path.join(out, "duplicates.json"))
    return 0


if __name__ == "__main__":
    sys.exit(main())

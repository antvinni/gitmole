"""Bug-inducing commits by R-SZZ, from git alone, for the backtest's second outcome.

The watch list's backtest scores "a fix-labelled commit touched the file in the six months after
the cut-off": fix locality, which a changelog or a config file scores without ever being wrong.
The SZZ family gives the other label, defect insertion: the commit that wrote the lines a fix
removed. Rosa et al. (ICSE 2021, JSS 2023) measured the git-only variants against a
developer-informed oracle and found R-SZZ, which keeps only the most recent candidate per fix,
the best of them at precision 0.66 against 0.39 for keeping every candidate. This is that variant:

1. the lines a fix removed or changed, per modified file, from `git diff -U0 fix^ fix`;
2. `git blame -w -C -C` of the parent at those lines, so whitespace and moved code do not mislead;
3. files the caller excludes (tests, vendored, generated) are not candidates;
4. of the commits blamed, the most recent by author date is the bug-inducing one, with the files
   whose blamed lines it wrote.

An insert-only fix blames nothing and R-SZZ finds nothing for it; that is the known blind spot.
A development tool behind `python -m gitmole.evaluate --szz`, not a pipeline step: one blame per
(fix, file) is minutes over a large history, and the report's own backtest stays the cheap one."""
from __future__ import annotations

import csv
import datetime as dt
import re
import subprocess

from . import filetypes

_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+\d+(?:,\d+)? @@")
_HEADER = re.compile(r"^([0-9a-f]{40,64}) \d+ \d+(?: \d+)?$")
_HASH = re.compile(r"^[0-9a-f]{7,64}$")


def _git(repo: str, *args) -> str:
    return subprocess.run([*filetypes.GIT, *args], cwd=repo, capture_output=True, check=True).stdout.decode("utf-8", "replace")


def deleted_ranges(repo: str, fix: str) -> dict:
    """{path: [(start, count)]} of the parent-side lines a fix removed or changed, for every file it
    modified (added and deleted files have no parent version to blame). An empty list is a file
    that only gained lines."""
    out, path = {}, None
    text = _git(repo, "diff", "-U0", "--diff-filter=M", "--no-color", f"{fix}^", fix)
    for line in text.split("\n"):
        if line.startswith("diff --git "):
            path = None
        elif line.startswith("+++ b/"):
            path = filetypes.unquote(line[6:])
            out.setdefault(path, [])
        elif path is not None and line.startswith("@@"):
            m = _HUNK.match(line)
            if not m:
                continue
            start, count = int(m.group(1)), int(m.group(2)) if m.group(2) is not None else 1
            if count:
                out[path].append((start, count))
    return out


def blame_lines(repo: str, rev: str, path: str, ranges: list) -> dict:
    """{commit: {"time": author epoch, "lines": n}} for the given parent-side line ranges, blamed
    with whitespace ignored and moves followed (-w -C -C: AG-SZZ's robustness for free)."""
    if not ranges:
        return {}
    argv = ["blame", "-w", "-C", "-C", "--line-porcelain"]
    for start, count in ranges:
        argv += ["-L", f"{start},{start + count - 1}"]
    try:
        text = _git(repo, *argv, rev, "--", path)
    except subprocess.CalledProcessError:
        return {}
    out, current = {}, None
    for line in text.split("\n"):
        m = _HEADER.match(line)
        if m:
            current = out.setdefault(m.group(1), {"time": 0, "lines": 0})
            current["lines"] += 1
        elif current is not None and line.startswith("author-time "):
            current["time"] = int(line[12:])
    return out


def bug_inducing(repo: str, fix: str, exclude=None):
    """{"commit", "date", "files"} for the R-SZZ pick of a fix: the most recent commit its deleted
    lines blame to, and the files whose lines it wrote; None when nothing blames (an insert-only
    fix, or every touched file excluded). `exclude(path)` says which files are not candidates; test
    files never are."""
    candidates = {}
    for path, ranges in deleted_ranges(repo, fix).items():
        if filetypes.is_test_path(path) or (exclude and exclude(path)):
            continue
        for commit, info in blame_lines(repo, f"{fix}^", path, ranges).items():
            c = candidates.setdefault(commit, {"time": info["time"], "files": set()})
            c["time"] = max(c["time"], info["time"])
            c["files"].add(path)
    if not candidates:
        return None
    commit = max(candidates, key=lambda c: (candidates[c]["time"], c))
    when = dt.datetime.fromtimestamp(candidates[commit]["time"], dt.timezone.utc).date().isoformat()
    return {"commit": commit, "date": when, "files": sorted(candidates[commit]["files"])}


_TRUE = {"true", "1", "yes", "buggy"}
_COMMIT_COLUMNS = ("commit_id", "commit", "hash", "sha", "bug_commit", "bic")
_PATH_COLUMNS = ("path", "file", "filepath", "file_path", "filename")


def read_labels(path: str) -> dict:
    """Independent bug-inducing labels: {commit: [paths] or None}. Three shapes: ApacheJIT's CSV
    (a `commit_id` column and a `buggy` flag; only the buggy rows count), Defectors' file-level
    rows (a commit column and a path column), or a bare list of hashes, one per line."""
    out = {}
    with open(path, encoding="utf-8", errors="replace", newline="") as fh:
        rows = list(csv.reader(fh))
    if not rows:
        return out
    head = [h.strip().lower() for h in rows[0]]
    commit_col = next((i for i, h in enumerate(head) if h in _COMMIT_COLUMNS), None)
    if commit_col is None:
        for row in rows:
            if row and _HASH.match(row[0].strip()):
                out[row[0].strip()] = None
        return out
    buggy_col = next((i for i, h in enumerate(head) if h == "buggy"), None)
    path_col = next((i for i, h in enumerate(head) if h in _PATH_COLUMNS), None)
    for row in rows[1:]:
        if len(row) <= commit_col or not row[commit_col].strip():
            continue
        if buggy_col is not None and (len(row) <= buggy_col or row[buggy_col].strip().lower() not in _TRUE):
            continue
        commit = row[commit_col].strip()
        if path_col is not None and len(row) > path_col and row[path_col].strip():
            out[commit] = (out.get(commit) or []) + [row[path_col].strip()]
        else:
            out.setdefault(commit, None)
    return out

#!/usr/bin/env python3
"""Code age from one `git blame` per tracked text file at HEAD.

Writes theseus/cohorts.json and theseus/authors.json in the layout
git-of-theseus produces (one sample, dated now), so the loader and the
"surviving code by year" table work unchanged. Standalone on purpose:
gitmole runs it as `python3 blame.py REPO OUT_DIR [--procs N] [--ignore GLOB]... [--aliases META_JSON]`.
"""
from __future__ import annotations

import datetime as dt
import fnmatch
import json
import os
import subprocess
import sys
import time
from collections import Counter
from multiprocessing import Pool


def default_procs(cpu: int = None) -> int:
    """Leave two cores free so the machine stays usable while blame runs."""
    cpu = cpu or os.cpu_count() or 2
    return max(1, cpu - 2)


def _low_priority():
    try:
        os.nice(10)
    except OSError:
        pass


try:
    from . import filetypes
except ImportError:  # run as a script: the package directory is sys.path[0]
    import filetypes


def text_files(repo: str, ignore=()) -> list:
    """Tracked, non-binary files, minus ignore globs."""
    out = subprocess.run(["git", "-c", "core.quotePath=false", "grep", "-I", "--name-only", "--cached", "-e", ""], cwd=repo, capture_output=True, text=True).stdout
    files = sorted(set(out.split("\n")) - {""})
    return [f for f in files if not any(fnmatch.fnmatch(f, g) for g in ignore)]


def code_files(repo: str, ignore=(), types=filetypes.DEFAULT) -> list:
    """text_files() restricted to source file types (None = no restriction)."""
    return [f for f in text_files(repo, ignore) if filetypes.matches(f, types)]


def blame_file(repo: str, path: str) -> dict:
    """{(year, author): lines} for one file at HEAD."""
    proc = subprocess.run(["git", "blame", "--line-porcelain", "HEAD", "--", path], cwd=repo, capture_output=True, text=True, errors="replace")
    if proc.returncode != 0:
        return {}
    counts, author, year = Counter(), None, None
    for line in proc.stdout.split("\n"):
        if line.startswith("author "):
            author = line[7:]
        elif line.startswith("author-time "):
            year = str(dt.datetime.fromtimestamp(int(line[12:]), dt.timezone.utc).year)
        elif line.startswith("\t"):
            counts[(year, author)] += 1
    return dict(counts)


def _job(args):
    return blame_file(*args)


def estimate(repo: str, files: list = None, ignore=(), sample: int = 25, procs: int = None, timer=time.monotonic, types=filetypes.DEFAULT) -> dict:
    """Project the wall time of the pass by timing a spread of `sample` blames single-threaded."""
    files = code_files(repo, ignore, types) if files is None else files
    procs = procs or default_procs()
    n = len(files)
    if not n or not sample:
        return {"files": n, "seconds": 0.0, "sampled": 0}
    step = max(1, n // sample)
    picked = files[::step][:sample]
    t0 = timer()
    for f in picked:
        blame_file(repo, f)
    per_file = (timer() - t0) / len(picked)
    return {"files": n, "seconds": per_file * n / procs, "sampled": len(picked)}


def aliases_from_meta(path: str) -> dict:
    with open(path) as fh:
        meta = json.load(fh)
    if "aliases" in meta:
        return dict(meta["aliases"])
    return {a["name"]: i["name"] for i in meta.get("identities", []) for a in i.get("aliases", [])}


def _series(counter: Counter, label) -> dict:
    now = dt.datetime.now().replace(microsecond=0).isoformat()
    items = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
    return {"labels": [label(k) for k, _ in items], "ts": [now], "y": [[n] for _, n in items]}


def write_all(repo: str, out_dir: str, ignore=(), aliases_path: str = None, procs: int = None, types=filetypes.DEFAULT) -> dict:
    aliases = aliases_from_meta(aliases_path) if aliases_path else {}
    files = code_files(repo, ignore, types)
    years, authors = Counter(), Counter()
    with Pool(procs or default_procs(), initializer=_low_priority) as pool:
        for counts in pool.imap_unordered(_job, [(repo, f) for f in files], chunksize=8):
            for (year, author), n in counts.items():
                years[year] += n
                authors[aliases.get(author, author)] += n
    os.makedirs(os.path.join(out_dir, "theseus"), exist_ok=True)
    cohorts = _series(years, lambda y: f"Code added in {y}")
    order = sorted(range(len(cohorts["labels"])), key=lambda i: cohorts["labels"][i])
    cohorts = {"labels": [cohorts["labels"][i] for i in order], "ts": cohorts["ts"], "y": [cohorts["y"][i] for i in order]}
    with open(os.path.join(out_dir, "theseus", "cohorts.json"), "w") as fh:
        json.dump(cohorts, fh)
    with open(os.path.join(out_dir, "theseus", "authors.json"), "w") as fh:
        json.dump(_series(authors, lambda a: a), fh)
    return {"files": len(files), "lines": sum(years.values())}


if __name__ == "__main__":
    args = sys.argv[1:]
    procs, aliases, ignore, types = None, None, [], filetypes.DEFAULT
    while "--types" in args:
        i = args.index("--types"); types = filetypes.parse(args[i + 1]); del args[i:i + 2]
    while "--procs" in args:
        i = args.index("--procs"); procs = int(args[i + 1]); del args[i:i + 2]
    while "--aliases" in args:
        i = args.index("--aliases"); aliases = args[i + 1]; del args[i:i + 2]
    while "--ignore" in args:
        i = args.index("--ignore"); ignore.append(args[i + 1]); del args[i:i + 2]
    if len(args) != 2:
        sys.exit("usage: blame.py REPO OUT_DIR [--procs N] [--ignore GLOB]... [--aliases META_JSON] [--types LIST|all]")
    print(json.dumps(write_all(args[0], args[1], ignore, aliases, procs, types)))

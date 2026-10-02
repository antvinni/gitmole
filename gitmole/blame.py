#!/usr/bin/env python3
"""Code age from one `git blame` per tracked text file at HEAD.

Writes theseus/cohorts.json and theseus/authors.json in the layout
git-of-theseus produces (one sample, dated now), so the loader and the
"surviving code by year" table work unchanged. Standalone on purpose:
gitmole runs it as `python3 blame.py REPO OUT_DIR [--procs N] [--ignore GLOB]... [--aliases META_JSON] [--log LOG]`.

With the change log, a line from a commit with Co-authored-by trailers is
shared equally between its author and the people the trailers name, so a
squash-merged repository does not attribute every line to whoever pressed
the button.

Each author label is `Name <email>` (label()), the identity git shows through
.mailmap, not a display name: two people who share a name, or a person and a
trailer-only alias of the same spelling, are two rows of the People table, and
each keeps its own lines. The loader canonicalises the name for every table
that keys people by name, and matches the pair to its identity row.
"""
from __future__ import annotations

import bisect
import datetime as dt
import fnmatch
import json
import os
import re
import subprocess
import sys
from collections import Counter
from multiprocessing import Pool


def default_procs(cpu: int = None) -> int:
    """Leave two cores free so the machine stays usable while blame runs."""
    cpu = cpu or os.cpu_count() or 2
    return max(1, cpu - 2)


def _low_priority(shared: dict = None, imported=()):
    try:
        os.nice(10)
    except OSError:
        pass
    if shared:
        set_co_authors(shared)
    set_imported(imported)


try:
    from . import filetypes, maat
except ImportError:  # run as a script: the package directory is sys.path[0]
    import filetypes
    import maat

_CO_AUTHORS = {}       # abbreviated commit hash -> the co-authors' labels (label()); set in every worker by the pool initializer
_HASH_LENGTHS = ()     # the abbreviation lengths the log used, so a blame's full hash can be looked up by prefix
_IMPORTED = ()         # abbreviated hashes of the import commits (maat.importing): their lines are nobody's


def set_imported(hashes) -> None:
    global _IMPORTED
    _IMPORTED = tuple(hashes or ())


def _is_imported(full_hash: str) -> bool:
    return any(full_hash.startswith(h) for h in _IMPORTED)


def label(name: str, email: str) -> str:
    """An identity as authors.json names it: `Name <email>`, git's own spelling."""
    return f"{name} <{email}>"


def co_authors_by_commit(log_text: str, aliases: dict = None) -> dict:
    """From the change log, the commits that name co-authors: {hash: [label(name, email)]}, the trailer's own
    name and address, and the same people maat's parse_log counts (canonicalised through `aliases` to leave
    out the author and to name each person once)."""
    aliases = aliases or {}
    out = {}
    for line in log_text.split("\n"):
        if not line.startswith("--"):
            continue
        parts = line.split("--", 4)
        if len(parts) < 4:
            continue
        h, author = parts[1], aliases.get(parts[3], parts[3])
        trailers = (parts[4] if len(parts) > 4 else "").partition(maat.TRAILER_SEP)[2]
        crew = [label(n, e) for n, e in maat.co_author_idents(trailers, author, aliases, set())]
        if crew:
            out[h] = crew
    return out


def imports_in(log_text: str, types=filetypes.DEFAULT) -> list:
    """The hashes of the log's import commits, the way the change analysis finds them."""
    return [c["hash"] for c in maat.importing(maat.parse_log(log_text, None, types))]


def set_co_authors(shared: dict) -> None:
    global _CO_AUTHORS, _HASH_LENGTHS
    _CO_AUTHORS = dict(shared)
    _HASH_LENGTHS = tuple(sorted({len(h) for h in _CO_AUTHORS}))


def _shared_with(full_hash: str) -> list:
    for n in _HASH_LENGTHS:
        found = _CO_AUTHORS.get(full_hash[:n])
        if found:
            return found
    return []


def drop_ignored(files: list, ignore=()) -> list:
    """The files no ignore glob matches."""
    return [f for f in files if not any(fnmatch.fnmatch(f, g) for g in ignore)]


def text_files(repo: str, ignore=(), paths=()) -> list:
    """Tracked, non-binary files, minus ignore globs; only those under `paths` (--path's directories) when given."""
    spec = ["--", *(":(literal)" + d for d in paths)] if paths else []   # literal: a directory named with * or ? is that directory
    return drop_ignored(filetypes.git_paths(repo, "grep", "-I", "--name-only", "--cached", "-e", "", *spec), ignore)


def code_files(repo: str, ignore=(), types=filetypes.DEFAULT, paths=()) -> list:
    """text_files() restricted to source file types (None = no restriction)."""
    return [f for f in text_files(repo, ignore, paths) if filetypes.matches(f, types)]


_HEADER = re.compile(r"^[0-9a-f]{40,64} \d+ \d+")


def blame_file(repo: str, path: str) -> dict:
    """{(year, label(name, email)): lines} for one file at HEAD. A line from a commit with co-authors (see
    set_co_authors) is split equally between everyone it credits, so the values are fractional
    then; whole lines are rounded once, when the totals are written. A line an import commit wrote
    (set_imported) counts for its year under the author None: it survives, but nobody here wrote it."""
    proc = subprocess.run(["git", "blame", "--line-porcelain", "HEAD", "--", path], cwd=repo, capture_output=True, text=True, errors="replace")
    if proc.returncode != 0:
        return {}
    counts, author, name, year, crew, imported = Counter(), None, None, None, [], False
    for line in proc.stdout.split("\n"):
        if line.startswith("author "):
            name = line[7:]
        elif line.startswith("author-mail "):
            author = label(name, line[12:].strip().strip("<>"))
        elif line.startswith("author-time "):
            year = str(dt.datetime.fromtimestamp(int(line[12:]), dt.timezone.utc).year)
        elif line.startswith("\t"):
            if imported:
                counts[(year, None)] += 1
            elif crew:
                share = 1 / (1 + len(crew))
                counts[(year, author)] += share
                for who in crew:
                    counts[(year, who)] += share
            else:
                counts[(year, author)] += 1
        elif _HEADER.match(line):
            full = line.split(" ", 1)[0]
            crew = _shared_with(full) if _HASH_LENGTHS else []
            imported = bool(_IMPORTED) and _is_imported(full)
    return {k: (int(v) if float(v).is_integer() else v) for k, v in counts.items()}


def _job(args):
    return blame_file(*args)


# Blame's work is the history it walks: from HEAD back to the oldest commit that still owns a line of the
# file, it visits every commit and asks whether the path changed. The count of those commits is a property of
# the commit being analysed, the same on any machine at any load, where a stopwatch over a sample is not:
# django's timed projection ran code age at load 2.4-2.7 and skipped it at 3.05, 7.29 and 8.05 (0.39.0-0.43.0).
# The rate turns that count into seconds once, on the reference machine (10 cores, so 8 blame workers),
# fitted over the 15 corpus clones' 25-file samples at load 2.6-4 on 1 Oct 2026: seconds on 8 workers =
# 9.06e-7 x commits walked, least squares on the log error, rms 0.51 (yt-dlp 13 s against a timed 34,
# binutils-gdb 947 against 1,639). It is a fixed exchange rate, not a measurement of this machine.
SECONDS_PER_COMMIT_WALKED = 7.2e-6   # one core on the reference machine: 9.0e-7 s across its 8 workers
REFERENCE_WORKERS = 8


def history_times(repo: str) -> list:
    """The committer times of every commit HEAD reaches, oldest first: what a blame of HEAD can walk."""
    out = subprocess.run(["git", "log", "--format=%ct", "HEAD"], cwd=repo, capture_output=True, text=True)
    return sorted(int(t) for t in out.stdout.split()) if out.returncode == 0 else []


def commits_walked(repo: str, path: str, history: list) -> int:
    """How many of HEAD's commits a blame of `path` walks: those no older than the oldest commit that still
    owns one of its lines, where the walk can stop."""
    proc = subprocess.run(["git", "blame", "--line-porcelain", "HEAD", "--", path], cwd=repo, capture_output=True, text=True, errors="replace")
    oldest = min((int(line[15:]) for line in proc.stdout.split("\n") if line.startswith("committer-time ")), default=None) \
        if proc.returncode == 0 else None
    return 0 if oldest is None else len(history) - bisect.bisect_left(history, oldest)


def estimate(repo: str, files: list = None, ignore=(), sample: int = 25, types=filetypes.DEFAULT, budget: float = None,
             history: list = None) -> dict:
    """Project the pass from the work a spread of `sample` blames does: the commits each walks
    (commits_walked), scaled to every file and priced at the reference machine's rate. The same commit gives
    the same projection on any machine at any load, so whether code age runs depends on the work alone.
    With a budget, sampling stops as soon as the walks already counted prove the projection over it: the
    blames left can only add to the total, so the skip is the one the whole sample would have decided, and
    `seconds` is then a lower bound (`partial`)."""
    files = code_files(repo, ignore, types) if files is None else files
    n = len(files)
    if not n or not sample:
        return {"files": n, "seconds": 0.0, "sampled": 0, "commits_walked": 0}
    history = history_times(repo) if history is None else history
    step = max(1, n // sample)
    picked = files[::step][:sample]
    rate = SECONDS_PER_COMMIT_WALKED / REFERENCE_WORKERS
    walked = 0
    for i, f in enumerate(picked, 1):
        walked += commits_walked(repo, f, history)
        if budget is not None and i < len(picked):
            floor = walked / len(picked) * n * rate
            if floor > budget:
                return {"files": n, "seconds": floor, "sampled": i, "commits_walked": round(walked / len(picked) * n), "partial": True}
    total = walked / len(picked) * n
    return {"files": n, "seconds": total * rate, "sampled": len(picked), "commits_walked": round(total)}


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


def write_all(repo: str, out_dir: str, ignore=(), aliases_path: str = None, procs: int = None, types=filetypes.DEFAULT, log_path: str = None,
              paths=()) -> dict:
    aliases = aliases_from_meta(aliases_path) if aliases_path else {}
    shared, imported = {}, []
    if log_path and os.path.exists(log_path):
        with open(log_path, encoding="utf-8", errors="replace", newline="") as fh:
            text = fh.read()
        shared = co_authors_by_commit(text, aliases)
        imported = imports_in(text, types)
    files = code_files(repo, ignore, types, paths)
    years, authors = Counter(), Counter()
    with Pool(procs or default_procs(), initializer=_low_priority, initargs=(shared, imported)) as pool:
        for counts in pool.imap_unordered(_job, [(repo, f) for f in files], chunksize=8):
            for (year, author), n in counts.items():
                years[year] += n
                if author is not None:   # an import's lines count for their year and for nobody
                    authors[author] += n
    years = Counter({k: int(round(v)) for k, v in years.items()})
    authors = Counter({k: int(round(v)) for k, v in authors.items() if round(v)})
    os.makedirs(os.path.join(out_dir, "theseus"), exist_ok=True)
    cohorts = _series(years, lambda y: f"Code added in {y}")
    order = sorted(range(len(cohorts["labels"])), key=lambda i: cohorts["labels"][i])
    cohorts = {"labels": [cohorts["labels"][i] for i in order], "ts": cohorts["ts"], "y": [cohorts["y"][i] for i in order]}
    with open(os.path.join(out_dir, "theseus", "cohorts.json"), "w", encoding="utf-8") as fh:
        json.dump(cohorts, fh)
    with open(os.path.join(out_dir, "theseus", "authors.json"), "w", encoding="utf-8") as fh:
        json.dump(_series(authors, lambda a: a), fh)
    return {"files": len(files), "lines": sum(years.values())}


if __name__ == "__main__":
    args = sys.argv[1:]
    procs, aliases, ignore, types, log_path, paths = None, None, [], filetypes.DEFAULT, None, []
    while "--path" in args:
        i = args.index("--path"); paths.append(args[i + 1]); del args[i:i + 2]
    while "--log" in args:
        i = args.index("--log"); log_path = args[i + 1]; del args[i:i + 2]
    while "--types" in args:
        i = args.index("--types"); types = filetypes.parse(args[i + 1]); del args[i:i + 2]
    while "--procs" in args:
        i = args.index("--procs"); procs = int(args[i + 1]); del args[i:i + 2]
    while "--aliases" in args:
        i = args.index("--aliases"); aliases = args[i + 1]; del args[i:i + 2]
    while "--ignore" in args:
        i = args.index("--ignore"); ignore.append(args[i + 1]); del args[i:i + 2]
    if aliases:   # the files the run found to be source by shape (filetypes.scripts) count as the types do
        types = filetypes.with_scripts(types, filetypes.scripts_from_meta(aliases))
    if len(args) != 2:
        sys.exit("usage: blame.py REPO OUT_DIR [--procs N] [--ignore GLOB]... [--aliases META_JSON] [--types LIST|all] [--log LOG] [--path DIR]...")
    print(json.dumps(write_all(args[0], args[1], ignore, aliases, procs, types, log_path, paths)))

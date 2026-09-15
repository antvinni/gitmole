#!/usr/bin/env python3
"""Change analysis over a git log export, in the layout code-maat produced.

Standalone on purpose: gitmole runs it as a pipeline step with
`python3 maat.py LOG OUT_DIR [--aliases META_JSON]` and it must not need the
package on sys.path. Input is `git log --all --numstat --date=short
--pretty=format:--%h--%ad--%aN --no-renames`.
"""
from __future__ import annotations

import csv
import datetime as dt
import itertools
import json
import math
import os
import sys
from collections import Counter, defaultdict


def parse_log(text: str, aliases: dict = None) -> list:
    """[{hash, date, author, files: [(path, added, deleted)]}], binary files count as 0/0."""
    aliases = aliases or {}
    commits, current = [], None
    for line in text.splitlines():
        if line.startswith("--"):
            _, h, date, author = line.split("--", 3)
            current = {"hash": h, "date": date, "author": aliases.get(author, author), "files": []}
            commits.append(current)
        elif line.strip() and current is not None:
            added, deleted, path = line.split("\t", 2)
            current["files"].append((path, int(added) if added.isdigit() else 0, int(deleted) if deleted.isdigit() else 0))
    return commits


def _revs(commits) -> Counter:
    return Counter(path for c in commits for path, _, _ in c["files"])


def revisions(commits: list) -> list:
    return [{"entity": e, "n-revs": n} for e, n in sorted(_revs(commits).items(), key=lambda kv: (-kv[1], kv[0]))]


def coupling(commits: list, min_shared: int = 5, min_degree: int = 30, max_changeset: int = 30) -> list:
    revs = _revs(commits)
    shared = Counter()
    for c in commits:
        paths = sorted({p for p, _, _ in c["files"]})
        if len(paths) > max_changeset:
            continue
        for a, b in itertools.combinations(paths, 2):
            shared[(a, b)] += 1
    rows = []
    for (a, b), n in shared.items():
        if n < min_shared:
            continue
        avg = (revs[a] + revs[b]) / 2
        degree = int(math.floor(100 * n / avg + 0.5))
        if degree < min_degree:
            continue
        rows.append({"entity": a, "coupled": b, "degree": degree, "average-revs": int(math.floor(avg + 0.5))})
    rows.sort(key=lambda r: (-r["degree"], -r["average-revs"], r["entity"], r["coupled"]))
    return rows


def authors(commits: list) -> list:
    who, revs = defaultdict(set), _revs(commits)
    for c in commits:
        for p, _, _ in c["files"]:
            who[p].add(c["author"])
    rows = [{"entity": e, "n-authors": len(s), "n-revs": revs[e]} for e, s in who.items()]
    rows.sort(key=lambda r: (-r["n-authors"], -r["n-revs"], r["entity"]))
    return rows


def _months_between(earlier: str, later: str) -> int:
    a, b = dt.date.fromisoformat(earlier), dt.date.fromisoformat(later)
    return max(0, (b.year - a.year) * 12 + (b.month - a.month) - (1 if b.day < a.day else 0))


def age(commits: list, now: str = None) -> list:
    now = now or dt.date.today().isoformat()
    last = {}
    for c in commits:
        for p, _, _ in c["files"]:
            last[p] = max(last.get(p, ""), c["date"])
    rows = [{"entity": e, "age-months": _months_between(d, now)} for e, d in last.items()]
    rows.sort(key=lambda r: (r["age-months"], r["entity"]))
    return rows


def entity_ownership(commits: list) -> list:
    added, deleted = Counter(), Counter()
    for c in commits:
        for p, a, d in c["files"]:
            added[(p, c["author"])] += a
            deleted[(p, c["author"])] += d
    rows = [{"entity": p, "author": who, "added": added[(p, who)], "deleted": deleted[(p, who)]} for (p, who) in added]
    rows.sort(key=lambda r: (r["entity"], r["author"]))
    return rows


ANALYSES = {
    "revisions": (revisions, ["entity", "n-revs"]),
    "coupling": (coupling, ["entity", "coupled", "degree", "average-revs"]),
    "authors": (authors, ["entity", "n-authors", "n-revs"]),
    "age": (age, ["entity", "age-months"]),
    "entity-ownership": (entity_ownership, ["entity", "author", "added", "deleted"]),
}


def aliases_from_meta(path: str) -> dict:
    with open(path) as fh:
        meta = json.load(fh)
    out = {}
    for ident in meta.get("identities", []):
        for a in ident.get("aliases", []):
            out[a["name"]] = ident["name"]
    return out


def write_all(log_path: str, out_dir: str, aliases_path: str = None) -> None:
    with open(log_path, encoding="utf-8", errors="replace") as fh:
        commits = parse_log(fh.read(), aliases_from_meta(aliases_path) if aliases_path else None)
    for name, (fn, header) in ANALYSES.items():
        with open(os.path.join(out_dir, f"maat-{name}.csv"), "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=header)
            w.writeheader()
            w.writerows(fn(commits))


if __name__ == "__main__":
    args = sys.argv[1:]
    aliases = None
    if "--aliases" in args:
        i = args.index("--aliases")
        aliases = args[i + 1]
        del args[i:i + 2]
    if len(args) != 2:
        sys.exit("usage: maat.py LOG OUT_DIR [--aliases META_JSON]")
    write_all(args[0], args[1], aliases)

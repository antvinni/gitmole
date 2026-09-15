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

try:
    from . import filetypes
except ImportError:  # run as a script: the package directory is sys.path[0]
    import filetypes


def parse_log(text: str, aliases: dict = None, types=None) -> list:
    """[{hash, date, time, author, files: [(path, added, deleted)]}], binary files count as 0/0.
    `types` restricts the file entries (None = keep everything); commits are always kept."""
    aliases = aliases or {}
    commits, current = [], None
    for line in text.splitlines():
        if line.startswith("--"):
            _, h, when, author = line.split("--", 3)
            current = {"hash": h, "date": when[:10], "time": when, "author": aliases.get(author, author), "files": []}
            commits.append(current)
        elif line.strip() and current is not None:
            added, deleted, path = line.split("\t", 2)
            if not filetypes.matches(path, types):
                continue
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


def activity(commits: list) -> dict:
    """Commits by weekday (Mon=0) and hour, by month, and per-author totals."""
    by_weekday, by_hour, by_month, net_by_year = [0] * 7, [0] * 24, Counter(), Counter()
    authors, timeline = {}, defaultdict(Counter)
    for c in commits:
        when = c.get("time") or c["date"]
        try:
            stamp = dt.datetime.fromisoformat(when)
        except ValueError:
            stamp = None
        day = stamp.date() if stamp else dt.date.fromisoformat(c["date"])
        by_weekday[day.weekday()] += 1
        if stamp and len(when) > 10:
            by_hour[stamp.hour] += 1
        by_month[c["date"][:7]] += 1
        net_by_year[c["date"][:4]] += sum(a - d for _, a, d in c["files"])
        timeline[c["author"]][c["date"][:7]] += 1
        a = authors.setdefault(c["author"], {"commits": 0, "added": 0, "deleted": 0, "first": c["date"], "last": c["date"]})
        a["commits"] += 1
        a["added"] += sum(x for _, x, _ in c["files"])
        a["deleted"] += sum(x for _, _, x in c["files"])
        a["first"], a["last"] = min(a["first"], c["date"]), max(a["last"], c["date"])
    return {"by_weekday": by_weekday, "by_hour": by_hour, "by_month": dict(sorted(by_month.items())),
            "net_by_year": dict(sorted(net_by_year.items())), "authors": authors,
            "timeline": {a: dict(sorted(m.items())) for a, m in timeline.items()}}


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


def write_all(log_path: str, out_dir: str, aliases_path: str = None, types=filetypes.DEFAULT) -> None:
    """GITMOLE_NOW=YYYY-MM-DD fixes the reference date for file ages (used by the end-to-end test)."""
    now = os.environ.get("GITMOLE_NOW") or None
    with open(log_path, encoding="utf-8", errors="replace") as fh:
        commits = parse_log(fh.read(), aliases_from_meta(aliases_path) if aliases_path else None, types)
    for name, (fn, header) in ANALYSES.items():
        rows = age(commits, now=now) if name == "age" else fn(commits)
        with open(os.path.join(out_dir, f"maat-{name}.csv"), "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=header)
            w.writeheader()
            w.writerows(rows)
    with open(os.path.join(out_dir, "activity.json"), "w") as fh:
        json.dump(activity(commits), fh)


if __name__ == "__main__":
    args = sys.argv[1:]
    aliases, types = None, filetypes.DEFAULT
    while "--types" in args:
        i = args.index("--types"); types = filetypes.parse(args[i + 1]); del args[i:i + 2]
    if "--aliases" in args:
        i = args.index("--aliases")
        aliases = args[i + 1]
        del args[i:i + 2]
    if len(args) != 2:
        sys.exit("usage: maat.py LOG OUT_DIR [--aliases META_JSON] [--types LIST|all]")
    write_all(args[0], args[1], aliases, types)

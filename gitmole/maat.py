#!/usr/bin/env python3
"""Change analysis over a git log export, in the layout code-maat produced.

Standalone on purpose: gitmole runs it as a pipeline step with
`python3 maat.py LOG OUT_DIR [--aliases META_JSON]` and it must not need the
package on sys.path. Input is `git log HEAD --numstat --date=short
--pretty=format:--%h--%ad--%aN--%s%x1f%(trailers:key=Co-authored-by,...) -M -w
--ignore-blank-lines`: renames are followed, so a moved file is one entity
under its new path and a pure move adds and deletes nothing (whoever moved a
directory to src/ did not write it); whitespace-only hunks count no lines, so a
file a reformat only re-indented is not a revision; and the Co-authored-by
trailers name the other people on a commit, who count as its authors too.

Sweeping commits, the ones that touch more files than 99% of the history's
commits and take out as many lines as they put in (a formatter run, a rename
across the tree, a copyright-year bump), are left out of every table but the
activity totals, along with the commits the repository itself declares
uninteresting in .git-blame-ignore-revs; activity.json lists them.
"""
from __future__ import annotations

import csv
import datetime as dt
import itertools
import json
import math
import os
import re
import sys
from collections import Counter, defaultdict

try:
    from . import filetypes, identity
except ImportError:  # run as a script: the package directory is sys.path[0]
    import filetypes
    import identity

TRAILER_SEP = "\x1f"   # the unit separator between the subject and each Co-authored-by value in the log
_TRAILER = re.compile(r"^\s*(?P<name>[^<]*?)\s*(?:<(?P<email>[^>]*)>)?\s*$")


def _co_authors(field: str, author: str, aliases: dict, bots: set) -> list:
    """The people a commit's Co-authored-by trailers name, canonicalised, each once, without the
    author (GitHub adds the trailer to a squash merge for its own author too) and without bots."""
    out = []
    for value in field.split(TRAILER_SEP):
        m = _TRAILER.match(value)
        if not m or not m.group("name"):
            continue
        name, email = m.group("name"), m.group("email") or ""
        if name in bots or identity.is_bot(name, email):
            continue
        name = aliases.get(name, name)
        if name != author and name not in out:
            out.append(name)
    return out


def parse_log(text: str, aliases: dict = None, types=None, bots: set = None) -> list:
    """[{hash, date, time, author, subject, co_authors, files: [(path, added, deleted)]}], binary files
    count as 0/0. `types` restricts the file entries (None = keep everything); commits are always kept.
    `bots` are names the run decided are services; they are never co-authors."""
    aliases = aliases or {}
    bots = bots or set()
    commits, current = [], None
    # split on newlines only: str.splitlines also breaks on \r, form feed and Unicode separators,
    # any of which can appear inside a commit subject
    for line in text.split("\n"):
        if line.startswith("--"):
            parts = line.split("--", 4)          # subject is last, so dashes inside it survive
            _, h, when, author = parts[:4]
            subject, _, trailers = (parts[4] if len(parts) > 4 else "").partition(TRAILER_SEP)
            author = aliases.get(author, author)
            current = {"hash": h, "date": when[:10], "time": when, "author": author, "subject": subject,
                       "co_authors": _co_authors(trailers, author, aliases, bots), "files": []}
            commits.append(current)
        elif line.strip() and current is not None:
            added, deleted, path = line.split("\t", 2)
            path = _renamed_to(filetypes.unquote(path))
            if not filetypes.matches(path, types):
                continue
            current["files"].append((path, int(added) if added.isdigit() else 0, int(deleted) if deleted.isdigit() else 0))
    return commits


_BRACED_RENAME = re.compile(r"\{([^{}]*) => ([^{}]*)\}")


def _renamed_to(path: str) -> str:
    """The new path of a rename as `git log -M --numstat` spells it: `{old => new}/rest`,
    `dir/{a => b}` or `old => new` for a whole path. A path without ' => ' is itself."""
    if " => " not in path:
        return path
    if "{" in path:
        return _BRACED_RENAME.sub(lambda m: m.group(2), path).replace("//", "/")
    return path.split(" => ", 1)[1]


_FIX_CONVENTIONAL = re.compile(r"^(fix|hotfix|bugfix)(\([^)]*\))?!?:", re.I)
_FIX_WORDS = re.compile(r"\b(fix|fixes|fixed|fixing|bugfix|hotfix|bug|bugs|regression|crash|crashes)\b", re.I)


def is_fix(subject: str) -> bool:
    """Does the commit subject describe a bug fix? Conventional `fix:` or plain fix/bug words."""
    return bool(_FIX_CONVENTIONAL.match(subject or "") or _FIX_WORDS.search(subject or ""))


def is_revert(subject: str) -> bool:
    """git's own revert subject: `Revert "..."`. Case-sensitive, the quote is not required."""
    return (subject or "").startswith("Revert ")


def _revs(commits) -> Counter:
    return Counter(path for c in commits for path, _, _ in c["files"])


def people(c: dict) -> list:
    """Everyone a commit credits: its author and the co-authors its trailers name."""
    return [c["author"], *c.get("co_authors", ())]


SWEEP_MIN_FILES = 20      # under this many files a commit is not a sweep, whatever the history
SWEEP_PERCENTILE = 0.99   # a sweep touches at least as many files as this share of the history's commits
SWEEP_TOLERANCE = 0.1     # ...and adds within this fraction of what it deletes


def sweeping(commits: list, min_files: int = SWEEP_MIN_FILES, percentile: float = SWEEP_PERCENTILE, tolerance: float = SWEEP_TOLERANCE) -> list:
    """The commits that touch at least as many files as the repository's own 99th percentile (never
    fewer than `min_files`) and add within 10% of what they delete: a formatter run, a rename across
    the tree, a copyright-year bump. Each counts as a revision of every file it touches and couples
    them all to each other, which is exactly the noise that inflates revisions × lines of code on a
    repository that adopted a formatter. A merge exports no file list and is never a sweep; an
    import or a deletion adds far more than it removes, or the reverse, and is not one either."""
    sizes = sorted(len(c["files"]) for c in commits if c["files"])
    if not sizes:
        return []
    cut = max(min_files, sizes[min(len(sizes) - 1, int(math.ceil(percentile * len(sizes))) - 1)])
    out = []
    for c in commits:
        if len(c["files"]) < cut:
            continue
        added, deleted = sum(a for _, a, _ in c["files"]), sum(d for _, _, d in c["files"])
        if abs(added - deleted) <= tolerance * max(added, deleted):
            out.append(c)
    return out


_SHA = re.compile(r"^[0-9a-f]{7,64}$")


def read_ignore_revs(paths: list) -> set:
    """The commits a repository declares uninteresting: the SHAs in its .git-blame-ignore-revs (and
    the file blame.ignoreRevsFile names), lowercased, past comments and blank lines. A missing file
    declares nothing."""
    out = set()
    for path in paths:
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                lines = fh.read().split("\n")
        except OSError:
            continue
        for line in lines:
            token = line.split("#", 1)[0].strip().lower()
            if token and _SHA.match(token):
                out.add(token)
    return out


def is_ignored(h: str, revs: set) -> bool:
    """Whether the log's abbreviated hash names a declared commit: one is a prefix of the other."""
    h = h.lower()
    return h in revs or any(full.startswith(h) or h.startswith(full) for full in revs)


def analysed(commits: list, ignored: set = frozenset()) -> list:
    """The commits every table but the activity totals reads: without the sweeps and the declared."""
    swept = {c["hash"] for c in sweeping(commits)}
    return [c for c in commits if c["hash"] not in swept and c["hash"] not in ignored]


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


MINOR_SHARE = 0.05   # Bird et al., "Don't Touch My Code!": under this share of a file's commits, a contributor is minor


def authors(commits: list) -> list:
    """Per entity: how many people committed to it (co-authors included), its revisions, and how many
    of those people are minor contributors, with under 5% of its commits each. Bird et al. found that
    count the strongest ownership predictor of failures; the sole owner is the knowledge risk."""
    who, revs = defaultdict(Counter), _revs(commits)
    for c in commits:
        for p, _, _ in c["files"]:
            for person in people(c):
                who[p][person] += 1
    rows = [{"entity": e, "n-authors": len(s), "n-revs": revs[e], "minor": sum(1 for n in s.values() if n / revs[e] < MINOR_SHARE)}
            for e, s in who.items()]
    rows.sort(key=lambda r: (-r["n-authors"], -r["n-revs"], r["entity"]))
    return rows


def soc(commits: list, min_shared: int = 5, max_changeset: int = 30) -> list:
    """Sum of coupling, Tornhill's measure of architectural significance: per entity, its co-changes
    with any other file across the changesets coupling() reads (those within `max_changeset` files),
    and how many distinct files it shares at least `min_shared` commits with. Pairwise degree finds
    the pairs; this finds the file weakly coupled to everything."""
    shared = Counter()
    for c in commits:
        paths = sorted({p for p, _, _ in c["files"]})
        if len(paths) > max_changeset:
            continue
        for a, b in itertools.combinations(paths, 2):
            shared[(a, b)] += 1
    total, partners = Counter(), Counter()
    for (a, b), n in shared.items():
        total[a] += n
        total[b] += n
        if n >= min_shared:
            partners[a] += 1
            partners[b] += 1
    rows = [{"entity": e, "soc": n, "partners": partners[e]} for e, n in total.items()]
    rows.sort(key=lambda r: (-r["soc"], -r["partners"], r["entity"]))
    return rows


def _months_between(earlier: str, later: str) -> int:
    a, b = dt.date.fromisoformat(earlier), dt.date.fromisoformat(later)
    return max(0, (b.year - a.year) * 12 + (b.month - a.month) - (1 if b.day < a.day else 0))


def months_before(date: str, months: int) -> str:
    """The ISO date `months` whole months before `date`, day clamped to the month's length."""
    import calendar
    d = dt.date.fromisoformat(date)
    y, m = d.year, d.month - months
    while m <= 0:
        y, m = y - 1, m + 12
    return dt.date(y, m, min(d.day, calendar.monthrange(y, m)[1])).isoformat()


def age(commits: list, now: str = None) -> list:
    now = now or dt.date.today().isoformat()
    last = {}
    for c in commits:
        for p, _, _ in c["files"]:
            last[p] = max(last.get(p, ""), c["date"])
    rows = [{"entity": e, "age-months": _months_between(d, now)} for e, d in last.items()]
    rows.sort(key=lambda r: (r["age-months"], r["entity"]))
    return rows


RECENT_MONTHS = 6


def fixes(commits: list, now: str = None) -> list:
    """Per entity: how many fix commits touched it, the last one, and how many in the recent window."""
    now = now or dt.date.today().isoformat()
    total, last, recent = Counter(), {}, Counter()
    for c in commits:
        if not is_fix(c.get("subject", "")):
            continue
        fresh = _months_between(c["date"], now) < RECENT_MONTHS
        for p, _, _ in c["files"]:
            total[p] += 1
            last[p] = max(last.get(p, ""), c["date"])
            if fresh:
                recent[p] += 1
    rows = [{"entity": p, "n-fixes": n, "last-fix": last[p], "recent-fixes": recent[p]} for p, n in total.items()]
    rows.sort(key=lambda r: (-r["recent-fixes"], -r["n-fixes"], r["entity"]))
    return rows


def _shares(n: int, k: int) -> list:
    """`n` lines over `k` people, the odd ones to the first: the author, whose commit it is."""
    each, rest = divmod(n, k)
    return [each + (1 if i < rest else 0) for i in range(k)]


def entity_ownership(commits: list) -> list:
    """Lines added and deleted per author per entity. A commit with co-authors shares its lines
    between everyone it credits, so the totals stay the lines the log counts."""
    added, deleted = Counter(), Counter()
    for c in commits:
        crew = people(c)
        for p, a, d in c["files"]:
            for who, x, y in zip(crew, _shares(a, len(crew)), _shares(d, len(crew))):
                added[(p, who)] += x
                deleted[(p, who)] += y
    rows = [{"entity": p, "author": who, "added": added[(p, who)], "deleted": deleted[(p, who)]} for (p, who) in added]
    rows.sort(key=lambda r: (r["entity"], r["author"]))
    return rows


def author_totals(commits: list) -> dict:
    """Per person: commits they are credited on, lines added and deleted (shared with co-authors),
    and the first and last date they committed."""
    out = {}
    for c in commits:
        crew = people(c)
        added, deleted = sum(x for _, x, _ in c["files"]), sum(x for _, _, x in c["files"])
        for who, x, y in zip(crew, _shares(added, len(crew)), _shares(deleted, len(crew))):
            a = out.setdefault(who, {"commits": 0, "added": 0, "deleted": 0, "first": c["date"], "last": c["date"]})
            a["commits"] += 1
            a["added"] += x
            a["deleted"] += y
            a["first"], a["last"] = min(a["first"], c["date"]), max(a["last"], c["date"])
    return out


def activity(commits: list, ignored: set = frozenset()) -> dict:
    """Commits by weekday (Mon=0) and hour, by month, and per-author totals, over every commit; plus
    the sweeping commits the tables leave out, each marked whether the repository declared it in
    .git-blame-ignore-revs, and how many declared commits the log holds."""
    by_weekday, by_hour, by_month, net_by_year = [0] * 7, [0] * 24, Counter(), Counter()
    timeline, fix_commits = defaultdict(Counter), 0
    revert_commits, reverted = 0, Counter()
    for c in commits:
        when = c.get("time") or c["date"]
        try:
            # git >= 2.45 writes UTC as a trailing Z, which fromisoformat rejects before Python 3.11
            stamp = dt.datetime.fromisoformat(when[:-1] + "+00:00" if when.endswith("Z") else when)
        except ValueError:
            stamp = None
        day = stamp.date() if stamp else dt.date.fromisoformat(c["date"])
        by_weekday[day.weekday()] += 1
        if stamp and len(when) > 10:
            by_hour[stamp.hour] += 1
        by_month[c["date"][:7]] += 1
        is_rev = is_revert(c.get("subject", ""))
        net = 0
        for p, a, d in c["files"]:
            net += a - d
            if is_rev:
                reverted[p] += 1
        net_by_year[c["date"][:4]] += net
        for who in people(c):
            timeline[who][c["date"][:7]] += 1
        fix_commits += is_fix(c.get("subject", ""))
        if is_rev:
            revert_commits += 1
    swept = sorted(sweeping(commits), key=lambda c: (-len(c["files"]), c["date"], c["hash"]))
    return {"by_weekday": by_weekday, "by_hour": by_hour, "by_month": dict(sorted(by_month.items())),
            "net_by_year": dict(sorted(net_by_year.items())), "authors": author_totals(commits),
            "timeline": {a: dict(sorted(m.items())) for a, m in timeline.items()}, "fix_commits": fix_commits,
            "revert_commits": revert_commits,
            "reverted": dict(sorted(reverted.items(), key=lambda kv: (-kv[1], kv[0]))),
            "sweeping": [{"hash": c["hash"], "date": c["date"], "author": c["author"], "subject": c.get("subject", ""), "files": len(c["files"]),
                          "added": sum(a for _, a, _ in c["files"]), "deleted": sum(d for _, _, d in c["files"]), "declared": c["hash"] in ignored}
                         for c in swept],
            "ignored_revs": sum(1 for c in commits if c["hash"] in ignored)}


def plumbing(commits: list, min_revs: int = 20, share: float = 0.8, max_lines: int = 3) -> list:
    """Files whose commits nearly always swap a few lines for as many: a version constant in
    __init__.py, the three fields of a version struct. Their churn is the release cadence and says
    nothing about their quality. A commit that adds lines without removing any is growth, not a
    bump. Needs enough commits to judge by."""
    revs, tiny = Counter(), Counter()
    for c in commits:
        for path, added, deleted in c["files"]:
            revs[path] += 1
            if added == deleted and added <= max_lines:
                tiny[path] += 1
    return [{"entity": e, "n-revs": n, "tiny-revs": tiny[e]} for e, n in sorted(revs.items()) if n >= min_revs and tiny[e] / n >= share]


ANALYSES = {
    "revisions": (revisions, ["entity", "n-revs"]),
    "plumbing": (plumbing, ["entity", "n-revs", "tiny-revs"]),
    "coupling": (coupling, ["entity", "coupled", "degree", "average-revs"]),
    "soc": (soc, ["entity", "soc", "partners"]),
    "authors": (authors, ["entity", "n-authors", "n-revs", "minor"]),
    "age": (age, ["entity", "age-months"]),
    "entity-ownership": (entity_ownership, ["entity", "author", "added", "deleted"]),
    "fixes": (fixes, ["entity", "n-fixes", "last-fix", "recent-fixes"]),
}
NEEDS_NOW = {"age", "fixes"}


def aliases_from_meta(path: str) -> dict:
    with open(path) as fh:
        meta = json.load(fh)
    if "aliases" in meta:
        return dict(meta["aliases"])
    out = {}
    for ident in meta.get("identities", []):
        for a in ident.get("aliases", []):
            out[a["name"]] = ident["name"]
    return out


def bots_from_meta(path: str) -> set:
    """The names the run decided are services, so a bot named in a trailer is not a co-author."""
    with open(path) as fh:
        meta = json.load(fh)
    return {b["name"] for b in meta.get("bots") or []}


def in_window(commits: list, since: str = None, until: str = None) -> list:
    """Commits authored on or after `since` and before `until` (YYYY-MM-DD); all of them when both are None."""
    return [c for c in commits if (not since or c["date"] >= since) and (not until or c["date"] < until)]


def validate_now(value: str) -> str:
    """A reference date must be exactly YYYY-MM-DD."""
    if len(value) != 10 or dt.date.fromisoformat(value).isoformat() != value:
        raise ValueError(f"reference date must be YYYY-MM-DD, got {value!r}")
    return value


def write_all(log_path: str, out_dir: str, aliases_path: str = None, types=filetypes.DEFAULT, now: str = None, since: str = None, until: str = None,
              ignore_revs: set = frozenset()) -> None:
    """`now` (YYYY-MM-DD) is the reference date for file ages; default today. `since` and `until` bound every
    analysis except file ages and activity.json's `authors_all`, which describe the whole history.
    `ignore_revs` are the SHAs the repository declares uninteresting; they and the sweeping commits stay
    out of every table but the activity totals."""
    # newline="": keep a \r inside a subject as-is instead of turning it into a line break
    with open(log_path, encoding="utf-8", errors="replace", newline="") as fh:
        commits = parse_log(fh.read(), aliases_from_meta(aliases_path) if aliases_path else None, types,
                            bots_from_meta(aliases_path) if aliases_path else None)
    ignored = {c["hash"] for c in commits if ignore_revs and is_ignored(c["hash"], ignore_revs)}
    windowed = in_window(commits, since, until)
    kept, kept_all = analysed(windowed, ignored), analysed(commits, ignored)
    for name, (fn, header) in ANALYSES.items():
        source = kept_all if name == "age" else kept   # ages describe the whole history
        rows = fn(source, now=now) if name in NEEDS_NOW else fn(source)
        with open(os.path.join(out_dir, f"maat-{name}.csv"), "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=header)
            w.writeheader()
            w.writerows(rows)
    act = activity(windowed, ignored)
    # knowledge loss is a whole-history question, so it reads authors_all, not the windowed table
    act["authors_all"] = author_totals(commits)
    act["window"] = since
    act["until"] = until
    with open(os.path.join(out_dir, "activity.json"), "w", encoding="utf-8") as fh:
        json.dump(act, fh)


if __name__ == "__main__":
    args = sys.argv[1:]
    aliases, types, now, since, until, ignore_paths = None, filetypes.DEFAULT, None, None, None, []
    while "--ignore-revs" in args:
        i = args.index("--ignore-revs"); ignore_paths.append(args[i + 1]); del args[i:i + 2]
    while "--since" in args:
        i = args.index("--since")
        try:
            since = validate_now(args[i + 1])
        except (ValueError, IndexError) as e:
            sys.exit(f"maat.py: {e}")
        del args[i:i + 2]
    while "--until" in args:
        i = args.index("--until")
        try:
            until = validate_now(args[i + 1])
        except (ValueError, IndexError) as e:
            sys.exit(f"maat.py: {e}")
        del args[i:i + 2]
    while "--now" in args:
        i = args.index("--now")
        try:
            now = validate_now(args[i + 1])
        except (ValueError, IndexError) as e:
            sys.exit(f"maat.py: {e}")
        del args[i:i + 2]
    while "--types" in args:
        i = args.index("--types"); types = filetypes.parse(args[i + 1]); del args[i:i + 2]
    if "--aliases" in args:
        i = args.index("--aliases")
        aliases = args[i + 1]
        del args[i:i + 2]
    if len(args) != 2:
        sys.exit("usage: maat.py LOG OUT_DIR [--aliases META_JSON] [--types LIST|all] [--now YYYY-MM-DD] [--since YYYY-MM-DD] [--until YYYY-MM-DD] [--ignore-revs FILE]...")
    write_all(args[0], args[1], aliases, types, now, since, until, read_ignore_revs(ignore_paths))

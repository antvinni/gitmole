#!/usr/bin/env python3
"""Change analysis over a git log export, in the layout code-maat produced: revisions, coupling and sum of
coupling after Adam Tornhill's code-maat, minor contributors after Bird et al. (FSE 2011), change entropy
after Hassan (ICSE 2009), oversized fixes after Herzig and Zeller (MSR 2013); see docs/references.md.

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


IMPORT_SHARE = 0.05     # an import adds at least this share of every line the history adds...
IMPORT_MIN_FILES = 100  # ...to at least this many files...
IMPORT_DELETED = 0.01   # ...and deletes at most this share of what it adds


def importing(commits: list, share: float = IMPORT_SHARE, min_files: int = IMPORT_MIN_FILES, deleted: float = IMPORT_DELETED) -> list:
    """The commits that bring a codebase in rather than change it: add-only, a hundred files or more,
    and a twentieth or more of every line the history ever adds (a project published with its history
    squashed into one first commit, a subsystem moved in from another repository). Whoever committed
    it did not write what it holds, so crediting them with ownership of every file it touched makes
    one person the owner of most of the tree. A large feature, however new, is a small share of a
    long history and stays in."""
    total = sum(a for c in commits for _, a, _ in c["files"])
    out = []
    for c in commits:
        if len(c["files"]) < min_files:
            continue
        a, d = sum(x for _, x, _ in c["files"]), sum(y for _, _, y in c["files"])
        if total and a >= share * total and d <= deleted * a:
            out.append(c)
    return out


def analysed(commits: list, ignored: set = frozenset()) -> list:
    """The commits every table but the activity totals reads: without the sweeps, the imports and the
    declared."""
    left_out = {c["hash"] for c in sweeping(commits)} | {c["hash"] for c in importing(commits)}
    return [c for c in commits if c["hash"] not in left_out and c["hash"] not in ignored]


def imported_files(commits: list) -> set:
    """The files an import brought in: nobody here created them."""
    return {p for c in importing(commits) for p, a, _ in c["files"] if a > 0}


def revisions(commits: list) -> list:
    return [{"entity": e, "n-revs": n} for e, n in sorted(_revs(commits).items(), key=lambda kv: (-kv[1], kv[0]))]


# A ticket-shaped key in a subject: GitHub's squash-merge suffix "(#1234)", a Jira-shaped "PROJ-42",
# or a reference such as "Fixes #77". Value shapes, not word lists: the shape is the convention.
_TICKET_SUFFIX = re.compile(r"\(#(\d+)\)\s*$")
_TICKET_JIRA = re.compile(r"^\s*[\[(]?([A-Z][A-Z0-9]+-\d+)\b")   # at the start, as trackers put it; UTF-8 mid-sentence is a word
_TICKET_REF = re.compile(r"\b(?:fixes|fixed|closes|closed|refs|resolves|resolved)\s+#?(\d+)\b", re.I)


def ticket_key(subject: str):
    """The change a commit belongs to, when its subject says: '#1234' for a squash suffix or a
    'Fixes #1234' reference, 'PROJ-42' for a Jira-shaped key opening the subject; None when nothing
    ticket-shaped is there."""
    subject = subject or ""
    m = _TICKET_SUFFIX.search(subject)
    if m:
        return f"#{m.group(1)}"
    m = _TICKET_JIRA.search(subject)
    if m:
        return m.group(1)
    m = _TICKET_REF.search(subject)
    if m:
        return f"#{m.group(1)}"
    return None


def changesets(commits: list) -> list:
    """The logical changes, code-maat's temporal period with CodeScene's ticket grouping: commits whose
    subjects share a ticket-shaped key are one changeset, wherever and whenever they landed; the rest
    group by author and calendar day, so a rebase-merged pull request is one change again. Two squash
    merges by one person on one day carry two keys and stay apart. Each changeset speaks with its first
    commit's hash, date, author and subject, carries its commit count, and sums the lines per path."""
    groups, order = {}, []
    for c in commits:
        key = ticket_key(c.get("subject", ""))
        key = ("ticket", key) if key else ("day", c["author"], c["date"])
        if key not in groups:
            groups[key] = {"hash": c["hash"], "date": c["date"], "time": c.get("time", c["date"]), "author": c["author"],
                           "subject": c.get("subject", ""), "co_authors": list(c.get("co_authors", ())), "commits": 0, "files": [], "_lines": {}}
            order.append(key)
        g = groups[key]
        g["commits"] += 1
        for p, a, d in c["files"]:
            if p not in g["_lines"]:
                g["_lines"][p] = [a, d]
            else:
                g["_lines"][p][0] += a
                g["_lines"][p][1] += d
    out = []
    for key in order:
        g = groups[key]
        g["files"] = [(p, a, d) for p, (a, d) in g["_lines"].items()]
        del g["_lines"]
        out.append(g)
    return out


def coupling(commits: list, min_shared: int = 5, min_degree: int = 30, max_changeset: int = 30) -> list:
    """Pairs that change together, over the logical changesets (see changesets()) rather than the raw
    commits, so a rebase-merged change counts once and a change spread over a ticket's commits counts
    as one. The cap on a changeset's size applies after grouping."""
    sets = changesets(commits)
    revs = _revs(sets)
    shared = Counter()
    for c in sets:
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


COMPANION_CONFIDENCE = 70   # percent of a file's changesets that also touch the companion
COMPANION_SHARED = 20       # ...over at least this many shared changesets


def companions(commits: list, min_confidence: int = COMPANION_CONFIDENCE, min_shared: int = COMPANION_SHARED, max_changeset: int = 30) -> list:
    """Directed pairs: `companion` changed in at least `min_confidence`% of the changesets that touched
    `entity`, over at least `min_shared` of them. ROSE's confidence (Zimmermann et al., ICSE 2004), not
    the symmetric degree: a small file that nearly always moves with a busy one is its companion even
    when the busy one mostly moves alone. Measured for the hook on the development set and once on the
    held-out Apache repositories (docs/validation.md)."""
    sets = changesets(commits)
    revs, shared = Counter(), Counter()
    for c in sets:
        paths = sorted({p for p, _, _ in c["files"]})
        if len(paths) > max_changeset:
            continue
        revs.update(paths)
        for a, b in itertools.combinations(paths, 2):
            shared[(a, b)] += 1
    rows = []
    for (a, b), n in shared.items():
        if n < min_shared:
            continue
        for x, y in ((a, b), (b, a)):
            confidence = int(math.floor(100 * n / revs[x] + 0.5))
            if confidence >= min_confidence:
                rows.append({"entity": x, "companion": y, "confidence": confidence, "shared": n})
    rows.sort(key=lambda r: (-r["confidence"], -r["shared"], r["entity"], r["companion"]))
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
    for c in changesets(commits):
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


def test_cochange(commits: list) -> list:
    """Per production file: how many changesets touched it, and how many of those also touched a test
    file. A hot file whose tests never move is a better-evidenced test signal than assertion density."""
    sets_by, with_tests = Counter(), Counter()
    for c in changesets(commits):
        paths = {p for p, _, _ in c["files"]}
        tested = any(filetypes.is_test_path(p) for p in paths)
        for p in paths:
            if filetypes.is_test_path(p):
                continue
            sets_by[p] += 1
            if tested:
                with_tests[p] += 1
    rows = [{"entity": p, "n-sets": n, "with-tests": with_tests[p]} for p, n in sets_by.items()]
    rows.sort(key=lambda r: (-r["n-sets"], r["entity"]))
    return rows


ENTROPY_DECAY = 0.5   # a period's weight halves for every month it lies before the reference date
BURST_GAP_HOURS = 1   # Hassan's ECC model starts a new period after this much quiet; his figure, not swept
ADAPTIVE_WINDOW = 6   # ...and sizes the system by the files touched in this many periods; his figure too
HCM1D_PHI = 10        # Hassan fitted 10 for HCM1d, weighing a period by e^(phi (T_i - now)). The form is
                      # legible in the paper; the unit of time is not, so years here are an assumption and
                      # this is the start of a sweep rather than a principled constant (docs/pipeline.md).


def _instant(c: dict):
    """A commit's datetime, or midnight on its date when the log carried no time."""
    stamp = c.get("time") or ""
    try:
        return dt.datetime.fromisoformat(stamp[:-1] + "+00:00" if stamp.endswith("Z") else stamp)
    except ValueError:
        return dt.datetime.fromisoformat(c["date"] + "T00:00:00+00:00")


def _entropy_periods(commits: list, kind: str, gap_hours: float) -> list:
    """[(stamp, Counter of file -> changes)] for the periods the entropy is summed over. "month" keys
    by calendar month, in the order the months first appear, which is what the shipped analysis has
    always done. "burst" is Hassan's ECC period: the commits in time order, broken wherever the tree
    was quiet for longer than `gap_hours`, each period stamped with its last commit's date."""
    if kind == "month":
        by_month = defaultdict(Counter)
        for c in commits:
            for p, _, _ in c["files"]:
                by_month[c["date"][:7]][p] += 1
        return list(by_month.items())
    if kind != "burst":
        raise ValueError(f"entropy: unknown period model {kind!r}")
    out, counts, last, stamp = [], Counter(), None, None
    for c in sorted(commits, key=lambda c: (_instant(c), c["hash"])):
        when = _instant(c)
        if last is not None and (when - last).total_seconds() > gap_hours * 3600:
            out.append((stamp, counts))
            counts = Counter()
        for p, _, _ in c["files"]:
            counts[p] += 1
        last, stamp = when, c["date"]
    if counts:
        out.append((stamp, counts))
    return out


def entropy(commits: list, now: str = None, decay: float = ENTROPY_DECAY, hcpf: int = 2,
            periods: str = "month", sizing: str = "period", window: int = ADAPTIVE_WINDOW,
            phi: float = None, gap_hours: float = BURST_GAP_HOURS) -> list:
    """Hassan's history complexity metric (ICSE 2009), decayed: for each calendar month, the Shannon
    entropy of the files' shares of that month's changes, normalised by log2 of the files changed;
    a file's score is the sum over months of its share times that entropy, each month weighted by
    `decay` to the power of its distance from `now`. Changes scattered over many files in a month are
    hard to keep track of; a month spent on one file is not. `periods` is how many months the file
    changed in.

    Every default is the analysis gitmole ships, so entropy.csv does not move. The rest are Hassan's
    other models, for `gitmole.evaluate` to rank by and compare — he found HCM3s and HCM1d the best
    two, and neither is what the default computes:

    - `hcpf` is how a period's entropy reaches a file: 2 is its share of the period (the default),
      3 splits the period evenly between the files it changed (HCM3s), 1 gives each of them the whole
      period's entropy (HCM1s, and the HCPF HCM1d decays).
    - `periods` is "month" or "burst" (the ECC model: a new period after `gap_hours` of quiet).
    - `sizing` is what the entropy is normalised by: "period" (the files the period changed, the
      default), "system" (every file the history has touched up to and including the period — the
      normalised static entropy Hassan's results use, with the files touched standing in for the files
      that exist, since the log has no tree), or "adaptive" (the files changed in this period and the
      `window - 1` before it: his adaptive sizing, which he describes but shows no results for).
    - `decay` of 1.0 is Hassan's simple sum, the s in HCM1s to HCM3s: nothing is forgotten.
    - `phi` replaces the halving with e^(-phi × years back), the form of HCM1d; see HCM1D_PHI on why
      its value is a sweep and not a citation.

    Hassan's two best models are HCM3s (hcpf 3, burst, system, decay 1.0) and HCM1d (hcpf 1, burst,
    system, phi). The default is neither.
    """
    now = now or dt.date.today().isoformat()
    buckets = _entropy_periods(commits, periods, gap_hours)
    if phi is not None and phi <= 0:
        raise ValueError(f"entropy: phi must be positive, not {phi!r}")
    sizes = None
    if sizing in ("adaptive", "system"):
        ordered = sorted(range(len(buckets)), key=lambda i: buckets[i][0])
        sizes, touched = {}, set()
        for slot, i in enumerate(ordered):
            if sizing == "system":
                touched.update(buckets[i][1])
                sizes[i] = len(touched)
            else:
                recent = ordered[max(0, slot - window + 1):slot + 1]
                sizes[i] = len({p for j in recent for p in buckets[j][1]})
    elif sizing != "period":
        raise ValueError(f"entropy: unknown sizing {sizing!r}")
    y0, m0 = int(now[:4]), int(now[5:7])
    scores, seen_in = defaultdict(float), Counter()
    for i, (stamp, counts) in enumerate(buckets):
        total, n = sum(counts.values()), len(counts)
        size = n if sizes is None else max(sizes[i], n)
        h = -sum((v / total) * math.log2(v / total) for v in counts.values()) / math.log2(size) if size > 1 and n > 1 else 0.0
        back = max(0, (y0 - int(stamp[:4])) * 12 + (m0 - int(stamp[5:7])))
        weight = math.exp(-phi * back / 12) if phi is not None else decay ** back
        for p, v in counts.items():
            seen_in[p] += 1
            share = 1.0 if hcpf == 1 else (1.0 / n if hcpf == 3 else v / total)
            scores[p] += share * h * weight
    rows = [{"entity": p, "periods": seen_in[p], "hcm": round(scores[p], 6)} for p in seen_in]
    rows.sort(key=lambda r: (-r["hcm"], -r["periods"], r["entity"]))
    return rows


DOA_DECAY_MONTHS = 5   # JetBrains' Bus Factor Explorer: knowledge halves every five months
DOA_AUTHOR_SHARE = 0.75
DOA_FLOOR = 3.293


def _doa(fa: int, dl: float, ac: float) -> float:
    """Avelino et al.'s degree of authorship: a creator's bonus, the author's own changes, and a
    logarithmic dilution by everyone else's."""
    return 3.293 + 1.098 * fa + 0.164 * dl - 0.321 * math.log(1 + ac)


def doa(commits: list, now: str = None, imported=frozenset()) -> list:
    """Per file and person: created it (the first commit that added lines to it; a pure move creates
    nothing), their changes, others' changes, the degree of authorship, and whether they count as an
    author of it (DOA at least three quarters of the file's highest and at least 3.293), undecayed and
    with knowledge halving every five months. Changes, not lines, so a reformat transfers nothing. A file
    in `imported` came in with an import commit, which is left out; nobody gets the bonus for creating
    it, rather than whoever changed it first afterwards."""
    now = dt.date.fromisoformat(now or dt.date.today().isoformat())
    changes, decayed, first = defaultdict(Counter), defaultdict(Counter), {}
    for c in commits:
        weight = 0.5 ** (max(0, (now - dt.date.fromisoformat(c["date"])).days) / 30.44 / DOA_DECAY_MONTHS)
        for p, added, _ in c["files"]:
            for who in people(c):
                changes[p][who] += 1
                decayed[p][who] += weight
            if added > 0 and (p not in first or (c["date"], c.get("time", "")) < first[p][0]):
                first[p] = ((c["date"], c.get("time", "")), c["author"])
    rows = []
    for p, per in changes.items():
        total, total_d = sum(per.values()), sum(decayed[p].values())
        creator = None if p in imported else first.get(p, (None, None))[1]
        scores = {}
        for who, n in per.items():
            fa = int(who == creator)
            scores[who] = (fa, n, total - n, _doa(fa, n, total - n), _doa(fa, decayed[p][who], total_d - decayed[p][who]))
        top, top_d = max(s[3] for s in scores.values()), max(s[4] for s in scores.values())
        for who, (fa, n, others, value, value_d) in sorted(scores.items()):
            rows.append({"entity": p, "author": who, "fa": fa, "dl": n, "ac": others, "doa": round(value, 4), "doa_decayed": round(value_d, 4),
                         "is_author": int(value >= DOA_FLOOR and value >= DOA_AUTHOR_SHARE * top),
                         "is_author_decayed": int(value_d >= DOA_FLOOR and value_d >= DOA_AUTHOR_SHARE * top_d)})
    rows.sort(key=lambda r: (r["entity"], r["author"]))
    return rows


def _local_hour(stamp: str):
    try:
        return dt.datetime.fromisoformat(stamp[:-1] + "+00:00" if stamp.endswith("Z") else stamp).hour if len(stamp) > 10 else None
    except ValueError:
        return None


LATE_HOURS = range(0, 4)   # Eyolfson, Tan and Lam: commits between midnight and 4 am, in the author's own time, were buggier


def latenight(commits: list) -> list:
    """Per file: its revisions, and how many were committed between midnight and 4 am in the author's
    own offset. A reason beside a file, never a rank: the effect is far weaker than churn or ownership."""
    revs, late = Counter(), Counter()
    for c in commits:
        hour = _local_hour(c.get("time") or "")
        for p, _, _ in c["files"]:
            revs[p] += 1
            late[p] += hour is not None and hour in LATE_HOURS
    rows = [{"entity": p, "n-revs": n, "late": late[p]} for p, n in revs.items()]
    rows.sort(key=lambda r: (-r["late"], r["entity"]))
    return rows


def component(path: str, depth: int) -> str:
    dirs = path.split("/")[:-1]
    return "/".join(dirs[:depth]) + "/" if dirs else "(root files)"


def components(commits: list, min_shared: int = 10, min_degree: int = 20, max_components: int = 10) -> list:
    """Coupling between components, the files truncated to their first one and two directories, over
    the logical changes: two files in one directory changing together is a layout, `auth/` and
    `billing/` changing together 40% of the time is architecture. A change that spans more than
    `max_components` components is a sweep and couples nothing."""
    out = []
    for depth in (1, 2):
        revs, shared = Counter(), Counter()
        for c in changesets(commits):
            comps = sorted({component(p, depth) for p, _, _ in c["files"]} - {"(root files)"})
            if not comps or len(comps) > max_components:
                continue
            revs.update(comps)
            for a, b in itertools.combinations(comps, 2):
                if not (b.startswith(a) or a.startswith(b)):   # gradle/ holding a file and gradle/root/ are one component and its part
                    shared[(a, b)] += 1
        for (a, b), n in shared.items():
            avg = (revs[a] + revs[b]) / 2
            degree = int(math.floor(100 * n / avg + 0.5))
            if n >= min_shared and degree >= min_degree:
                out.append({"depth": depth, "entity": a, "coupled": b, "degree": degree, "shared": n, "average-revs": int(math.floor(avg + 0.5))})
    out.sort(key=lambda r: (r["depth"], -r["degree"], -r["shared"], r["entity"], r["coupled"]))
    return out


RECENT_MONTHS = 6
OVERSIZED_PERCENTILE = 0.99   # a fix changing more lines than this share of the history's commits credits nothing
OVERSIZED_FLOOR = 500         # ...and never under this many lines, so a small repository's percentile does not bite


def _lines(c: dict) -> int:
    return sum(a + d for _, a, d in c["files"])


def oversized(commits: list, percentile: float = OVERSIZED_PERCENTILE, floor: int = OVERSIZED_FLOOR) -> list:
    """The commits above the repository's own 99th percentile of lines changed (never under `floor`).
    Commit sizes are heavy-tailed, so the percentile is the repository's; Herzig and Zeller showed a
    tangled fix mislabels most of the files it touches, and a fix this size is tangled by size."""
    sizes = sorted(_lines(c) for c in commits if c["files"])
    if not sizes:
        return []
    cut = max(floor, sizes[min(len(sizes) - 1, int(math.ceil(percentile * len(sizes))) - 1)])
    return [c for c in commits if c["files"] and _lines(c) >= cut]


def fix_commits(commits: list) -> list:
    """The fix pool: commits whose subject says fix, less the oversized ones."""
    big = {c["hash"] for c in oversized(commits)}
    return [c for c in commits if is_fix(c.get("subject", "")) and c["hash"] not in big]


def fixes(commits: list, now: str = None) -> list:
    """Per entity: how many fix commits touched it, the last one, and how many in the recent window.
    An oversized fix (see oversized()) credits none of its files."""
    now = now or dt.date.today().isoformat()
    total, last, recent = Counter(), {}, Counter()
    for c in fix_commits(commits):
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


TANGLED_FILES = 10   # a commit this wide, across this many directories, under a subject with this many clauses,
TANGLED_DIRS = 4     # looks like several changes in one; Herzig and Zeller (MSR 2013) found such commits
TANGLED_CLAUSES = 2  # mislabel a large share of the files they touch
_BRACKETED = re.compile(r"\([^()]*\)|\[[^\[\]]*\]|`[^`]*`")
_CLAUSE_BREAK = re.compile(r"\s*(?:;|,|&|\+|\band\b)\s*", re.I)


_STRONG_BREAK = re.compile(r"\s*(?:;|,|&|\+)\s*")
_AND = re.compile(r"\s+and\s+", re.I)


def clauses(subject: str) -> int:
    """How many things a subject says it does: its parts between semicolons, commas, ampersands and
    pluses, with anything in brackets or backticks passed over (a call's arguments are not clauses); a
    part after a plain 'and' counts only when it is two words or more, since "on macOS and Linux" joins
    two nouns, not two changes."""
    count = 0
    for part in _STRONG_BREAK.split(_BRACKETED.sub("", subject or "")):
        pieces = [x for x in _AND.split(part) if x.strip()]
        if pieces:
            count += 1 + sum(1 for x in pieces[1:] if len(x.split()) >= 2)
    return count


def is_tangled(c: dict) -> bool:
    """Many files across many directories under a subject that lists several things: several changes
    in one commit, whose fix label, if any, credits files the fix never touched."""
    if len(c["files"]) < TANGLED_FILES:
        return False
    dirs = {os.path.dirname(p) for p, _, _ in c["files"]}
    return len(dirs) >= TANGLED_DIRS and clauses(c.get("subject", "")) >= TANGLED_CLAUSES


def activity(commits: list, ignored: set = frozenset()) -> dict:
    """Commits by weekday (Mon=0) and hour, by month, and per-author totals, over every commit; plus
    the sweeping commits the tables leave out, each marked whether the repository declared it in
    .git-blame-ignore-revs, how many declared commits the log holds, the oversized fixes the fix pool
    leaves out, the tangled-looking commits, and how many subjects end in a squash-merge suffix."""
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
    brought_in = sorted(importing(commits), key=lambda c: (c["date"], c["hash"]))
    big = {c["hash"] for c in oversized(commits)}
    tangled = sorted((c for c in commits if is_tangled(c)), key=lambda c: (-len(c["files"]), c["date"], c["hash"]))
    return {"by_weekday": by_weekday, "by_hour": by_hour, "by_month": dict(sorted(by_month.items())),
            "net_by_year": dict(sorted(net_by_year.items())), "authors": author_totals(commits),
            "timeline": {a: dict(sorted(m.items())) for a, m in timeline.items()}, "fix_commits": fix_commits,
            "revert_commits": revert_commits,
            "reverted": dict(sorted(reverted.items(), key=lambda kv: (-kv[1], kv[0]))),
            "sweeping": [{"hash": c["hash"], "date": c["date"], "author": c["author"], "subject": c.get("subject", ""), "files": len(c["files"]),
                          "added": sum(a for _, a, _ in c["files"]), "deleted": sum(d for _, _, d in c["files"]), "declared": c["hash"] in ignored}
                         for c in swept],
            "imports": [{"hash": c["hash"], "date": c["date"], "author": c["author"], "subject": c.get("subject", ""), "files": len(c["files"]),
                         "added": sum(a for _, a, _ in c["files"]), "deleted": sum(d for _, _, d in c["files"])} for c in brought_in],
            "added_total": sum(a for c in commits for _, a, _ in c["files"]),
            "ignored_revs": sum(1 for c in commits if c["hash"] in ignored),
            "oversized_fixes": sum(1 for c in commits if c["hash"] in big and is_fix(c.get("subject", ""))),
            "tangled_commits": len(tangled),
            "tangled": [{"hash": c["hash"], "date": c["date"], "files": len(c["files"]), "dirs": len({os.path.dirname(p) for p, _, _ in c["files"]}),
                         "subject": c.get("subject", "")} for c in tangled[:10]],
            "squash_subjects": sum(1 for c in commits if _TICKET_SUFFIX.search(c.get("subject", "")))}


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
    "companions": (companions, ["entity", "companion", "confidence", "shared"]),
    "soc": (soc, ["entity", "soc", "partners"]),
    "tests": (test_cochange, ["entity", "n-sets", "with-tests"]),
    "authors": (authors, ["entity", "n-authors", "n-revs", "minor"]),
    "age": (age, ["entity", "age-months"]),
    "entity-ownership": (entity_ownership, ["entity", "author", "added", "deleted"]),
    "fixes": (fixes, ["entity", "n-fixes", "last-fix", "recent-fixes"]),
    "entropy": (entropy, ["entity", "periods", "hcm"]),
    "doa": (doa, ["entity", "author", "fa", "dl", "ac", "doa", "doa_decayed", "is_author", "is_author_decayed"]),
    "latenight": (latenight, ["entity", "n-revs", "late"]),
    "components": (components, ["depth", "entity", "coupled", "degree", "shared", "average-revs"]),
}
NEEDS_NOW = {"age", "fixes", "entropy", "doa"}


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
        if name == "doa":   # the files an import created have no creator here
            rows = fn(source, now=now, imported=imported_files(commits))
        else:
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

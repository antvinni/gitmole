"""Parsers for the files the tools write. Each takes text and returns plain data."""
from __future__ import annotations

import csv
import math
import io
import sys
import json
import os
import re
from collections import Counter, OrderedDict

from . import filetypes, identity, leaks, maat, scope as scopes, textfmt


def _rel(path: str) -> str:
    """Tools started in the repo print './x'; the log and blame say 'x'."""
    return path[2:] if path.startswith("./") else path


def _only(rows: list, types, scope=()) -> list:
    """scc's language rows with the files outside `types` (None: none) or outside --path's directories
    dropped and the totals rebuilt from what is left. A row without per-file data (an older size.json)
    is kept as it is."""
    out = []
    for r in rows:
        files = r.get("Files")
        if files is None:
            out.append(r)
            continue
        kept = [f for f in files if (types is None or filetypes.matches(_rel(f.get("Location", "")), types))
                and scopes.within(_rel(f.get("Location", "")), scope)]
        if kept:
            out.append({**r, "Count": len(kept), "Files": kept,
                        **{k: sum(f.get(k, 0) for f in kept) for k in ("Code", "Comment", "Blank", "Complexity")}})
    return out


class Unreadable(ValueError):
    """meta.json is missing its end or is not JSON: nothing else in the directory can be trusted."""


def _json_or(text: str, default):
    """The parsed document, or `default` for no text or for text a killed step left truncated."""
    if not text.strip():
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return default


def parse_scc(text: str, types=None, scope=()) -> dict:
    """scc --by-file JSON as languages and per-file rows. `types` (as filetypes.parse gives it: a
    set, or None for everything) keeps only the code files, so the size matches the other tables;
    `scope` (a run's --path directories) keeps only the files under them. scc itself always measures the
    whole tree: the backtest's tree at its cut-off is narrowed here too, from the scope its meta records."""
    rows = _json_or(text, [])
    if not isinstance(rows, list):
        rows = []
    if types is not None or scope:
        rows = _only(rows, types, scope)
    languages = sorted(
        (
            {
                "name": r["Name"],
                "files": r["Count"],
                "code": r["Code"],
                "comment": r["Comment"],
                "blank": r["Blank"],
                "complexity": r["Complexity"],
            }
            for r in rows
        ),
        key=lambda r: -r["code"],
    )
    files = {}
    for r in rows:
        for f in r.get("Files", []) or []:
            files[_rel(f.get("Location", ""))] = {"code": f.get("Code", 0), "complexity": f.get("Complexity", 0)}
    return {
        "languages": languages,
        "total_code": sum(r["code"] for r in languages),
        "total_files": sum(r["files"] for r in languages),
        "files": files,
    }


NUMERIC_COLUMNS = {"n-revs", "degree", "average-revs", "n-authors", "age-months", "added", "deleted", "n-fixes", "recent-fixes", "tiny-revs",
                   "minor", "soc", "partners", "n-sets", "with-tests", "periods", "fa", "dl", "ac", "is_author", "is_author_decayed", "late",
                   "depth", "shared", "confidence", "commits"}
FLOAT_COLUMNS = {"doa", "doa_decayed", "dl_decayed", "ac_decayed", "hcm"}


def parse_maat_csv(text: str) -> list:
    """Rows as dicts. Only known numeric columns become ints; a file or author named 2024 stays a string."""
    if not text.strip():
        return []
    out = []
    for row in csv.DictReader(io.StringIO(text)):
        out.append({k: (_num(v) if k in NUMERIC_COLUMNS else _float(v) if k in FLOAT_COLUMNS else v) for k, v in row.items()})
    return out


def _float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _num(v):
    """An int for a numeric cell; 0 for a missing, empty or garbage one (a row cut short by a killed step)."""
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def parse_theseus(text: str) -> dict:
    d = _json_or(text, {})
    if not isinstance(d, dict) or not d.get("labels"):
        return OrderedDict()
    return OrderedDict((label, d["y"][i][-1]) for i, label in enumerate(d["labels"]))


def parse_authors_log(text: str) -> list:
    counts = Counter()
    for line in text.splitlines():
        if "\t" not in line:
            continue
        name, email = line.split("\t", 1)
        counts[(name, email)] += 1
    return [
        {"name": n, "email": e, "commits": c}
        for (n, e), c in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]


NAME_CAP = 200   # a function name a table can show; deeply nested fixtures give lizard dotted names of megabytes
csv.field_size_limit(min(sys.maxsize, 2**31 - 1))   # an older functions.csv may still carry such a name


def parse_functions(text: str) -> list:
    """lizard --csv rows: nloc, ccn, tokens, params, length, location, file, function, long name, start, end;
    then, from gitmole's own step, a label for a nameless function (its start line) and why the span
    looks mis-parsed. A nameless function goes by its label, or "(anonymous)" in an older file, and
    stays marked anonymous so the report can say where it is. A row lizard wrote twice (its Perl reader
    emits a file's `*global*` more than once) is one function."""
    rows, seen = [], set()
    for r in csv.reader(io.StringIO(text)):
        if len(r) < 11 or tuple(r[:11]) in seen:
            continue
        seen.add(tuple(r[:11]))
        name, label, suspect = r[7], r[11] if len(r) > 11 else "", r[12] if len(r) > 12 else ""
        anonymous = name in ("", "(anonymous)")
        rows.append({"file": _rel(r[6]), "function": textfmt.cut(label if anonymous and label else name, NAME_CAP) or "(anonymous)", "anonymous": anonymous,
                     "ccn": _num(r[1]), "nloc": _num(r[0]), "params": _num(r[3]), "start": _num(r[9]), "end": _num(r[10]), "suspect": suspect})
    rows.sort(key=lambda f: (f["file"], f["start"], f["end"], f["function"]))   # the function step works in parallel; the order is this one
    return rows


def parse_secrets(text: str) -> list:
    """betterleaks rows as rule, file, short commit, line, fingerprint, the hashed value and the placeholder
    flag, and where the repository declared the value allowed when it did. A report written before values were hashed still has them: hash them here, keep nothing raw."""
    rows = _json_or(text, [])
    if not isinstance(rows, list):
        rows = []
    key = leaks.new_key()   # for an older report with raw values: one key per read, as the wrapper does per run
    out = []
    for r in rows:
        if "SecretHash" in r:
            value, placeholder = r["SecretHash"], bool(r.get("Placeholder"))
        elif r.get("Secret"):
            value, placeholder = leaks.digest(r["Secret"], key), leaks.is_placeholder(r["Secret"])
        else:
            value, placeholder = None, False
        out.append({"rule": r.get("RuleID", ""), "file": r.get("File", ""), "commit": r.get("Commit", "")[:7], "line": r.get("StartLine"),
                    "fingerprint": r.get("Fingerprint", ""), "value": value, "placeholder": placeholder, "confidence": r.get("Confidence")})
        if r.get("Date"):   # the commit's date: which sighting of a value came first (sarif places a removed value there)
            out[-1]["date"] = str(r["Date"])
        if isinstance(r.get("AtHead"), bool):   # whether HEAD's version of the file still holds the value (leaks.annotate)
            out[-1]["at_head"] = r["AtHead"]
            if r["AtHead"] and r.get("HeadLine"):
                out[-1]["head_line"] = r["HeadLine"]
        if isinstance(r.get("Local"), bool):   # a credential URI's password: to loopback or a compose service, or not (leaks.mark_local)
            out[-1]["local"] = r["Local"]
        declared = r.get("Declared")
        if isinstance(declared, dict) and declared.get("File"):   # the repository declared the value allowed (leaks.annotate)
            out[-1]["declared"] = {"file": declared["File"], "commit": str(declared.get("Commit") or "")[:7], "how": declared.get("How", "")}
    # betterleaks scans in parallel and does not promise an order; everything downstream reads the rows in this one
    out.sort(key=lambda r: (r["file"], r["commit"], r["line"] or 0, r["rule"], r["fingerprint"]))
    return out


def parse_dependencies(data) -> dict:
    """dependencies.json as the osv-scanner step writes it, with a status: scanned (sources, packages,
    vulnerable rows, database_date), no-sources, no-database, or not-run when there is no file."""
    if not isinstance(data, dict) or not data.get("status"):
        return {"status": "not-run"}
    out = {"status": data["status"]}
    if data["status"] == "scanned":
        out.update({"sources": data.get("sources") or [], "packages": _num(data.get("packages")),
                    "vulnerable": data.get("vulnerable") or [], "database_date": data.get("database_date")})
        if data.get("database_digest"):
            out["database_digest"] = data["database_digest"]
    elif data["status"] == "no-database":
        out["download"] = data.get("download") or ""
    return out


_RENAME_LINE = re.compile(r"^[-\d]+\t[-\d]+\t(.* => .*)$", re.M)


def _renamed_from(path: str) -> str:
    """The old path of a rename as `git log -M --numstat` spells it (maat._renamed_to gives the new one)."""
    if "{" in path:
        return maat._BRACED_RENAME.sub(lambda m: m.group(1), path).replace("//", "/").lstrip("/")
    return path.split(" => ", 1)[0]


def parse_fix_history(text: str, fixes: list, meta: dict, activity: dict, now: str) -> dict:
    """{entity: {"first": DATE, "recent": [HASH, ...] or None}} for the maat-fixes rows with a recent fix,
    read back from log.txt, so an analysis directory from before this was needed still reads.

    `recent` is the fix commits behind the row's recent-fixes count, newest first, from maat's own fix
    pool rebuilt the way the change analysis built it (the window, less the sweeps and imports
    activity.json lists, less the oversized fixes). A pool that does not give back the recorded counts
    (a revision the repository declared uninteresting, a log that changed) is None: a guess would name
    the wrong commits. `first` is the day the file first appears, its renames followed back."""
    rows = {r["entity"]: r for r in fixes if (r.get("recent-fixes") or 0) > 0}
    if not rows:
        return {}
    activity = activity or {}
    commits = maat.parse_log(text, None, filetypes.parse(meta.get("file_types")))
    left_out = {c.get("hash") for key in ("sweeping", "imports") for c in activity.get(key) or []}
    kept = [c for c in maat.in_window(commits, activity.get("window"), activity.get("until")) if c["hash"] not in left_out]
    total, recent = {e: 0 for e in rows}, {e: [] for e in rows}
    for c in maat.fix_commits(kept):
        fresh = maat._months_between(c["date"], now) < maat.RECENT_MONTHS
        for path, _, _ in c["files"]:
            if path in total:
                total[path] += 1
                if fresh:
                    recent[path].append((c["date"], c["hash"]))
    older = {}   # a rename's new path -> its old paths, to follow a file back past a move
    for m in _RENAME_LINE.finditer(text):
        raw = filetypes.unquote(m.group(1))
        new, old = maat._renamed_to(raw), _renamed_from(raw)
        if old != new:
            older.setdefault(new, set()).add(old)
    lineage = {}
    for e in rows:
        seen, todo = set(), [e]
        while todo:
            path = todo.pop()
            if path not in seen:
                seen.add(path)
                todo.extend(older.get(path, ()))
        for path in seen:
            lineage.setdefault(path, set()).add(e)
    first = {}
    for c in commits:
        for path, _, _ in c["files"]:
            for e in lineage.get(path, ()):
                if c["date"] < first.get(e, "9999"):
                    first[e] = c["date"]
    out = {}
    for e, r in rows.items():
        exact = total[e] == r.get("n-fixes") and len(recent[e]) == r["recent-fixes"]
        out[e] = {"first": first.get(e), "recent": [h for _, h in sorted(recent[e], key=lambda x: x[0], reverse=True)] if exact else None}
    return out


def _fix_history(out_dir: str, fixes: list, meta: dict, activity: dict) -> dict:
    """parse_fix_history over the directory's log.txt; {} when there is none (the backtest's sub-report).
    The reference date is the one the change analysis ran with: the run's recorded one, else today."""
    if not any((r.get("recent-fixes") or 0) > 0 for r in fixes):
        return {}
    path = os.path.join(out_dir, "log.txt")
    if not os.path.isfile(path):
        return {}
    import datetime as dt
    with open(path, encoding="utf-8", errors="replace", newline="") as fh:
        return parse_fix_history(fh.read(), fixes, meta, activity, meta.get("now") or dt.date.today().isoformat())


def _read(out_dir: str, name: str) -> str:
    path = os.path.join(out_dir, name)
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def parse_tree(out_dir: str, meta: dict):
    """The paths at HEAD from tree.txt (git ls-tree -r -z --name-only), or None when the run has none to
    judge by: an output directory from before the step, or a step that did not finish."""
    path = os.path.join(out_dir, "tree.txt")
    if not os.path.exists(path) or ((meta.get("steps") or {}).get("tree") or "run") != "run":
        return None
    with open(path, "rb") as fh:
        paths = frozenset(p.decode("utf-8", "replace") for p in fh.read().split(b"\0") if p)
    return paths or None


def _read_json(out_dir: str, name: str, default):
    """`default` for a missing file or one a killed step left truncated or malformed."""
    return _json_or(_read(out_dir, name), default)


def _nested(out_dir: str):
    """The backtest sub-report, or None when there is none or its meta.json cannot be read."""
    sub = os.path.join(out_dir, "backtest")
    if not os.path.isfile(os.path.join(sub, "meta.json")):
        return None
    try:
        return load_report(sub, nested=False)
    except Unreadable:
        return None


def _authored(meta: dict, activity: dict, provenance: dict) -> None:
    """Fill in `authored` where an older run left it out, so the People table and the Timeline
    do not call a Co-authored-by credit a commit. What such a run kept is the trailer inventory: the
    identities that are named in trailers and never author a commit (provenance never_author), whose
    every credit is a trailer's. An identity row loses the commits of those variants; a per-person total
    loses those credits, never below zero. A person who both authors and is credited under one address
    keeps the credit, which only the newer run can tell apart."""
    never = (provenance.get("trailers") or {}).get("never_author") or []
    if not never:
        return
    emails = {(t.get("email") or "").lower() for t in never}
    for i in meta.get("identities") or []:
        if "authored" not in i:
            others = i.get("aliases") or []
            head = {"email": i.get("email"), "commits": i["commits"] - sum(a["commits"] for a in others)}   # the row's commits are its variants' sum
            credit = sum(v["commits"] for v in [head, *others] if (v.get("email") or "").lower() in emails)
            i["authored"] = max(0, i["commits"] - credit)
    aliases = meta.get("aliases") or {}
    credited = {}
    for t in never:
        name = aliases.get(t.get("name"), t.get("name"))
        credited[name] = credited.get(name, 0) + (t.get("commits") or 0)
    for key in ("authors", "authors_all"):
        for name, a in (activity.get(key) or {}).items():
            if "authored" not in a and name in credited:
                a["authored"] = max(0, (a.get("commits") or 0) - credited[name])


DECAYED = ("dl_decayed", "ac_decayed")   # maat-doa.csv's decayed changes, written from 0.40; read here and not exported


def _solve(target: float, total: float) -> float:
    """The decayed changes w in [0, total] at which 0.164 w - 0.321 ln(1 + total - w) is `target`: the part
    of maat._doa that is not the creator's bonus. It rises with w, so bisection finds it."""
    def f(w):
        return 0.164 * w - 0.321 * math.log(1 + total - w) - target
    if f(0.0) >= 0:
        return 0.0
    if f(total) <= 0:
        return total
    lo, hi = 0.0, total
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if f(mid) < 0 else (lo, mid)
    return (lo + hi) / 2


def _decayed(rows: list) -> dict:
    """{author: (their decayed changes, everyone else's)} for one file. From the csv's own columns when the
    run wrote them. An older run kept only the decayed scores: each score fixes its row's changes once the
    file's total T is known, and T is where those add up to T, found on a grid up to the undecayed total
    (no weight is over 1) and narrowed by bisection, or the grid point closest to it. The scores are
    rounded, so a person at the degree-of-authorship floor can land either side of it (yt-dlp's
    0.39.0 run: the same decayed truck factor as a recount from the log, 461 of 14,432 author flags
    otherwise)."""
    if all(k in r for r in rows for k in DECAYED):
        return {r["author"]: (r["dl_decayed"], r["ac_decayed"]) for r in rows}
    targets = [r.get("doa_decayed", 0.0) - 3.293 - 1.098 * (r.get("fa") or 0) for r in rows]

    def excess(total):
        return sum(_solve(t, total) for t in targets) - total
    top = float(sum(r.get("dl") or 0 for r in rows))
    steps = 256
    grid = [top * k / steps for k in range(1, steps + 1)]
    values = [excess(t) for t in grid]
    total = None
    for k in range(1, steps):
        if (values[k] >= 0) != (values[k - 1] >= 0):
            lo, hi, rising = grid[k - 1], grid[k], values[k] >= 0
            for _ in range(60):
                mid = (lo + hi) / 2
                if (excess(mid) >= 0) == rising:
                    hi = mid
                else:
                    lo = mid
            total = (lo + hi) / 2
    if total is None:
        total = grid[min(range(steps), key=lambda k: abs(values[k]))] if grid else 0.0
    return {r["author"]: (w, total - w) for r, w in zip(rows, (_solve(t, total) for t in targets))}


def _doa_without(rows: list, tools: set) -> list:
    """maat-doa.csv's rows as the degree of authorship reads with the tools taken out of every file: a
    person's score counts the other people's changes only, and who is an author is decided among the
    people. Recomputed from the csv's changes, undecayed and decayed (_decayed)."""
    by_file = {}
    for r in rows:
        by_file.setdefault(r["entity"], []).append(r)
    out = []
    for entity, rs in by_file.items():
        people = [r for r in rs if r["author"] not in tools]
        if len(people) == len(rs):
            out.extend(rs)
            continue
        if not people:
            continue
        theirs = sum(r.get("dl") or 0 for r in rs if r["author"] in tools)
        decayed = _decayed(rs)
        theirs_d = sum(decayed[r["author"]][0] for r in rs if r["author"] in tools)
        changed, scores = [], []
        for r in people:
            fa, (dl_d, ac_d) = r.get("fa") or 0, decayed[r["author"]]
            ac = max(0, (r.get("ac") or 0) - theirs)
            value, value_d = maat._doa(fa, r.get("dl") or 0, ac), maat._doa(fa, dl_d, max(0.0, ac_d - theirs_d))
            row = {**r, "ac": ac, "doa": round(value, 4), "doa_decayed": round(value_d, 4)}
            if all(k in r for k in DECAYED):
                row["ac_decayed"] = round(max(0.0, ac_d - theirs_d), 6)
            changed.append(row)
            scores.append((value, value_d))
        top, top_d = max(v for v, _ in scores), max(v for _, v in scores)
        for r, (value, value_d) in zip(changed, scores):   # judged unrounded, as maat.doa judges them
            r["is_author"] = int(value >= maat.DOA_FLOOR and value >= maat.DOA_AUTHOR_SHARE * top)
            r["is_author_decayed"] = int(value_d >= maat.DOA_FLOOR and value_d >= maat.DOA_AUTHOR_SHARE * top_d)
        out.extend(changed)
    return out


def _authors_without(rows: list, tool_rows: list) -> list:
    """maat-authors.csv's rows without the tools: each file's author count less the tools that touched it,
    and its minor contributors less the tools among them (under maat.MINOR_SHARE of the file's commits,
    from the ownership table's commits column; an export without that column keeps its minor count)."""
    revs = {r["entity"]: r.get("n-revs") or 0 for r in rows}
    count, minor = Counter(), Counter()
    for r in tool_rows:
        count[r["entity"]] += 1
        if "commits" in r and revs.get(r["entity"]) and (r.get("commits") or 0) / revs[r["entity"]] < maat.MINOR_SHARE:
            minor[r["entity"]] += 1
    return [{**r, "n-authors": max(0, r["n-authors"] - count[r["entity"]]), **({"minor": max(0, r["minor"] - minor[r["entity"]])} if "minor" in r else {})}
            if count[r["entity"]] else r for r in rows]


def _tools_apart(meta: dict, ownership: list, authors: list, doa: list, surviving: dict) -> tuple:
    """The tables with the coding tools taken out (identity.tools: several names on one bare no-reply
    address), and what the tools were credited with, kept apart: ownership, owners and authors, minor contributors, the degree of authorship the truck factor
    reads, and the surviving code are about people. A tool that shares a commit knows none of it when
    the person leaves. Returns (ownership, authors, doa, surviving, tools), `tools` {} when there are none."""
    names = identity.tools(meta.get("identities") or [])
    if not names:
        return ownership, authors, doa, surviving, {}
    theirs = [r for r in ownership if r.get("author") in names]
    added = Counter()
    for r in theirs:
        added[r["entity"]] += r.get("added") or 0
    ids = [i for i in meta.get("identities") or [] if i.get("name") in names]
    tools = {"names": sorted(names), "commits": sum(i.get("commits") or 0 for i in ids),
             "added": dict(sorted((e, n) for e, n in added.items() if n)),
             "surviving": sum(n for name, n in surviving.items() if name in names)}
    return ([r for r in ownership if r.get("author") not in names], _authors_without(authors, theirs), _doa_without(doa, names),
            OrderedDict((k, v) for k, v in surviving.items() if k not in names), tools)


def load_report(out_dir: str, nested: bool = True) -> dict:
    """Read every output file gitmole writes. Missing optional files become empty values.

    `nested`: also load the backtest sub-report (out_dir/backtest), one level deep only."""
    meta = _read_json(out_dir, "meta.json", None) if os.path.exists(os.path.join(out_dir, "meta.json")) else {}
    if not isinstance(meta, dict):
        raise Unreadable(f"{os.path.join(out_dir, 'meta.json')} is truncated or not JSON; run gitmole again")
    cohorts = _read(out_dir, "theseus/cohorts.json")
    authors = _read(out_dir, "theseus/authors.json")
    canonical = dict(meta["aliases"]) if "aliases" in meta else identity.canonical_names(meta.get("identities") or [])
    bots = {b["name"] for b in meta.get("bots") or []}   # the run decided from name, email and aliases; the tables only have the name

    def is_bot(name):
        return name in bots or identity.is_bot(name)
    surviving = OrderedDict()
    for name, lines in (parse_theseus(authors) if authors else {}).items():
        key = canonical.get(name, name)
        if is_bot(key):   # a deploy job that committed a built site owns nothing anyone needs to know
            continue
        surviving[key] = surviving.get(key, 0) + lines
    ownership = [r for r in parse_maat_csv(_read(out_dir, "maat-entity-ownership.csv")) if not is_bot(r.get("author") or "")]
    fixes = parse_maat_csv(_read(out_dir, "maat-fixes.csv"))
    activity = _read_json(out_dir, "activity.json", {})
    provenance = _read_json(out_dir, "provenance.json", {}) or {}
    _authored(meta, activity if isinstance(activity, dict) else {}, provenance if isinstance(provenance, dict) else {})
    ownership, authors_rows, doa, surviving, tools = _tools_apart(meta, ownership, parse_maat_csv(_read(out_dir, "maat-authors.csv")),
                                                                  parse_maat_csv(_read(out_dir, "maat-doa.csv")), surviving)
    doa = [{k: v for k, v in r.items() if k not in DECAYED} for r in doa]   # read for the recount above; the tables never showed them
    return {
        "out_dir": out_dir,
        "meta": meta,
        "tree": parse_tree(out_dir, meta),   # every path at HEAD, binaries too; None before 0.39
        # a run records its --file-types spec (None for the default list); a run from before that record
        # was measured unfiltered, so it is re-rendered unfiltered rather than with a guessed list
        "size": parse_scc(_read(out_dir, "size.json"), filetypes.parse(meta["file_types"]) if "file_types" in meta else None, scopes.of(meta)),
        "revisions": parse_maat_csv(_read(out_dir, "maat-revisions.csv")),
        "plumbing": parse_maat_csv(_read(out_dir, "maat-plumbing.csv")),
        "coupling": parse_maat_csv(_read(out_dir, "maat-coupling.csv")),
        "companions": parse_maat_csv(_read(out_dir, "maat-companions.csv")),   # the hook's directed pairs; empty before 0.29
        "soc": parse_maat_csv(_read(out_dir, "maat-soc.csv")),   # sum of coupling; empty for an output directory from before 0.11
        "tests": parse_maat_csv(_read(out_dir, "maat-tests.csv")),   # test co-change per production file; empty before 0.12
        "entropy": parse_maat_csv(_read(out_dir, "maat-entropy.csv")),   # Hassan's change entropy per file; empty before 0.13
        "doa": doa,   # degree of authorship per file and person; empty before 0.19
        "latenight": parse_maat_csv(_read(out_dir, "maat-latenight.csv")),
        "components": parse_maat_csv(_read(out_dir, "maat-components.csv")),
        "authors": authors_rows,
        "age": parse_maat_csv(_read(out_dir, "maat-age.csv")),
        "ownership": ownership,
        "tools": tools,   # what the coding tools were credited with, kept out of the tables about people; {} when there are none
        "fixes": fixes,
        "fix_history": _fix_history(out_dir, fixes, meta, activity),   # which commits the recent fixes were, and when each file began
        "cohorts": parse_theseus(cohorts) if cohorts else {},
        "theseus_authors": surviving,
        "secrets": parse_secrets(_read(out_dir, "secrets.json")),
        # the wrapper writes the file only when the scan finished, so a killed step or an old output
        # directory leaves it missing, and the report must not claim a clean scan
        "secrets_scanned": isinstance(_read_json(out_dir, "secrets.json", None), list),
        "activity": activity,
        "functions": parse_functions(_read(out_dir, "functions.csv")),
        # the osv-scanner step writes the file whatever it found (no lock files, no local database, a
        # scan); a missing file means the step did not finish or the run predates it
        "dependencies": parse_dependencies(_read_json(out_dir, "dependencies.json", None)),
        "trend": _read_json(out_dir, "trend.json", {"samples": [], "files": {}}),
        "signing": _read_json(out_dir, "signing.json", {}) or {},   # commit signing coverage; {} before the step or after a killed one
        "hygiene": _read_json(out_dir, "hygiene.json", {}) or {},   # the hygiene checks (hygiene.py); {} before 0.15
        "unreachable": _read_json(out_dir, "unreachable.json", {}) or {},
        "structure": _read_json(out_dir, "structure.json", {}) or {},
        "provenance": provenance,   # trailers, cohorts, commit shape, agent files; {} before 0.17   # tree-sitter metrics (structure.py); {} without gitmole[structure]   # what the secrets step found outside reachable history
        "backtest": _nested(out_dir) if nested else None,
    }

"""Parsers for the files the tools write. Each takes text and returns plain data."""
from __future__ import annotations

import csv
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
FLOAT_COLUMNS = {"doa", "doa_decayed", "hcm"}


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
        "doa": parse_maat_csv(_read(out_dir, "maat-doa.csv")),   # degree of authorship per file and person; empty before 0.19
        "latenight": parse_maat_csv(_read(out_dir, "maat-latenight.csv")),
        "components": parse_maat_csv(_read(out_dir, "maat-components.csv")),
        "authors": parse_maat_csv(_read(out_dir, "maat-authors.csv")),
        "age": parse_maat_csv(_read(out_dir, "maat-age.csv")),
        "ownership": ownership,
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

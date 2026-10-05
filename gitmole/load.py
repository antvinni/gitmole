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
    rows = _json_or(text, []) if isinstance(text, str) else text   # a caller that parsed the file already passes its rows
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


def all_code(rows, scope=()) -> dict:
    """{path: scc's code lines} for every file scc counted, whatever its type: what the type filter left out
    is measured against this (classify.lines). Under --path, the files below its directories."""
    out = {}
    for r in rows if isinstance(rows, list) else []:
        for f in (r.get("Files") or []) if isinstance(r, dict) else []:
            path = _rel(f.get("Location", ""))
            if scopes.within(path, scope):
                out[path] = f.get("Code", 0)
    return out


NUMERIC_COLUMNS = {"n-revs", "degree", "average-revs", "n-authors", "age-months", "added", "deleted", "n-fixes", "recent-fixes", "tiny-revs",
                   "minor", "soc", "partners", "n-sets", "with-tests", "periods", "fa", "dl", "ac", "is_author", "is_author_decayed", "late",
                   "depth", "shared", "confidence", "commits", "renamed", "recent"}
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


SPAN_RATIO = 2   # a span more than twice the other's is not two parsers counting a brace differently


def _last_name(name: str) -> str:
    return re.split(r"[.:#]+", name)[-1] if name else ""


def cross_check(functions: list, structure: dict) -> list:
    """lizard's spans checked against the structure step's (tree-sitter), where both have the function: the
    same file and start line, one function starting there on each side, the same name where both have one,
    and a file tree-sitter parsed without errors. structure.json keeps only the functions over its own
    thresholds, so this covers the long and complex ones, which are the ones a table and a finding name.

    lizard loses its place in two ways. It ends a function early, at a nested function or a lambda it
    closes the outer one for (`executeRun`: 268 lines to lizard, 6,394 to tree-sitter): the span becomes
    the structure step's, the lines its line count, and the complexity stays lizard's, which is then a
    floor, since it counted only the part it read; lizard's own end and lines stay under `lizard_span`.
    Or it runs on past the end: when it also counted more lines of code than SPAN_RATIO times the lines
    the function has at all, it counted what follows as the function's (superpowers'
    extractAndStripFrontmatter: 33-382 and 339 lines to lizard, 33-68 to tree-sitter). The span and the
    lines become the structure step's here too, lizard's own staying under `lizard_overrun`, and the row is
    marked suspect, as the function step's own checks mark the swallowed spans they catch: the complexity
    is still lizard's, counted over what follows as well, so it is a ceiling nobody should rank or flag
    by. A row the function step already marked keeps its reason and is corrected the same way. A span
    that ran on over a comment or into functions lizard listed on their own (paperclip's passesFilter: 21
    lines of code over 61, of a 25-line function; brew's audit_deps) keeps its counts, which are the
    function's. Both need the spans to differ by more than SPAN_RATIO; nothing is ever unmarked by an
    over-run."""
    theirs = {}
    for s in (structure or {}).get("functions") or []:
        if not isinstance(s, dict) or not isinstance(s.get("start"), int) or not isinstance(s.get("end"), int):
            continue
        key = (s.get("file"), s["start"])
        theirs[key] = None if key in theirs else s   # two functions on one line: which is which cannot be told
    if not theirs:
        return functions
    parsed = (structure.get("files") or {}) if isinstance(structure.get("files"), dict) else {}
    mine = Counter((f["file"], f["start"]) for f in functions)
    for f in functions:
        key = (f["file"], f["start"])
        s = theirs.get(key)
        if s is None or mine[key] != 1 or (parsed.get(f["file"]) or {}).get("errors", True):
            continue
        if not (f.get("anonymous") or textfmt.nameless(s.get("name") or "") or _last_name(f["function"]) == _last_name(s.get("name") or "")):
            continue
        ours, real = f["end"] - f["start"] + 1, s["end"] - s["start"] + 1
        if real > SPAN_RATIO * ours:
            f["lizard_span"] = {"end": f["end"], "nloc": f["nloc"]}
            f.update(end=s["end"], nloc=real, suspect="")
        elif ours > SPAN_RATIO * real and f["nloc"] > SPAN_RATIO * real:
            f["suspect"] = f["suspect"] or f"{f['nloc']} lines of code in a function the structure step ends after {real} lines, at line {s['end']}"
            f["lizard_overrun"] = {"end": f["end"], "nloc": f["nloc"]}
            f.update(end=s["end"], nloc=real)
    return functions


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
        if r.get("TestCode") is True:   # inside a Rust #[cfg(test)] module of its file at that commit (leaks.mark_test_code)
            out[-1]["test_code"] = True
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
    vulnerable rows, database_date, the informational rows), no-sources, no-database, or not-run when there is no file."""
    if not isinstance(data, dict) or not data.get("status"):
        return {"status": "not-run"}
    out = {"status": data["status"]}
    if data["status"] == "scanned":
        out.update({"sources": data.get("sources") or [], "packages": _num(data.get("packages")),
                    "vulnerable": data.get("vulnerable") or [], "database_date": data.get("database_date")})
        if data.get("database_digest"):
            out["database_digest"] = data["database_digest"]
        if data.get("compose_builds"):
            out["compose_builds"] = data["compose_builds"]
        if data.get("informational"):   # packages whose every advisory is informational (deps.informational)
            out["informational"] = data["informational"]
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
    commits = maat.parse_log(text, None, filetypes.for_meta(meta))
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


def parse_imports(text: str, imports: list, tree) -> tuple:
    """What log.txt says about each import commit the change analysis found (activity.json's `imports`,
    which counts code files only): (the rows with these keys added, every path an import put something in,
    under every name it has had since).

    `files_all`, `added_all` and `binaries` are the commit's raw totals, as `git show --stat` gives them: every
    file, every added line, and the binary rows numstat writes as `-`. `under` is the conventionally
    vendored directory (filetypes.vendor_root) that every path the import brought in sits under, when they
    share one. `in_tree` is how many of those paths, their renames followed, the analysed commit still
    tracks, known only with a tree listing; it is 0 only when the log shows the rest deleted, and then
    `removed_in` is the commit that deleted the most of them, with how many commits it took.

    numstat has no status letter, so what the import brought in is read from the log: a path it added
    lines or a binary to that no older commit touched. A path an older commit touched is one the import
    changed (superpowers' .gitignore, two lines added beside 720 files of node_modules) and is not counted
    as its survivor; the cost is an import that brings back files deleted before it, whose survivors would
    be missed if everything new in it were gone. Gone is said only when the log shows it going: every
    path it brought in is untracked, and the last commit to touch each only took lines out. A subtree's squashed history names its files by their paths in the other repository
    (redis: deps/jemalloc/ arrives as src/arena.c), so none is ever tracked under that name, and the next
    squash changes them without deleting any: nothing is claimed of it.

    One pass over the log's lines, made only when there is an import to look up."""
    wanted = {c.get("hash") for c in imports}
    lines = text.split("\n")
    heads = [(i, line.split("--", 4)) for i, line in enumerate(lines) if line.startswith("--")]
    heads = [(i, parts[1], parts[2][:10]) for i, parts in heads if len(parts) > 3]
    at = {h: k for k, (_, h, _) in enumerate(heads) if h in wanted}

    def rows(k):
        end = heads[k + 1][0] if k + 1 < len(heads) else len(lines)
        for line in lines[heads[k][0] + 1:end]:
            parts = line.split("\t", 2)
            if len(parts) == 3:
                yield parts[0], filetypes.unquote(parts[2])

    out, every = [], set()
    for c in imports:
        k = at.get(c.get("hash"))
        if k is None:
            out.append(c)
            continue
        mine = list(rows(k))
        touched = {p for a, p in mine if " => " not in p and a != "0"}   # it put something there: lines, or a binary
        fresh = set(touched)
        for j in range(k + 1, len(heads)):   # the older commits: a path one of them touched was here before
            if not fresh:
                break
            for _, p in rows(j):
                fresh.discard(maat._renamed_to(p))
        roots = {filetypes.vendor_root(p) for p in fresh}
        row = {**c, "files_all": len(mine), "added_all": sum(int(a) for a, _ in mine if a.isdigit()),
               "binaries": sum(1 for a, _ in mine if a == "-")}
        if len(roots) == 1 and None not in roots:
            row["under"] = roots.pop()
        alive = {p: (p in fresh, None, False) for p in touched}   # the name now -> (brought in, the newest commit to touch it, which only took out)
        every |= touched
        for j in range(k - 1, -1, -1):   # the newer commits, oldest first
            for a, p in rows(j):
                if " => " in p:
                    old, new = _renamed_from(p), maat._renamed_to(p)
                    if old in alive and old != new:
                        alive[new] = (alive.pop(old)[0], j, False)
                        every.add(new)
                elif p in alive:
                    alive[p] = (alive[p][0], j, a in ("0", "-"))   # no line added: a deletion, as far as numstat shows one
        if tree is not None and fresh:
            held = sum(1 for p, (brought, _, _) in alive.items() if brought and p in tree)
            went = [t for p, t in alive.items() if p not in tree]
            if held or all(t[2] for t in went if t[0]):
                row["in_tree"] = held
            if not held and "in_tree" in row:
                # The commit that deleted the most of what it added to, the newest of them on a tie. Not simply
                # the newest: a file the import only changed may be deleted years later (yt-dlp's 3ca3f77f9
                # brought youtube_dl/ back for five months; one file it touched went in 2024).
                by = Counter(t[1] for t in went if t[2])
                j = min(by, key=lambda j: (-by[j], j))
                row["removed_in"] = {"hash": heads[j][1], "date": heads[j][2], "commits": len(by)}
        out.append(row)
    return out, frozenset(every)


def _imports(out_dir: str, activity, tree) -> frozenset:
    """parse_imports over the directory's log.txt, written into activity's rows; the paths the imports
    added to. Nothing when there is no import or no log (the backtest's sub-report)."""
    rows = activity.get("imports") if isinstance(activity, dict) else None
    path = os.path.join(out_dir, "log.txt")
    if not rows or not os.path.isfile(path):
        return frozenset()
    with open(path, encoding="utf-8", errors="replace", newline="") as fh:
        activity["imports"], paths = parse_imports(fh.read(), rows, tree)
    return paths


DOCUMENTS_KEPT = 15   # the most-changed documents a report keeps: the list shows five, --full and the JSON these


def parse_unscored_history(text: str, activity: dict, scored, documents=frozenset()) -> dict:
    """What the log says about the files nothing ranks, read from log.txt, which holds every path whatever
    its type: {"commits": {commits, fixes, outside, fixes_outside}, "revisions": {document: n}}.

    `outside` counts the commits that changed files and none that is scored (`scored(path)`), `fixes_outside`
    the fix commits among them: the header's "N% of commits are fixes" is over every commit, the bug magnets
    over scored files only, and these two say how far apart the populations are. Both are over the commits
    the header counts (the window), merges included in the total and, having no file list, never outside.
    `revisions` counts each of `documents` the way the change analysis counts a source file: in the window,
    less the sweeps and imports activity.json lists."""
    activity = activity or {}
    commits = maat.in_window(maat.parse_log(text), activity.get("window"), activity.get("until"))
    left_out = {c.get("hash") for key in ("sweeping", "imports") for c in activity.get(key) or []}
    counts, revisions = {"commits": len(commits), "fixes": 0, "outside": 0, "fixes_outside": 0}, Counter()
    for c in commits:
        fix = maat.is_fix(c.get("subject", ""))
        counts["fixes"] += fix
        if c["files"] and not any(scored(path) for path, _, _ in c["files"]):
            counts["outside"] += 1
            counts["fixes_outside"] += fix
        if documents and c["hash"] not in left_out:
            revisions.update(path for path, _, _ in c["files"] if path in documents)
    return {"commits": counts, "revisions": dict(revisions)}


def _coverage(out_dir: str, report: dict, code: dict) -> dict:
    """What the report ranks and what it leaves out by type: {files, lines, unranked} and, when the files the
    type filter left out hold more lines than the scored ones (classify.unranked), {commits} and, when
    documentation is most of the tree (classify.DOC_MAJORITY), {documents}: its most-revised files. {} for
    a run that recorded no coverage (an older one, or one whose steps did not finish). The log is read
    only for a repository the line is shown on, so the others pay for a pass over the tree listing and
    nothing else."""
    from . import classify
    files = report["meta"].get("coverage") or {}
    tree = report.get("tree")
    if tree is not None:   # scc counts the working directory: an untracked file there (an --out inside the
        tracked = set(tree)   # clone, written while scc runs) is not the repository's, and differs run to run
        code = {p: n for p, n in code.items() if p in tracked}
    if not files or not code:
        return {}
    cls = classify.Classifier(report)
    lines = classify.lines(cls, code)
    out = {"files": files, "lines": lines, "unranked": classify.unranked(lines)}
    path = os.path.join(out_dir, "log.txt")
    if not out["unranked"] or not os.path.isfile(path):
        return out
    documents = classify.documents(cls, code) if classify.documents_lead(lines) else frozenset()
    with open(path, encoding="utf-8", errors="replace", newline="") as fh:
        history = parse_unscored_history(fh.read(), report.get("activity"), lambda p: cls.reason(p) is None, documents)
    out["commits"] = history["commits"]
    if documents:
        ranked = sorted(((p, n) for p, n in history["revisions"].items() if n >= 2), key=lambda kv: (-kv[1], kv[0]))
        out["documents"] = [{"file": p, "revisions": n} for p, n in ranked[:DOCUMENTS_KEPT]]
    return out


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
    address, or a name credited there by trailers), and what the tools were credited with, kept apart: ownership, owners and authors, minor contributors, the degree of authorship the truck factor
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


_LABEL = re.compile(r"^(?P<name>.*) <(?P<email>[^<>]*)>$")


def split_label(label: str) -> tuple:
    """(name, email) from an authors.json label: `Name <email>` since 0.42 (blame.label), a bare name from an
    older run or from git-of-theseus, whose email is then None."""
    m = _LABEL.match(label)
    return (m.group("name"), m.group("email")) if m else (label, None)


def _surviving_by_identity(meta: dict, lines_by_label: dict, canonical: dict, is_bot) -> dict:
    """{"name <email>" of an identity row in meta (identity.row_label): surviving lines}. A label's name and address pick the row
    holding that variant, so two rows that share a display name (a person and a trailer-only alias of the
    same spelling, three product agents called one thing) each keep their own lines. A label without an
    address (an older run, git-of-theseus) or one no row holds goes to the first row, the most committed,
    that carries its name: once, where the name-keyed table gave every such row all of it."""
    ids = meta.get("identities") or []
    by_variant, by_name = {}, {}
    for n, i in enumerate(ids):
        for v in [i, *(i.get("aliases") or [])]:
            by_variant.setdefault((v.get("name"), (v.get("email") or "").lower()), n)
            by_name.setdefault(v.get("name"), n)
    out = Counter()
    for lbl, lines in lines_by_label.items():
        name, email = split_label(lbl)
        if is_bot(canonical.get(name, name)):
            continue
        n = by_variant.get((name, email.lower())) if email is not None else None
        if n is None:
            n = by_name.get(name, by_name.get(canonical.get(name, name)))
        if n is not None:
            out[identity.row_label(ids[n])] += lines
    return {k: int(v) for k, v in sorted(out.items())}


def _merges_once(meta: dict) -> None:
    """An older run counted merges per display name and gave each identity row carrying the name the whole
    count (paperclip: a trailer-only alias of the maintainer showed -348 commits, and 725 merges in all
    against git's 376). Such a run keeps the count once, on the first row of the name, the most committed;
    a run that counted them per identity says so (merges_by)."""
    if meta.get("merges_by") == "identity":
        return
    seen = set()
    for i in meta.get("identities") or []:
        if i.get("merges"):
            names = frozenset([i["name"], *(a["name"] for a in i.get("aliases") or [])])
            if names & seen:
                i.pop("merges")
            seen |= names


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
    lines_by_label = parse_theseus(authors) if authors else {}
    _merges_once(meta)
    by_identity = _surviving_by_identity(meta, lines_by_label, canonical, is_bot)
    for lbl, lines in lines_by_label.items():
        name = split_label(lbl)[0]
        key = canonical.get(name, name)
        if is_bot(key):   # a deploy job that committed a built site owns nothing anyone needs to know
            continue
        surviving[key] = surviving.get(key, 0) + lines
    ownership = [r for r in parse_maat_csv(_read(out_dir, "maat-entity-ownership.csv")) if not is_bot(r.get("author") or "")]
    for r in ownership:   # a blank `recent` is 0, and the key is kept only where there is a count (meta's ownership_recent says it was counted)
        if "recent" in r and not r["recent"]:
            del r["recent"]
    fixes = parse_maat_csv(_read(out_dir, "maat-fixes.csv"))
    activity = _read_json(out_dir, "activity.json", {})
    provenance = _read_json(out_dir, "provenance.json", {}) or {}
    _authored(meta, activity if isinstance(activity, dict) else {}, provenance if isinstance(provenance, dict) else {})
    ownership, authors_rows, doa, surviving, tools = _tools_apart(meta, ownership, parse_maat_csv(_read(out_dir, "maat-authors.csv")),
                                                                  parse_maat_csv(_read(out_dir, "maat-doa.csv")), surviving)
    doa = [{k: v for k, v in r.items() if k not in DECAYED} for r in doa]   # read for the recount above; the tables never showed them
    structure = _read_json(out_dir, "structure.json", {}) or {}   # tree-sitter metrics (structure.py); {} without gitmole[structure]
    if not isinstance(structure, dict):
        structure = {}
    tree = parse_tree(out_dir, meta)
    scc_rows = _json_or(_read(out_dir, "size.json"), [])   # parsed once: the size tables read the code files, the coverage every file
    report = {
        "out_dir": out_dir,
        "meta": meta,
        "tree": tree,   # every path at HEAD, binaries too; None before 0.39
        "imported": _imports(out_dir, activity, tree),   # the paths the import commits added to; the rows themselves are in activity
        # a run records its --file-types spec (None for the default list); a run from before that record
        # was measured unfiltered, so it is re-rendered unfiltered rather than with a guessed list
        "size": parse_scc(scc_rows, filetypes.for_meta(meta, unrecorded=None), scopes.of(meta)),
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
        # when each path first appeared and whether by a rename, for the files HEAD has (the area ages read no
        # others); absent before 0.45, so an older output directory dates no area
        "arrivals": [r for r in parse_maat_csv(_read(out_dir, "maat-arrivals.csv")) if tree is None or r["entity"] in tree],
        "authors": authors_rows,
        "age": parse_maat_csv(_read(out_dir, "maat-age.csv")),
        "ownership": ownership,
        "tools": tools,   # what the coding tools were credited with, kept out of the tables about people; {} when there are none
        "fixes": fixes,
        "fix_history": _fix_history(out_dir, fixes, meta, activity),   # which commits the recent fixes were, and when each file began
        "cohorts": parse_theseus(cohorts) if cohorts else {},
        "theseus_authors": surviving,   # by canonical name, as every table about people keys them
        "surviving_by_identity": by_identity,   # by "name <email>" of meta's identity rows: the People table's column
        "secrets": parse_secrets(_read(out_dir, "secrets.json")),
        # the wrapper writes the file only when the scan finished, so a killed step or an old output
        # directory leaves it missing, and the report must not claim a clean scan
        "secrets_scanned": isinstance(_read_json(out_dir, "secrets.json", None), list),
        "activity": activity,
        # lizard's spans, checked against the structure step's where it has the same function (cross_check)
        "functions": cross_check(parse_functions(_read(out_dir, "functions.csv")), structure),
        # the osv-scanner step writes the file whatever it found (no lock files, no local database, a
        # scan); a missing file means the step did not finish or the run predates it
        "dependencies": parse_dependencies(_read_json(out_dir, "dependencies.json", None)),
        "trend": _read_json(out_dir, "trend.json", {"samples": [], "files": {}}),
        "signing": _read_json(out_dir, "signing.json", {}) or {},   # commit signing coverage; {} before the step or after a killed one
        "hygiene": _read_json(out_dir, "hygiene.json", {}) or {},   # the hygiene checks (hygiene.py); {} before 0.15
        "unreachable": _read_json(out_dir, "unreachable.json", {}) or {},
        "structure": structure,
        "provenance": provenance,   # trailers, cohorts, commit shape, agent files; {} before 0.17   # tree-sitter metrics (structure.py); {} without gitmole[structure]   # what the secrets step found outside reachable history
        "backtest": _nested(out_dir) if nested else None,
    }
    # what is ranked and what the type filter left out; {} before the run recorded its coverage
    report["coverage"] = _coverage(out_dir, report, all_code(scc_rows, scopes.of(meta)))
    return report

"""Parsers for the files the tools write. Each takes text and returns plain data."""
from __future__ import annotations

import csv
import io
import sys
import json
import os
import re
from collections import Counter, OrderedDict

from . import filetypes, identity, leaks, textfmt


def _rel(path: str) -> str:
    """Tools started in the repo print './x'; the log and blame say 'x'."""
    return path[2:] if path.startswith("./") else path


def _only(rows: list, types) -> list:
    """scc's language rows with the files outside `types` dropped and the totals rebuilt from what is
    left. A row without per-file data (an older size.json) is kept as it is."""
    out = []
    for r in rows:
        files = r.get("Files")
        if files is None:
            out.append(r)
            continue
        kept = [f for f in files if filetypes.matches(_rel(f.get("Location", "")), types)]
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


def parse_scc(text: str, types=None) -> dict:
    """scc --by-file JSON as languages and per-file rows. `types` (as filetypes.parse gives it: a
    set, or None for everything) keeps only the code files, so the size matches the other tables."""
    rows = _json_or(text, [])
    if not isinstance(rows, list):
        rows = []
    if types is not None:
        rows = _only(rows, types)
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
                   "minor", "soc", "partners", "n-sets", "with-tests", "periods"}


def parse_maat_csv(text: str) -> list:
    """Rows as dicts. Only known numeric columns become ints; a file or author named 2024 stays a string."""
    if not text.strip():
        return []
    out = []
    for row in csv.DictReader(io.StringIO(text)):
        out.append({k: (_num(v) if k in NUMERIC_COLUMNS else v) for k, v in row.items()})
    return out


def _num(v):
    """An int for a numeric cell; 0 for a missing, empty or garbage one (a row cut short by a killed step)."""
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


_SIZER_ROW = re.compile(r"^\|(?P<pad> *)(?P<name>.*?)\s*(?:\[(?P<ref>\d+)\])?\s*\|\s*(?P<value>.*?)\s*\|\s*(?P<concern>\**)\s*\|$")
_SIZER_NOTE = re.compile(r"^\[(?P<ref>\d+)\]\s+\S+\s+\((?:[^:]+:)?(?P<path>[^)]*)\)")


def parse_git_sizer(text: str) -> list:
    notes = {}
    for line in text.splitlines():
        m = _SIZER_NOTE.match(line)
        if m:
            notes[m.group("ref")] = m.group("path")

    # Two shapes of section: "Overall repository size" and "Biggest objects" have sub-headers
    # ("* Blobs") with their metrics indented under them; "History structure" and "Biggest
    # checkouts" list their metrics directly ("* Number of files"). A starred line with a value
    # is a metric, a starred line without one is a sub-header, an unstarred line is a section.
    rows, section, sub = [], "", ""
    for line in text.splitlines():
        m = _SIZER_ROW.match(line)
        if not m:
            continue
        indent = len(m.group("pad")) - 1
        raw = m.group("name").strip()
        name = raw.lstrip("* ").strip()
        if not name or name == "Name" or name.startswith("---"):
            continue
        if indent == 0 and not raw.startswith("*"):
            section = sub = name
            continue
        if indent == 0 and not m.group("value"):
            sub = name
            continue
        if not m.group("concern"):
            continue
        rows.append({
            "name": f"{sub if indent else section}: {name}",
            "value": m.group("value"),
            "concern": len(m.group("concern")),
            "ref": notes.get(m.group("ref") or "", ""),
        })
    return rows


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
    stays marked anonymous so the report can say where it is."""
    rows = []
    for r in csv.reader(io.StringIO(text)):
        if len(r) < 11:
            continue
        name, label, suspect = r[7], r[11] if len(r) > 11 else "", r[12] if len(r) > 12 else ""
        anonymous = name in ("", "(anonymous)")
        rows.append({"file": _rel(r[6]), "function": textfmt.cut(label if anonymous and label else name, NAME_CAP) or "(anonymous)", "anonymous": anonymous,
                     "ccn": _num(r[1]), "nloc": _num(r[0]), "params": _num(r[3]), "start": _num(r[9]), "end": _num(r[10]), "suspect": suspect})
    return rows


_DUP_PLACE = re.compile(r"^(.+?):(\d+) ~ (\d+)$")
_DUP_RATE = re.compile(r"Total duplicate rate:\s*([\d.]+)%")


def parse_duplicates_json(data) -> dict | None:
    """duplicates.json as the jscpd step writes it: the rate over the kept files and the blocks, largest
    first, each place a (path, start, end) tuple. None when there is no such file."""
    if not isinstance(data, dict):
        return None
    blocks = [{"lines": _num(b.get("lines")), "places": sorted(tuple(p[:3]) for p in b.get("places") or [] if len(p) >= 3)}
              for b in data.get("blocks") or []]
    rate = data.get("rate")
    out = {"rate": float(rate) if rate is not None else None, "blocks": blocks, "files": _num(data.get("files"))}
    if isinstance(data.get("then"), dict):
        out["then"] = data["then"]   # the rate at the last commit a year before: the direction
    return out


def parse_duplicates(text: str) -> dict:
    """lizard -Eduplicate output, which runs before 0.7 wrote: blocks of 'path:start ~ end' lines and the overall rate."""
    blocks, current = [], None
    for line in text.splitlines():
        line = line.rstrip()
        if line == "Duplicate block:":
            current = []
        elif current is not None:
            m = _DUP_PLACE.match(line)
            if m:
                current.append((_rel(m.group(1)), int(m.group(2)), int(m.group(3))))
            elif line.startswith("^^^"):
                if current:
                    blocks.append({"lines": current[0][2] - current[0][1] + 1, "places": sorted(current)})
                current = None
    m = _DUP_RATE.search(text)
    return {"rate": float(m.group(1)) if m else None, "blocks": blocks}


def parse_secrets(text: str) -> list:
    """betterleaks rows as rule, file, short commit, line, fingerprint, the hashed value and the placeholder
    flag. A report written before values were hashed still has them: hash them here, keep nothing raw."""
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
                    "fingerprint": r.get("Fingerprint", ""), "value": value, "placeholder": placeholder})
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
    elif data["status"] == "no-database":
        out["download"] = data.get("download") or ""
    return out


def _read(out_dir: str, name: str) -> str:
    path = os.path.join(out_dir, name)
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


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
    return {
        "out_dir": out_dir,
        "meta": meta,
        # a run records its --file-types spec (None for the default list); a run from before that record
        # was measured unfiltered, so it is re-rendered unfiltered rather than with a guessed list
        "size": parse_scc(_read(out_dir, "size.json"), filetypes.parse(meta["file_types"]) if "file_types" in meta else None),
        "revisions": parse_maat_csv(_read(out_dir, "maat-revisions.csv")),
        "plumbing": parse_maat_csv(_read(out_dir, "maat-plumbing.csv")),
        "coupling": parse_maat_csv(_read(out_dir, "maat-coupling.csv")),
        "soc": parse_maat_csv(_read(out_dir, "maat-soc.csv")),   # sum of coupling; empty for an output directory from before 0.11
        "tests": parse_maat_csv(_read(out_dir, "maat-tests.csv")),   # test co-change per production file; empty before 0.12
        "entropy": parse_maat_csv(_read(out_dir, "maat-entropy.csv")),   # Hassan's change entropy per file; empty before 0.13
        "authors": parse_maat_csv(_read(out_dir, "maat-authors.csv")),
        "age": parse_maat_csv(_read(out_dir, "maat-age.csv")),
        "ownership": ownership,
        "fixes": parse_maat_csv(_read(out_dir, "maat-fixes.csv")),
        "sizer": parse_git_sizer(_read(out_dir, "repo-health.txt")),
        "cohorts": parse_theseus(cohorts) if cohorts else {},
        "theseus_authors": surviving,
        "secrets": parse_secrets(_read(out_dir, "secrets.json")),
        # the wrapper writes the file only when the scan finished, so a killed step or an old output
        # directory leaves it missing, and the report must not claim a clean scan
        "secrets_scanned": isinstance(_read_json(out_dir, "secrets.json", None), list),
        "activity": _read_json(out_dir, "activity.json", {}),
        "functions": parse_functions(_read(out_dir, "functions.csv")),
        "duplicates": parse_duplicates_json(_read_json(out_dir, "duplicates.json", None)) or parse_duplicates(_read(out_dir, "duplicates.txt")),
        # the osv-scanner step writes the file whatever it found (no lock files, no local database, a
        # scan); a missing file means the step did not finish or the run predates it
        "dependencies": parse_dependencies(_read_json(out_dir, "dependencies.json", None)),
        "trend": _read_json(out_dir, "trend.json", {"samples": [], "files": {}}),
        "signing": _read_json(out_dir, "signing.json", {}) or {},   # commit signing coverage; {} before the step or after a killed one
        "hygiene": _read_json(out_dir, "hygiene.json", {}) or {},   # the hygiene checks (hygiene.py); {} before 0.15
        "unreachable": _read_json(out_dir, "unreachable.json", {}) or {},
        "structure": _read_json(out_dir, "structure.json", {}) or {},
        "provenance": _read_json(out_dir, "provenance.json", {}) or {},   # trailers, cohorts, commit shape, agent files; {} before 0.17   # tree-sitter metrics (structure.py); {} without gitmole[structure]   # what the secrets step found outside reachable history
        "backtest": _nested(out_dir) if nested else None,
    }

"""Parsers for the files the tools write. Each takes text and returns plain data."""
from __future__ import annotations

import csv
import io
import json
import os
import re
from collections import Counter, OrderedDict

from . import filetypes, identity, leaks


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


def parse_scc(text: str, types=None) -> dict:
    """scc --by-file JSON as languages and per-file rows. `types` (as filetypes.parse gives it: a
    set, or None for everything) keeps only the code files, so the size matches the other tables."""
    rows = json.loads(text) if text.strip() else []
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


NUMERIC_COLUMNS = {"n-revs", "degree", "average-revs", "n-authors", "age-months", "added", "deleted", "n-fixes", "recent-fixes"}


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
    d = json.loads(text)
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


def parse_functions(text: str) -> list:
    """lizard --csv rows: nloc, ccn, tokens, params, length, location, file, function, long name, start, end."""
    rows = []
    for r in csv.reader(io.StringIO(text)):
        if len(r) < 11:
            continue
        rows.append({"file": _rel(r[6]), "function": r[7], "ccn": _num(r[1]), "nloc": _num(r[0]), "params": _num(r[3]),
                     "start": _num(r[9]), "end": _num(r[10])})
    return rows


_DUP_PLACE = re.compile(r"^(.+?):(\d+) ~ (\d+)$")
_DUP_RATE = re.compile(r"Total duplicate rate:\s*([\d.]+)%")


def parse_duplicates(text: str) -> dict:
    """lizard -Eduplicate output: blocks of 'path:start ~ end' lines and the overall rate."""
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
    """gitleaks rows as rule, file, short commit, line, fingerprint, the hashed value and the placeholder
    flag. A report written before values were hashed still has them: hash them here, keep nothing raw."""
    rows = json.loads(text) if text.strip() else []
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


def _read(out_dir: str, name: str) -> str:
    path = os.path.join(out_dir, name)
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _read_json(out_dir: str, name: str, default):
    """`default` for a missing file or one a killed step left truncated or malformed."""
    text = _read(out_dir, name)
    if not text:
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return default


def load_report(out_dir: str, nested: bool = True) -> dict:
    """Read every output file gitmole writes. Missing optional files become empty values.

    `nested`: also load the backtest sub-report (out_dir/backtest), one level deep only."""
    meta = json.loads(_read(out_dir, "meta.json") or "{}")
    cohorts = _read(out_dir, "theseus/cohorts.json")
    authors = _read(out_dir, "theseus/authors.json")
    canonical = dict(meta["aliases"]) if "aliases" in meta else identity.canonical_names(meta.get("identities") or [])
    surviving = OrderedDict()
    for name, lines in (parse_theseus(authors) if authors else {}).items():
        key = canonical.get(name, name)
        surviving[key] = surviving.get(key, 0) + lines
    return {
        "out_dir": out_dir,
        "meta": meta,
        # a run records its --file-types spec (None for the default list); a run from before that record
        # was measured unfiltered, so it is re-rendered unfiltered rather than with a guessed list
        "size": parse_scc(_read(out_dir, "size.json"), filetypes.parse(meta["file_types"]) if "file_types" in meta else None),
        "revisions": parse_maat_csv(_read(out_dir, "maat-revisions.csv")),
        "coupling": parse_maat_csv(_read(out_dir, "maat-coupling.csv")),
        "authors": parse_maat_csv(_read(out_dir, "maat-authors.csv")),
        "age": parse_maat_csv(_read(out_dir, "maat-age.csv")),
        "ownership": parse_maat_csv(_read(out_dir, "maat-entity-ownership.csv")),
        "fixes": parse_maat_csv(_read(out_dir, "maat-fixes.csv")),
        "sizer": parse_git_sizer(_read(out_dir, "repo-health.txt")),
        "cohorts": parse_theseus(cohorts) if cohorts else {},
        "theseus_authors": surviving,
        "secrets": parse_secrets(_read(out_dir, "secrets.json")),
        "activity": _read_json(out_dir, "activity.json", {}),
        "functions": parse_functions(_read(out_dir, "functions.csv")),
        "duplicates": parse_duplicates(_read(out_dir, "duplicates.txt")),
        "trend": _read_json(out_dir, "trend.json", {"samples": [], "files": {}}),
        "backtest": load_report(os.path.join(out_dir, "backtest"), nested=False)
                    if nested and os.path.isfile(os.path.join(out_dir, "backtest", "meta.json")) else None,
    }

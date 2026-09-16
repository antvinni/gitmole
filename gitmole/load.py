"""Parsers for the files the tools write. Each takes text and returns plain data."""
from __future__ import annotations

import csv
import io
import json
import os
import re
from collections import Counter, OrderedDict

from . import identity


def _rel(path: str) -> str:
    """Tools started in the repo print './x'; the log and blame say 'x'."""
    return path[2:] if path.startswith("./") else path


def parse_scc(text: str) -> dict:
    rows = json.loads(text) if text.strip() else []
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

    rows, section = [], ""
    for line in text.splitlines():
        m = _SIZER_ROW.match(line)
        if not m:
            continue
        indent = len(m.group("pad")) - 1
        name = m.group("name").strip().lstrip("* ").strip()
        if not name or name == "Name" or name.startswith("---"):
            continue
        if indent == 0:
            section = name
            continue
        if not m.group("concern"):
            continue
        rows.append({
            "name": f"{section}: {name}",
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
                    blocks.append({"lines": current[0][2] - current[0][1] + 1, "places": current})
                current = None
    m = _DUP_RATE.search(text)
    return {"rate": float(m.group(1)) if m else None, "blocks": blocks}


def parse_secrets(text: str) -> list:
    rows = json.loads(text) if text.strip() else []
    return [
        {"rule": r.get("RuleID", ""), "file": r.get("File", ""), "commit": r.get("Commit", "")[:7], "line": r.get("StartLine")}
        for r in rows
    ]


def _read(out_dir: str, name: str) -> str:
    path = os.path.join(out_dir, name)
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def load_report(out_dir: str) -> dict:
    """Read every output file gitmole writes. Missing optional files become empty values."""
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
        "size": parse_scc(_read(out_dir, "size.json")),
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
        "activity": json.loads(_read(out_dir, "activity.json") or "{}"),
        "functions": parse_functions(_read(out_dir, "functions.csv")),
        "duplicates": parse_duplicates(_read(out_dir, "duplicates.txt")),
    }

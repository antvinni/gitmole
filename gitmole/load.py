"""Parsers for the files the tools write. Each takes text and returns plain data."""
from __future__ import annotations

import csv
import io
import json
import os
import re
from collections import Counter, OrderedDict

from . import identity


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
            loc = f.get("Location", "")
            loc = loc[2:] if loc.startswith("./") else loc
            files[loc] = {"code": f.get("Code", 0), "complexity": f.get("Complexity", 0)}
    return {
        "languages": languages,
        "total_code": sum(r["code"] for r in languages),
        "total_files": sum(r["files"] for r in languages),
        "files": files,
    }


def parse_maat_csv(text: str) -> list:
    if not text.strip():
        return []
    out = []
    for row in csv.DictReader(io.StringIO(text)):
        out.append({k: _num(v) for k, v in row.items()})
    return out


def _num(v):
    if v is None:
        return v
    try:
        return int(v)
    except ValueError:
        return v


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
    }

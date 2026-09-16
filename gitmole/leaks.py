#!/usr/bin/env python3
"""gitleaks, with the secret values kept out of the output directory.

gitmole runs this as the gitleaks step: `python3 leaks.py OUT_JSON`, from inside the repository.
gitleaks writes its JSON report to our stdout, so the raw report is never a file; each value is
replaced by a short hash (enough to tell one value repeated in many places from many values) and a
flag for shapes that cannot be a live secret, and only that is written. The report never needed the
values: it names the rule, the file and the commit. Standalone, like maat.py and blame.py.

The same module groups the loaded rows for the findings and the report footer.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile

try:
    from . import filetypes
except ImportError:  # run as a script: the package directory is sys.path[0]
    import filetypes

ARGV = ["gitleaks", "git", "--no-banner", "--report-format", "json", "--report-path", "-", "--exit-code", "0"]
RAW_FIELDS = ("Secret", "Match", "Line", "Message")   # the value, the text around it, and the commit message, which can quote it

# A version string (5.0.0-1667386184.dfbbb54) and a token shortened with an ellipsis are the only shapes
# skipped. Nothing is skipped by prefix: a public and a private key of the same service often share one.
_VERSION = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", "surrogateescape")).hexdigest()[:12]


def is_placeholder(value: str) -> bool:
    value = value or ""
    return bool(_VERSION.match(value)) or value.endswith("...") or value.endswith("…")


def sanitise(rows: list) -> list:
    out = []
    for r in rows:
        value = r.get("Secret") or ""
        clean = {k: v for k, v in r.items() if k not in RAW_FIELDS}
        clean["SecretHash"] = digest(value)
        clean["Placeholder"] = is_placeholder(value)
        out.append(clean)
    return out


def group(rows: list) -> list:
    """One entry per distinct secret value (placeholders left out): its rule, the files and commits it
    appears in, the number of distinct places (commit, file, line), and whether every place is a test
    file. Values that appear in source come first, then the most widespread."""
    groups, order = {}, []
    for i, r in enumerate(rows):
        if r.get("placeholder"):
            continue
        key = r.get("value") or ("row", i)
        if key not in groups:
            groups[key] = {"value": r.get("value"), "rule": r["rule"], "files": [], "commits": [], "_places": set(), "test": True}
            order.append(key)
        g = groups[key]
        if r["file"] not in g["files"]:
            g["files"].append(r["file"])
        if r["commit"] not in g["commits"]:
            g["commits"].append(r["commit"])
        g["_places"].add((r["commit"], r["file"], r.get("line")))
        g["test"] = g["test"] and filetypes.is_test_path(r["file"])
    out = []
    for key in order:
        g = groups[key]
        places = g.pop("_places")
        out.append({**g, "places": len(places)})
    out.sort(key=lambda g: (g["test"], -g["places"]))   # stable: first-seen order breaks ties
    return out


def placeholders(rows: list) -> int:
    """Distinct places whose value had a placeholder shape."""
    return len({(r["commit"], r["file"], r.get("line")) for r in rows if r.get("placeholder")})


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: leaks.py OUT_JSON", file=sys.stderr)
        return 2
    target = args[0]
    # stderr is inherited, so gitleaks' own log lands in run.log as before
    proc = subprocess.run(ARGV, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE)
    if proc.returncode != 0:
        print(f"leaks.py: gitleaks exited {proc.returncode}; no report written", file=sys.stderr)
        return proc.returncode
    text = proc.stdout.decode("utf-8", "surrogateescape").strip()
    rows = sanitise(json.loads(text) if text else [])
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(target)), prefix=".secrets-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(rows, fh, indent=1)
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return 0


if __name__ == "__main__":
    sys.exit(main())

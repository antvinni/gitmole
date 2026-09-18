"""python -m gitmole.measure: the measurement harness of docs/measurement.md.

    python -m gitmole.measure run [--ref REF]... [--sets development,awkward,gate]   # one or more releases
    python -m gitmole.measure history [--sets ...] [--force]                         # every release tag, oldest first
    python -m gitmole.measure extras                                                 # the current tree's one-off checks
    python -m gitmole.measure report                                                 # docs/measurement-history.md and the graphs
    python -m gitmole.measure labels dump|score                                      # the hand-label sheet and its verdicts

Runs are sequential, one repository at a time, so the times and memory are comparable. Records go to
docs/measurements/<version>.json, one per release, committed so two releases diff."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys

from . import corpus, dashboard, harness

RECORDS = os.path.join(corpus.ROOT, "docs", "measurements")
DEFAULT_SETS = "development,awkward,gate"


def _labels_dir() -> str:
    return os.environ.get("GITMOLE_LABELS_DIR") or os.path.join(corpus.workspace(), "labels")


def measure(ref: str, sets: list, manifest: dict, root: str, only=None) -> dict:
    src = harness.source(ref, root)
    version = harness.version_of(src)
    commit = subprocess.run(["git", "rev-parse", ref if ref != "worktree" else "HEAD"], cwd=corpus.ROOT, capture_output=True, text=True).stdout.strip()
    record = {"version": version, "ref": ref, "commit": commit, "measured": dt.date.today().isoformat(),
              "sets": sets, "reference_date": manifest["reference_date"], "repos": {}}
    for entry in corpus.entries(manifest, sets):
        if only and entry["name"] not in only:
            continue
        print(f"measure: {version} {entry['name']}", file=sys.stderr, flush=True)
        try:
            rec = harness.measure_entry(src, entry, root, manifest["reference_date"], _labels_dir())
        except Exception as e:   # the harness failing is not the release failing: record it and go on
            rec = {"status": "harness-error", "note": f"{type(e).__name__}: {e}"[:200]}
        rec["set"] = entry["set"]
        record["repos"][entry["name"]] = rec
    record["summary"] = dashboard.summarise(record)
    return record


def write(record: dict, directory: str = RECORDS) -> str:
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, f"{record['version']}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=1, sort_keys=True)
        fh.write("\n")
    return path


def tags() -> list:
    out = subprocess.run(["git", "tag", "--list", "v*", "--sort=creatordate"], cwd=corpus.ROOT, capture_output=True, text=True, check=True).stdout
    return [t for t in out.split() if t]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m gitmole.measure", description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run")
    r.add_argument("--ref", action="append", default=[], help="a release tag, or worktree (default)")
    r.add_argument("--sets", default=DEFAULT_SETS)
    r.add_argument("--only", action="append", default=[], help="only these corpus entries")
    h = sub.add_parser("history")
    h.add_argument("--sets", default=DEFAULT_SETS)
    h.add_argument("--force", action="store_true", help="measure a release again even when its record exists")
    sub.add_parser("extras")
    sub.add_parser("report")
    lab = sub.add_parser("labels")
    lab.add_argument("action", choices=["dump", "score"])
    args = p.parse_args(argv)
    manifest = corpus.load()
    root = corpus.workspace()
    if args.command == "run":
        for ref in args.ref or ["worktree"]:
            print(write(measure(ref, args.sets.split(","), manifest, root, set(args.only) or None)))
        return 0
    if args.command == "history":
        have = {r["version"] for r in dashboard.load_history(RECORDS)} if os.path.isdir(RECORDS) else set()
        for tag in tags():
            if tag.lstrip("v") in have and not args.force:
                continue
            print(write(measure(tag, args.sets.split(","), manifest, root)), flush=True)
        return 0
    if args.command == "extras":
        from . import extras
        print(write(extras.run_all(manifest, root), os.path.join(RECORDS, "extras")))
        return 0
    if args.command == "report":
        from . import report
        for path in report.render(RECORDS):
            print(path)
        return 0
    if args.command == "labels":
        from . import labels
        return labels.main(args.action, RECORDS)
    return 2


if __name__ == "__main__":
    sys.exit(main())

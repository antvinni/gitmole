"""python -m gitmole.measure: the measurement harness of docs/measurement.md.

    python -m gitmole.measure run [--ref REF]... [--sets development,awkward,gate | --release]   # one or more releases
    python -m gitmole.measure extras [--release]                                                 # the current tree's one-off checks
    python -m gitmole.measure report                                                             # docs/measurement-history.md and the graphs
    python -m gitmole.measure labels dump|score                                                  # the hand-label sheet and its verdicts
    python -m gitmole.measure consistency [--version V] [--rerender]                             # findings against the report's own facts
    python -m gitmole.measure positives [--version V] [--sets development]                     # share of each pool fixed, per cut-off

The timed runs are sequential, one repository at a time and nothing else on the machine, so the times
and memory are comparable. The rankings at cut-offs are not timed, so they run side by side once every
timed run is over (--jobs). Records go to docs/measurements/<version>.json, one per measured release, committed
so two releases diff."""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

from . import corpus, dashboard, harness

RECORDS = os.path.join(corpus.ROOT, "docs", "measurements")
DEFAULT_SETS = "development,awkward,gate"
RELEASE_SETS = "development,large,awkward,gate,well-kept"   # a release round: the fast loop's sets, the large repositories and the well-kept gate
JOBS = 3   # rankings side by side; each backtest of a large history can take about the release run's peak memory


def resolve_sets(sets, release: bool) -> list:
    """--sets or --release, never both: a release round's sets are fixed so that its records compare."""
    if release and sets is not None:
        raise ValueError(f"--sets and --release are exclusive (--release runs {RELEASE_SETS})")
    return (RELEASE_SETS if release else sets or DEFAULT_SETS).split(",")


def _labels_dir() -> str:
    return os.environ.get("GITMOLE_LABELS_DIR") or os.path.join(corpus.workspace(), "labels")


def _error(e: Exception) -> dict:
    return {"status": "harness-error", "note": f"{type(e).__name__}: {e}"[:200]}


def measure(ref: str, sets: list, manifest: dict, root: str, only=None, jobs: int = JOBS) -> dict:
    src = harness.source(ref, root)
    version = harness.version_of(src)
    reference = manifest["reference_date"]
    commit = subprocess.run(["git", "rev-parse", ref if ref != "worktree" else "HEAD"], cwd=corpus.ROOT, capture_output=True, text=True).stdout.strip()
    record = {"version": version, "ref": ref, "commit": commit, "measured": dt.date.today().isoformat(),
              "sets": sets, "reference_date": reference, "repos": {}}
    entries = [e for e in corpus.entries(manifest, sets) if not only or e["name"] in only]
    recs = {}
    for entry in entries:   # the timed half, strictly one at a time: nothing else may run while a release is being timed
        print(f"measure: {version} {entry['name']}", file=sys.stderr, flush=True)
        try:
            recs[entry["name"]] = harness.run_entry(src, entry, root, reference)
        except Exception as e:   # the harness failing is not the release failing: record it and go on
            recs[entry["name"]] = _error(e)
    # the untimed half, side by side, the entry with the longest run first so the round ends when the biggest ranking does
    pending = [e for e in entries if recs[e["name"]].get("status") != "harness-error"]
    pending.sort(key=lambda e: -(recs[e["name"]].get("seconds") or 0))
    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        futures = {}
        for entry in pending:
            print(f"rank: {version} {entry['name']}", file=sys.stderr, flush=True)
            futures[entry["name"]] = pool.submit(harness.rank_entry, src, entry, root, reference, recs[entry["name"]], _labels_dir())
        for name, future in futures.items():
            try:
                recs[name] = future.result()
            except Exception as e:
                recs[name] = _error(e)
    for entry in entries:
        rec = recs[entry["name"]]
        rec["set"] = entry["set"]
        record["repos"][entry["name"]] = rec
    record["summary"] = dashboard.summarise(record)
    return record


def positives_table(record: dict, sets: list) -> str:
    """dashboard.positive_shares as Markdown: one row per cut-off, oldest first, the median then each repository."""
    shares = dashboard.positive_shares(record, sets)
    names = sorted({n for c in shares for n in c["repos"]})
    out = [f"Share of the pool in the outcome per cut-off, {record['version']}, {', '.join(sets)} (oldest first)", "",
           "| cut-off | median | " + " | ".join(names) + " |", "|---:|---:|" + "---:|" * len(names)]
    for c in shares:
        cells = ["-" if c["repos"].get(n) is None else f"{c['repos'][n]:.2f}" for n in names]
        out.append(f"| {c['index'] + 1} | {c['median']:.2f} | " + " | ".join(cells) + " |")
    return "\n".join(out)


def write(record: dict, directory: str = RECORDS) -> str:
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, f"{record['version']}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=1, sort_keys=True)
        fh.write("\n")
    return path


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m gitmole.measure", description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run")
    r.add_argument("--ref", action="append", default=[], help="a release tag, or worktree (default)")
    r.add_argument("--sets", default=None, help=f"comma-separated (default: {DEFAULT_SETS}, the fast loop)")
    r.add_argument("--release", action="store_true", help=f"a release round's sets: {RELEASE_SETS}")
    r.add_argument("--only", action="append", default=[], help="only these corpus entries")
    r.add_argument("--merge", action="store_true", help="add these runs to the release's existing record instead of replacing it")
    r.add_argument("--jobs", type=int, default=JOBS, help=f"rankings computed side by side after the timed runs (default {JOBS}; 1 is sequential)")
    x = sub.add_parser("extras")
    x.add_argument("--release", action="store_true", help="include the large set, as a release round does")
    sub.add_parser("report")
    cl = sub.add_parser("claims", help="check a round's findings against their own numbers, without measuring again")
    cl.add_argument("--version", action="append", default=[], help="a release already run (default: the latest recorded)")
    co = sub.add_parser("consistency", help="check a round's findings against each other and the facts the runs collected")
    co.add_argument("--version", default=None, help="a release already run (default: the latest recorded)")
    co.add_argument("--rerender", action="store_true",
                    help="judge this tree's rules instead: re-render each saved analysis with --no-run first (no collection)")
    co.add_argument("--only", action="append", default=[], help="only these corpus entries")
    po = sub.add_parser("positives", help="the snoring control: each cut-off's share of the pool in the outcome, from a recorded round")
    po.add_argument("--version", default=None, help="a recorded release (default: the latest recorded)")
    po.add_argument("--sets", default="development", help="comma-separated, of development, large, well-kept (the holdout is not read here)")
    lab = sub.add_parser("labels")
    lab.add_argument("action", choices=["dump", "score"])
    args = p.parse_args(argv)
    try:
        sets = resolve_sets(args.sets, args.release) if args.command == "run" else None
    except ValueError as e:
        p.error(str(e))
    manifest = corpus.load()
    root = corpus.workspace()
    if args.command == "run":
        for ref in args.ref or ["worktree"]:
            record = measure(ref, sets, manifest, root, set(args.only) or None, args.jobs)
            existing = os.path.join(RECORDS, f"{record['version']}.json")
            if args.merge and os.path.exists(existing):
                with open(existing, encoding="utf-8") as fh:
                    old = json.load(fh)
                old["repos"].update(record["repos"])
                old["sets"] = sorted(set(old.get("sets") or []) | set(record["sets"]))
                old["summary"] = dashboard.summarise(old)
                record = old
            print(write(record))
        return 0
    if args.command == "claims":
        from . import claims
        versions = args.version or [dashboard.load_history(RECORDS)[-1]["version"]]
        for version in versions:
            total = {"checked": 0, "clean": 0, "advisory": 0}
            complaints = []
            for path in sorted(glob.glob(os.path.join(root, "runs", version, "*", "report.json"))):
                name = os.path.basename(os.path.dirname(path))
                try:
                    with open(path, encoding="utf-8") as fh:
                        found = (json.load(fh) or {}).get("findings") or []
                except (OSError, ValueError):
                    continue
                one = claims.over(found)
                for key in total:
                    total[key] += one[key]
                complaints += [(name, c["rule"], c["kind"]) for c in one["complaints"]]
            print(f"{version}: {total['clean']} of {total['checked']} findings agree with their own numbers"
                  f" ({total['advisory']} advisory)")
            for name, rule, kind in complaints:
                print(f"  {name}/{rule}: {kind}")
        return 0
    if args.command == "consistency":
        from . import consistency
        version = args.version or dashboard.load_history(RECORDS)[-1]["version"]
        return consistency.round_(manifest, root, version, rerender=args.rerender, only=set(args.only) or None)
    if args.command == "positives":
        sets = args.sets.split(",")
        if not set(sets) <= set(dashboard.RANKED):
            p.error(f"--sets takes {', '.join(dashboard.RANKED)}: the holdout is read only by a release-tag job")
        history = dashboard.load_history(RECORDS)
        record = next((r for r in history if r["version"] == args.version), None) if args.version else history[-1]
        if record is None:
            print(f"positives: no record for {args.version}", file=sys.stderr)
            return 2
        print(positives_table(record, sets))
        return 0
    if args.command == "extras":
        from . import extras
        print(write(extras.run_all(manifest, root, release=args.release), os.path.join(RECORDS, "extras")))
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

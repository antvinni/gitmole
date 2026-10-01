"""python -m gitmole.measure: the measurement harness of docs/measurement.md.

    python -m gitmole.measure run [--ref REF]... [--sets development,awkward,gate | --release] [--[no-]remediation]   # one or more releases
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
import time
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


def last_asked(version: str, directory: str = RECORDS):
    """The latest record before `version` that carries remediation's table (its summary's `rules`): the
    point a release round's trigger diffs from. A record that did not ask is skipped, so a run of
    unchanged releases still compares with the one whose numbers stand."""
    try:
        history = dashboard.load_history(directory)
    except OSError:
        return None
    earlier = [r for r in history if dashboard._key(r.get("version", "0")) < dashboard._key(version)
               and isinstance((r.get("summary") or {}).get("remediation"), dict) and r["summary"]["remediation"].get("rules") is not None]
    return earlier[-1] if earlier else None


def remediation_decision(remediation, ref: str, commit: str, version: str, directory: str = RECORDS) -> dict:
    """Whether this round asks remediation's question: {"asked", "reason", "changed"}. `remediation` is
    True (--remediation: always), False (not asked, nothing recorded: the fast loop), "off"
    (--no-remediation: not asked, and said so) or "auto" (--release: asked when a path in
    remediation.ASKED_WHEN_CHANGED changed since the last record that asked it)."""
    from . import remediation as rem
    if remediation is True:
        return {"asked": True, "reason": "--remediation", "changed": []}
    if remediation == "off":
        return {"asked": False, "reason": "--no-remediation", "changed": []}
    if remediation != "auto":
        return {"asked": False, "reason": None, "changed": []}
    asked, reason, changed = rem.asked_since(corpus.ROOT, last_asked(version, directory), None if ref == "worktree" else commit)
    return {"asked": asked, "reason": reason, "changed": changed}


def measure(ref: str, sets: list, manifest: dict, root: str, only=None, jobs: int = JOBS, remediation=False) -> dict:
    """One release over the sets. With `remediation` asked (remediation_decision), the untimed half also
    asks remediation's question at each ranking cut-off of the development entries: a release run per
    cut-off, the round's largest added cost, so the fast loop leaves it out, and a release round asks it
    only when what it depends on changed."""
    awake = harness.keep_awake()
    started, wall = time.monotonic(), time.time()
    power = harness.power_source()
    src = harness.source(ref, root)
    version = harness.version_of(src)
    reference = manifest["reference_date"]
    commit = subprocess.run(["git", "rev-parse", ref if ref != "worktree" else "HEAD"], cwd=corpus.ROOT, capture_output=True, text=True).stdout.strip()
    record = {"version": version, "ref": ref, "commit": commit, "measured": dt.date.today().isoformat(),
              "sets": sets, "reference_date": reference, "repos": {}}
    decision = remediation_decision(remediation, ref, commit, version)
    if decision["reason"]:
        record["remediation_asked"] = decision
        print(f"remediation: {'asked' if decision['asked'] else 'not asked'} ({decision['reason']})", file=sys.stderr, flush=True)
    not_asked = None if decision["asked"] else decision["reason"]
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
            futures[entry["name"]] = pool.submit(harness.rank_entry, src, entry, root, reference, recs[entry["name"]], _labels_dir(),
                                                      decision["asked"], not_asked)
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
    record["round"] = round_times(record["repos"], time.monotonic() - started, time.time() - wall, power, awake)
    return record


def round_times(repos: dict, monotonic: float, wall: float, power, awake: str) -> dict:
    """The round's own clock: its wall seconds, and how much of them the machine slept, as the gap between
    the wall clock and the monotonic one (which stops in sleep), over the whole round and inside the timed
    runs alone. A timed run's `seconds` excludes a sleep; its neighbours' load and caches may not."""
    timed = [r["wall_seconds"] - r["seconds"] for r in repos.values()
             if isinstance(r.get("wall_seconds"), (int, float)) and isinstance(r.get("seconds"), (int, float))]
    return {"wall_seconds": round(wall, 1), "slept_seconds": round(max(0.0, wall - monotonic), 1),
            "timed_slept_seconds": round(sum(max(0.0, g) for g in timed), 1), "power": power, "awake": awake}


def merge_round(old, new: dict) -> dict:
    """--merge adds a round's runs to an earlier one's record: their clocks add, and a power source or
    keep-awake that differed between them reads "mixed"."""
    if not old:
        return new
    out = {k: round((old.get(k) or 0) + (new.get(k) or 0), 1) for k in ("wall_seconds", "slept_seconds", "timed_slept_seconds")}
    for k in ("power", "awake"):
        out[k] = new.get(k) if old.get(k) == new.get(k) else "mixed"
    return out


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
    asks = r.add_mutually_exclusive_group()
    asks.add_argument("--remediation", action="store_true",
                      help="ask remediation's question at the ranking cut-offs (development set), whatever changed")
    asks.add_argument("--no-remediation", action="store_true",
                      help="with --release: do not ask it, and record that it was not asked")
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
        harness.keep_awake()   # before the first ref is extracted; held until this process exits
        for ref in args.ref or ["worktree"]:
            asked = True if args.remediation else ("off" if args.no_remediation else "auto") if args.release else False
            record = measure(ref, sets, manifest, root, set(args.only) or None, args.jobs, asked)
            existing = os.path.join(RECORDS, f"{record['version']}.json")
            if args.merge and os.path.exists(existing):
                with open(existing, encoding="utf-8") as fh:
                    old = json.load(fh)
                old["repos"].update(record["repos"])
                old["sets"] = sorted(set(old.get("sets") or []) | set(record["sets"]))
                old["summary"] = dashboard.summarise(old)
                old["round"] = merge_round(old.get("round"), record["round"])
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

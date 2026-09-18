"""Run under the MEASURED version's code (PYTHONPATH set to that release's source) to read its own view of
an output directory: `probe.py rank OUT` prints the version's watch-list ranking over its whole pool, the
lines of code each file had, and the files its bug-magnet rule names. Written against the interfaces
every release since 0.2.0 shares (load.load_report, watch.risks, the size table), and nothing newer, so
the harness can score any release the same way. Run as a script: it must not import the current tree."""
import json
import sys


def _report(out):
    from gitmole import load
    try:
        return load.load_report(out, nested=False)
    except TypeError:   # releases before the backtest sub-report had no `nested`
        return load.load_report(out)


def _files_of(finding):
    ev = finding.get("evidence") or {}
    out = []
    for item in ev.get("files") or []:
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, dict) and item.get("file"):
            out.append(item["file"])
    return out


def rank(out):
    from gitmole import watch
    report = _report(out)
    rows = watch.risks(report)
    size = report.get("size") or {}
    files = size.get("files") or {}
    lines = {p: (v.get("code", 0) if isinstance(v, dict) else 0) for p, v in files.items()}
    magnets = None
    try:
        from gitmole import findings
        rule = getattr(findings, "bug_magnets", None)
        if rule is not None:
            fired = rule(report)
            if all(_files_of(x) for x in fired):   # a release whose findings carry no evidence cannot say which files
                magnets = sorted({f for x in fired for f in _files_of(x)})
    except Exception as e:   # an old rule over a sub-report it was not written for: no answer, not a crash
        magnets = None
        print(f"probe: bug_magnets: {e}", file=sys.stderr)
    revisions = {r["entity"]: r["n-revs"] for r in report.get("revisions") or []}
    total = size.get("total_code")
    if total is None:
        total = sum(lines.values())
    return {"pool": [r["file"] for r in rows], "revs": {r["file"]: revisions.get(r["file"], r.get("revs", 0)) for r in rows},
            "lines": {r["file"]: lines.get(r["file"], 0) for r in rows}, "total_code": total, "magnets": magnets}


if __name__ == "__main__":
    command, out = sys.argv[1], sys.argv[2]
    if command != "rank":
        sys.exit(f"probe: unknown command {command}")
    json.dump(rank(out), sys.stdout)

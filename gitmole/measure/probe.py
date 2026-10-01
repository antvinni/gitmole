"""Run under the MEASURED version's code (PYTHONPATH set to that release's source) to read its own view of
an output directory: `probe.py rank OUT` prints the version's watch-list ranking over its whole pool, the
lines of code each file had, the files its bug-magnet rule names, and why each file outside the pool is
outside it. Written against the interfaces every release since 0.2.0 shares (load.load_report,
watch.risks, the size table), and nothing newer except the classifier, asked only where the release has
one, so the harness can score any release the same way. Run as a script: it must not import the current
tree."""
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


def _left_out(report, rows, revisions, files):
    """Every path the history before the cut-off or the tree at it names that the pool does not hold, with
    the first reason the release's own classifier gives (generated, vendored, test file, ...), else
    "changed fewer than twice" (the pool's floor of two revisions), else "left out" for a release whose
    classifier this probe cannot ask. The harness counts the outcome's files by these reasons; a file
    named by neither the history nor the tree was absent at the cut-off. None when the classifier cannot
    be built, so an old release records no account rather than a wrong one."""
    try:
        from gitmole import classify
        reason = classify.Classifier(report).reason
    except Exception as e:   # a release from before classify.py, or one whose classifier wants more than this report has
        print(f"probe: classifier: {e}", file=sys.stderr)
        return None
    pooled = {r["file"] for r in rows}
    out = {}
    for p in set(files) | set(revisions):
        if p in pooled:
            continue
        out[p] = reason(p) or ("not in the tree" if p not in files else "changed fewer than twice" if revisions.get(p, 0) < 2 else "left out")
    return out


def rank(out):
    from gitmole import watch
    report = _report(out)
    rows = watch.risks(report)
    size = report.get("size") or {}
    files = size.get("files") or {}
    lines = {p: (v.get("code", 0) if isinstance(v, dict) else 0) for p, v in files.items()}
    cplx = {p: (v.get("complexity", 0) if isinstance(v, dict) else 0) for p, v in files.items()}
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
            "lines": {r["file"]: lines.get(r["file"], 0) for r in rows}, "total_code": total, "magnets": magnets,
            # the second effort driver: a release whose size table carries no complexity reports None
            # rather than a budget built out of zeros, so the harness can tell the two apart
            "complexity": {r["file"]: cplx.get(r["file"], 0) for r in rows}, "total_complexity": sum(cplx.values()) or None,
            # why each file outside the pool is outside it, for the account of the outcome the score cannot credit
            "left_out": _left_out(report, rows, revisions, files)}


if __name__ == "__main__":
    command, out = sys.argv[1], sys.argv[2]
    if command != "rank":
        sys.exit(f"probe: unknown command {command}")
    json.dump(rank(out), sys.stdout)

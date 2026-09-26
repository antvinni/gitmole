"""The checks docs/measurement.md runs on the current release only, since they re-run rules or tools in
ways an old release cannot: threshold sensitivity, description (differential) checks, determinism across
time zones and locales, and the hook's coupling warning replayed over history. They read the outputs a
`run --ref worktree` left in the workspace, so run that first."""
from __future__ import annotations

import datetime as dt
import inspect
import json
import os
import shutil
import subprocess

from .. import blame, evaluate, findings, load, maat, sarif, signing, watch
from . import corpus, harness, metrics

FACTORS = (0.5, 0.75, 0.9, 1.1, 1.25, 1.5)


def _dev(manifest: dict, release: bool = False) -> list:
    """The repositories the extras read: the development set, and in a release round the large set too,
    so a fast loop never pays for the large ones. gitmole's own history is too short for them."""
    sets = ["development", "large"] if release else ["development"]
    return [e for e in corpus.entries(manifest, sets) if e["name"] != "gitmole"]


def determinism_pair(dev: list) -> list:
    """curl and django, the pair the determinism check has always run; curl and react where django did not run."""
    names = {e["name"] for e in dev}
    pair = ("curl", "django") if "django" in names else ("curl", "react")
    return [e for e in dev if e["name"] in pair]


def _out(root: str, version: str, name: str) -> str:
    return os.path.join(root, "runs", version, name, "out")


# --- threshold sensitivity --------------------------------------------------------------------

def _items(found: list) -> set:
    """What a rule's findings flag: the places SARIF would point at, or the title when there are none."""
    out = set()
    for f in found:
        places = sarif._places(f)
        if places:
            out |= {(f["rule"]["id"], p[0] or "", p[2] or "") for p in places}
        else:
            out.add((f["rule"]["id"], f.get("title", "")))
    return out


def _shifted(default, factor):
    if isinstance(default, int):
        return max(1, int(round(default * factor)))
    return round(default * factor, 4)


def sensitivity(reports: dict) -> list:
    """For every numeric keyword threshold of every rule: the findings it emits and the overlap of what
    they flag (Jaccard) against the shipped value, at 10, 25 and 50% either side, per repository."""
    rows = []
    for rule in findings.RULES:
        params = [(n, p.default) for n, p in inspect.signature(rule).parameters.items()
                  if n != "report" and isinstance(p.default, (int, float)) and not isinstance(p.default, bool)]
        base = {r: rule(rep) for r, rep in reports.items()}
        for name, default in params:
            row = {"rule": rule.__name__, "param": name, "default": default, "base": {r: len(v) for r, v in base.items()}, "shifts": {}}
            for factor in FACTORS:
                value = _shifted(default, factor)
                if value == default:
                    row["shifts"][str(factor)] = None   # an integer too small to move by this much
                    continue
                per = {}
                for r, rep in reports.items():
                    got = rule(rep, **{name: value})
                    a, b = _items(base[r]), _items(got)
                    per[r] = {"findings": len(got), "jaccard": metrics.jaccard(a, b)}
                row["shifts"][str(factor)] = {"value": value, "repos": per}
            row["verdict"] = _verdict(row)
            rows.append(row)
    return rows


def _verdict(row: dict) -> str:
    """flat: at 10% either side every repository keeps its count within a quarter and three quarters of
    what it flags; fragile: some repository's count halves or doubles, or under half of what it flags
    stays; moderate otherwise; silent when the rule fires on no repository at any setting."""
    near = [row["shifts"].get(k) for k in ("0.9", "1.1")]
    near = [s for s in near if s] or [row["shifts"].get(k) for k in ("0.75", "1.25") if row["shifts"].get(k)]
    if not near:
        return "untested"
    counts = [(row["base"][r], x["findings"], x["jaccard"]) for s in near for r, x in s["repos"].items()]
    if all(b == 0 and n == 0 for b, n, _ in counts):
        return "silent"
    fragile = any((b and (n >= 2 * b or n <= b / 2)) or (not b and n) or (j is not None and j < 0.5) for b, n, j in counts)
    flat = all((b == n or (b and 0.75 <= n / b <= 1.25)) and (j is None or j >= 0.75) for b, n, j in counts)
    return "fragile" if fragile else "flat" if flat else "moderate"


# --- description checks ----------------------------------------------------------------------

def _line_count(path: str):
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError:
        return None
    return data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0)


# A difference found and traced to a definition rather than a bug, keyed by the check: filled in only
# after the difference has been looked at, so an unexplained difference stays visible until then.
EXPLANATIONS = {}


def describe(clone: str, out: str) -> list:
    """Count what the report counts a second way and list each comparison; `explained` names the
    definition that accounts for a known difference, and an unexplained difference is a bug to find."""
    checks = []
    meta = json.load(open(os.path.join(out, "meta.json"), encoding="utf-8"))
    head = int(subprocess.run(["git", "rev-list", "--count", "HEAD"], cwd=clone, capture_output=True, text=True).stdout.strip() or 0)
    checks.append({"check": "commits in the history", "gitmole": meta.get("commits"), "second": head, "second_by": "git rev-list --count HEAD"})
    with open(os.path.join(out, "size.json"), encoding="utf-8") as fh:
        langs = json.load(fh)
    differ, total = [], 0
    for lang in langs:
        for f in lang.get("Files") or []:
            total += 1
            n = _line_count(os.path.join(clone, f["Location"]))
            if n is not None and n != f["Lines"]:
                differ.append(f["Location"])
    checks.append({"check": "lines per file", "gitmole": total, "second": total - len(differ), "second_by": "newlines counted in each file scc measured",
                   "differ": sorted(differ)[:20], "differ_count": len(differ)})
    cov = meta.get("coverage") or {}
    texts = len(blame.text_files(clone))
    checks.append({"check": "tracked text files classified", "gitmole": sum(cov.values()), "second": texts, "second_by": "git grep -I (tracked, not binary)"})
    shas = subprocess.run(["git", "log", "HEAD", "-n", "200", "--format=%H"], cwd=clone, capture_output=True, text=True).stdout.split()
    ours = len(signing._signatures(clone, shas))
    program = subprocess.run(["git", "config", "--get", "gpg.program"], cwd=clone, capture_output=True, text=True).stdout.strip() or "gpg"
    if shutil.which(program):   # without gpg, git reports every commit as unsigned: no second count to compare
        theirs = sum(1 for g in subprocess.run(["git", "log", "HEAD", "-n", "200", "--format=%G?"], cwd=clone, capture_output=True, text=True).stdout.split() if g != "N")
        checks.append({"check": "signed commits among the last 200", "gitmole": ours, "second": theirs, "second_by": "git log --format=%G?"})
    else:
        checks.append({"check": "signed commits among the last 200", "gitmole": ours, "second": None, "second_by": f"git log --format=%G? (unavailable: {program} is not installed)", "unavailable": True})
    for c in checks:
        if c.get("unavailable"):
            c["agree"] = None
            continue
        c["agree"] = c["gitmole"] == c["second"]
        if not c["agree"]:
            c["explained"] = EXPLANATIONS.get(c["check"])
    return checks


# --- determinism ------------------------------------------------------------------------------

VARIANTS = [{"TZ": "UTC", "LC_ALL": "C"}, {"TZ": "Asia/Tokyo", "LC_ALL": "en_US.UTF-8"}]


def determinism(src: str, entries: list, root: str, reference: str) -> list:
    """The --json export of the same clone under two time zones and locales, compared outside its envelope."""
    rows = []
    for e in entries:
        clone = corpus.clone(e, root)
        exports = []
        for i, env in enumerate(VARIANTS):
            rec = harness.run_release(src, clone, os.path.join(root, "determinism", e["name"], str(i)), reference, env_extra=env)
            try:
                with open(os.path.join(root, "determinism", e["name"], str(i), "report.json"), encoding="utf-8") as fh:
                    data = json.load(fh)
                data.pop("envelope", None)
                exports.append(json.dumps(data, sort_keys=True))
            except (OSError, ValueError):
                exports.append(None)
            if rec["status"] != "ok":
                exports[-1] = None
        rows.append({"repo": e["name"], "variants": VARIANTS, "identical": exports[0] is not None and exports[0] == exports[1]})
    return rows


# --- the hook replay --------------------------------------------------------------------------

def hook_anchors(clone: str, cache: str, out: str, anchors: int = 3, window_months: int = 2):
    """For each anchor date, six months apart, oldest first: the report at the anchor (its coupling table
    from the history before it), the history the companion table is computed from, and the commits of
    the `window_months` after it that are the queries. Shared by the replay at the shipped thresholds
    and by the sweep, so both judge the same commits."""
    commits = harness.canonical_log(clone, cache)
    os.makedirs(out, exist_ok=True)
    last = max(c["date"] for c in commits)[:10]
    for k in range(anchors, 0, -1):
        t = maat.months_before(last, 6 * k)
        rev = subprocess.run(["git", "rev-list", "-1", f"--before={t}T00:00:00+00:00", "HEAD"], cwd=clone, capture_output=True, text=True).stdout.strip()
        if not rev:
            continue
        from .. import backtest
        size_json, generated, vendored = backtest.snapshot_at(clone, rev, out)
        report = evaluate.report_at(commits, t, load.parse_scc(size_json, None), {"bots": []}, generated, vendored)
        history = maat.analysed(maat.in_window(commits, until=t))
        report["coupling"] = maat.coupling(history)
        yield report, history, list(maat.in_window(commits, t, evaluate.months_after(t, window_months)))


def replay(report: dict, ranked: list, window: list, counts: dict = None, max_files: int = 20, top: int = 3) -> dict:
    """Zimmermann et al.'s two experiments over one window of commits, added into `counts`. Error
    prevention: leave one file out of each commit touching two to `max_files` scored files and see
    whether the warning names it — precision is correct over warned, recall correct over queries (each
    query expects exactly one file), feedback warned over queries, and top-`top` likelihood how often the
    file is among the first `top` companions named. Closure: a complete commit, where any warning is a
    false alarm."""
    c = counts if counts is not None else {"queries": 0, "warned": 0, "correct": 0, "top": 0, "complete_commits": 0, "closure_alarms": 0}
    pool = {r["file"] for r in ranked}
    for commit in window:
        files = sorted({p for p, _, _ in commit["files"] if p in pool})
        if not 2 <= len(files) <= max_files:
            continue
        c["complete_commits"] += 1
        if gaps_of(ranked, files):
            c["closure_alarms"] += 1
        for f in files:
            c["queries"] += 1
            named = gaps_of(ranked, [x for x in files if x != f])
            if named:
                c["warned"] += 1
                c["correct"] += f in named
                c["top"] += f in named[:top]
    return c


def gaps_of(ranked: list, files: list) -> list:
    """The companions the hook would name for a change touching `files`, surest first: exactly
    watch.change_risk's coupling_gaps read off the scored rows, without rebuilding the change view
    per query (a test holds the two equal)."""
    touched = set(files)
    by_file = {r["file"]: r for r in ranked}
    gaps = [(other, degree, f) for f in files if f in by_file for other, degree in by_file[f]["companions"] if other not in touched]
    gaps.sort(key=lambda g: (-g[1], g[2], g[0]))
    return [other for other, _, _ in gaps]


def rates(c: dict) -> dict:
    """The counts and the four rates Zimmermann reports, plus the closure false alarm rate."""
    q, w, full = c["queries"], c["warned"], c["complete_commits"]
    return {**c, "precision": round(c["correct"] / w, 3) if w else None, "recall": round(c["correct"] / q, 3) if q else None,
            "top3": round(c["top"] / q, 3) if q else None, "feedback": round(w / q, 3) if q else None,
            "closure_false_alarm_rate": round(c["closure_alarms"] / full, 3) if full else None}


def hook_replay(clone: str, cache: str, out: str, anchors: int = 3, window_months: int = 2, max_files: int = 20) -> dict:
    """The two experiments at the shipped thresholds (maat.companions' defaults), over three anchors six
    months apart with the two months after each as queries, the history strictly before each commit
    approximated at anchor granularity."""
    counts = None
    for report, history, window in hook_anchors(clone, cache, out, anchors, window_months):
        report["companions"] = maat.companions(history)
        counts = replay(report, watch.risks(report), window, counts, max_files)
    return rates(counts or {"queries": 0, "warned": 0, "correct": 0, "top": 0, "complete_commits": 0, "closure_alarms": 0})


def run_all(manifest: dict, root: str, release: bool = False) -> dict:
    src = harness.source("worktree", root)
    version = harness.version_of(src)
    reference = manifest["reference_date"]
    dev = _dev(manifest, release)
    reports = {}
    for e in dev:
        out = _out(root, version, e["name"])
        if os.path.isfile(os.path.join(out, "meta.json")):
            reports[e["name"]] = load.load_report(out)
    record = {"version": version, "measured": dt.date.today().isoformat(), "sets": ["development", "large"] if release else ["development"]}
    record["sensitivity"] = sensitivity(reports) if reports else None
    record["description"] = {e["name"]: describe(corpus.clone(e, root), _out(root, version, e["name"])) for e in dev if e["name"] in reports}
    record["hook"] = {e["name"]: hook_replay(corpus.clone(e, root), os.path.join(root, "logs", e["name"] + ".txt"), os.path.join(root, "hook", e["name"]))
                      for e in dev}
    record["determinism"] = determinism(src, determinism_pair(dev), root, reference)
    return record

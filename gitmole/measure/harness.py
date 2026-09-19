"""Run one release of gitmole over one corpus entry and measure it.

A release is its own source, extracted with `git archive` (or the working tree), run with the same
interpreter under PYTHONPATH, so every release is judged by its own code. What a release produces is
then scored by THIS tree's definitions, which stay fixed across the history: the outcome at a cut-off
is the current evaluate.fixed_between (or the corpus labels), over a change log exported the current way.
So a difference between two releases is a difference in the releases, not in the yardstick."""
from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time

from .. import evaluate, maat, run, szz
from . import corpus, metrics

HERE = os.path.dirname(os.path.realpath(__file__))
TOP = 15
HORIZON = 6
WINDOWS = 6
STABILITY_COMMITS = 50
MAIN_TIMEOUT = 3600
FIXTURE_TIMEOUT = 600


def source(ref: str, root: str) -> str:
    """The release's source tree: `worktree` is this checkout, anything else a git ref extracted once."""
    if ref == "worktree":
        return corpus.ROOT
    dest = os.path.join(root, "src", ref)
    if not os.path.isfile(os.path.join(dest, "gitmole", "__init__.py")):
        os.makedirs(dest, exist_ok=True)
        archive = subprocess.run(["git", "archive", ref], cwd=corpus.ROOT, check=True, capture_output=True).stdout
        subprocess.run(["tar", "-x", "-C", dest], input=archive, check=True)
    return dest


def version_of(src: str) -> str:
    with open(os.path.join(src, "gitmole", "__init__.py"), encoding="utf-8") as fh:
        m = re.search(r'__version__\s*=\s*"([^"]+)"', fh.read())
    return m.group(1) if m else "unknown"


def _spawn(argv: list, cwd: str, env: dict, stdout, stderr, timeout: float) -> str:
    """Run in its own process group; 'timeout' when it had to be killed, else None."""
    proc = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr, start_new_session=True)
    try:
        proc.wait(timeout=timeout)
        return None
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait()
        return "timeout"


def _env(src: str, reference: str, extra: dict = None) -> dict:
    env = dict(os.environ, PYTHONPATH=src, GITMOLE_NOW=reference, COLUMNS="100", TERM="dumb", NO_COLOR="1", PYTHONDONTWRITEBYTECODE="1")
    env.update(extra or {})
    return env


def run_release(src: str, clone: str, work: str, reference: str, fail_on: bool = False, timeout: float = MAIN_TIMEOUT, env_extra: dict = None) -> dict:
    """One ordinary run of the release on the clone: `gitmole CLONE --out OUT --json REPORT`, timed and
    measured. Returns status (ok, refused, crashed, timeout), the note, the files it left."""
    if os.path.isdir(work):
        shutil.rmtree(work)
    os.makedirs(work)
    out, report, stats = os.path.join(work, "out"), os.path.join(work, "report.json"), os.path.join(work, "stats.json")
    argv = [sys.executable, os.path.join(HERE, "wrap.py"), stats, "--", sys.executable, "-m", "gitmole", clone, "--out", out, "--json", report]
    if fail_on:
        argv += ["--fail-on", "critical"]
    with open(os.path.join(work, "stdout.txt"), "w") as so, open(os.path.join(work, "stderr.txt"), "w") as se:
        load = os.getloadavg()[0]
        killed = _spawn(argv, src, _env(src, reference, env_extra), so, se, timeout)
    with open(os.path.join(work, "stderr.txt"), encoding="utf-8", errors="replace") as fh:
        err = fh.read()
    st = {}
    if os.path.exists(stats):
        with open(stats) as fh:
            st = json.load(fh)
    rc = st.get("rc")
    rec = {"rc": rc, "seconds": st.get("seconds"), "peak_mb": st.get("peak_mb"), "load": round(load, 2), "out": out, "report": report}
    if killed:
        rec.update(status="timeout", note=f"killed after {timeout:.0f}s")
    elif "Traceback (most recent call last)" in err:
        last = [l for l in err.strip().split("\n") if l.strip()][-1]
        rec.update(status="crashed", note=last[:200])
    elif rc in (0, 3) and os.path.exists(report):
        rec.update(status="ok")
        if fail_on:
            rec["gate_fired"] = rc == 3
    elif rc == 2:
        last = [l for l in err.strip().split("\n") if l.strip()]
        rec.update(status="refused", note=(last[-1] if last else "exit 2")[:200])
    else:
        last = [l for l in err.strip().split("\n") if l.strip()]
        rec.update(status="crashed", note=(last[-1] if last else f"exit {rc}")[:200])
    with open(os.path.join(work, "stdout.txt"), encoding="utf-8", errors="replace") as fh:
        rec["report_lines"] = sum(1 for _ in fh)
    return rec


def read_outputs(rec: dict) -> dict:
    """What the run's own files say: findings by severity and rule, step statuses and timings, coverage."""
    out = {}
    try:
        with open(rec["report"], encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return out
    found = data.get("findings") or []
    out["findings"] = len(found)
    out["severity"] = {s: sum(1 for f in found if f.get("severity") == s) for s in ("critical", "warning", "info")}
    out["rules"] = sorted({(f.get("rule") or {}).get("id") or f.get("title", "") for f in found})
    meta = data.get("meta") or {}
    steps = meta.get("steps")
    if isinstance(steps, dict):
        out["steps"] = steps
        out["steps_failed"] = sorted(k for k, v in steps.items() if v in ("failed", "timeout"))
    env = data.get("envelope") or {}
    if env.get("step_seconds"):
        out["step_seconds"] = env["step_seconds"]
    if env.get("step_peak_mb"):
        out["step_peak_mb"] = env["step_peak_mb"]
    cov = meta.get("coverage")
    if isinstance(cov, dict) and cov:
        total = sum(v for v in cov.values() if isinstance(v, (int, float)))
        out["scored_share"] = round(cov.get("scored", 0) / total, 4) if total else None
    return out


# --- the ranking at cut-offs ------------------------------------------------------------------

def canonical_log(clone: str, cache: str) -> list:
    """The clone's change log exported the current way and parsed by the current maat: the fixed
    yardstick every release is scored against."""
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    if not os.path.exists(cache):
        text = subprocess.run(["git", "-c", "core.quotePath=false", "log", "HEAD", "--use-mailmap", "--numstat", "--date=iso-strict",
                               f"--pretty=format:{run.LOG_FORMAT}", "-M", "-w", "--ignore-blank-lines"],
                              cwd=clone, check=True, capture_output=True).stdout.decode("utf-8", "replace")
        with open(cache, "w", encoding="utf-8") as fh:
            fh.write(text)
    with open(cache, encoding="utf-8", newline="") as fh:
        return maat.parse_log(fh.read())


def ranking_at(src: str, clone: str, out: str, until: str, reference: str) -> dict:
    """The release's own ranking at `until`: its backtest rebuilds the report from the commits before
    that date, and the probe reads it with the release's own watch.risks."""
    env = _env(src, reference)
    proc = subprocess.run([sys.executable, "-m", "gitmole.backtest", out, "--until", until, "--repo", clone], cwd=src, env=env, capture_output=True, timeout=1800)
    if proc.returncode != 0:
        return {"error": (proc.stderr.decode("utf-8", "replace").strip().split("\n") or ["backtest failed"])[-1][:200]}
    probe = subprocess.run([sys.executable, os.path.join(HERE, "probe.py"), "rank", os.path.join(out, "backtest")], cwd=src, env=env, capture_output=True, timeout=900)
    if probe.returncode != 0:
        return {"error": (probe.stderr.decode("utf-8", "replace").strip().split("\n") or ["probe failed"])[-1][:200]}
    return json.loads(probe.stdout.decode("utf-8"))


def score(rank: dict, outcome: set, top: int = TOP) -> dict:
    """One cut-off: the list's hits against what random and perfect would do, the churn baseline over
    the same pool, ROC-AUC over the whole ordering, and recall at 20% of the codebase's lines."""
    pool = rank["pool"]
    positives = outcome.intersection(pool)
    churn = sorted(pool, key=lambda f: (-rank["revs"].get(f, 0), f))
    h, ch = metrics.hits(pool, positives, top), metrics.hits(churn, positives, top)
    exp, most = metrics.expected(len(pool), len(positives), top), metrics.best(len(pool), len(positives), top)
    return {"pool": len(pool), "positives": len(positives), "hits": h, "expected": round(exp, 3), "best": most, "churn_hits": ch,
            "auc": metrics.auc(pool, positives), "churn_auc": metrics.auc(churn, positives),
            "recall20": metrics.recall_at_effort(pool, rank["lines"], positives, total=rank.get("total_code")),
            "churn_recall20": metrics.recall_at_effort(churn, rank["lines"], positives, total=rank.get("total_code")),
            "top": pool[:top]}   # for the carry-over between consecutive cut-offs


def magnets_at(rank: dict, outcome: set) -> dict:
    """The findings backtest for bug magnets: of the files the rule named, how many were fixed again in
    the horizon, against unnamed files in the same deciles of the list's own score (the pool's order)."""
    named = set(rank.get("magnets") or [])
    pool = rank["pool"]
    if rank.get("magnets") is None or not pool:
        return None
    decile = {f: i * 10 // len(pool) for i, f in enumerate(pool)}
    used = {decile[f] for f in named if f in decile}
    matched = [f for f in pool if f not in named and decile[f] in used]
    return {"named": len(named), "named_fixed": len(named & outcome), "matched": len(matched), "matched_fixed": sum(f in outcome for f in matched)}


def rank_repo(src: str, entry: dict, clone: str, out: str, reference: str, cache: str, labels: dict = None) -> dict:
    """The six cut-offs, the stability pair and the findings backtest for one repository."""
    commits = canonical_log(clone, cache)
    if not commits:
        return {"cutoffs": []}
    last = entry.get("end") or max(c["date"] for c in commits)[:10]
    earliest = min(c["date"] for c in commits)[:10]
    rows, magnets = [], []
    for t in evaluate.cutoffs(last, WINDOWS, HORIZON):
        if t <= earliest:
            continue
        end = evaluate.months_after(t, HORIZON)
        rank = ranking_at(src, clone, out, t, reference)
        if "error" in rank:
            rows.append({"cutoff": t, "error": rank["error"]})
            continue
        outcome = evaluate.labelled_between(commits, labels, t, end) if labels is not None else evaluate.fixed_between(commits, t, end)
        rows.append({"cutoff": t, **score(rank, outcome)})
        m = magnets_at(rank, outcome)
        if m:
            magnets.append(m)
    stability = None
    ordered = sorted(commits, key=lambda c: (c["date"], c["hash"]))
    t0 = maat.months_before(last, HORIZON)
    after = [c for c in ordered if c["date"][:10] > t0]
    if len(after) > STABILITY_COMMITS and t0 > earliest:
        t1 = after[STABILITY_COMMITS - 1]["date"][:10]
        a, b = ranking_at(src, clone, out, t0, reference), ranking_at(src, clone, out, t1, reference)
        if "error" not in a and "error" not in b:
            stability = {"from": t0, "to": t1, "spearman": metrics.spearman(a["pool"], b["pool"]),
                         "top_jaccard": metrics.jaccard(a["pool"][:TOP], b["pool"][:TOP])}
    return {"cutoffs": rows, "stability": stability, "magnets": magnets}


def labels_for(entry: dict, manifest: dict, labels_dir: str):
    """The corpus labels an entry is scored against, or None for fix locality."""
    if entry.get("labels") != "apachejit":
        return None
    path = os.path.join(labels_dir, "apachejit_total.csv")
    return szz.read_labels(path) if os.path.exists(path) else None


def measure_entry(src: str, entry: dict, root: str, reference: str, labels_dir: str = None, env_extra: dict = None) -> dict:
    """Everything the history records for one release on one corpus entry."""
    clone = corpus.clone(entry, root)
    name = entry["name"]
    work = os.path.join(root, "runs", version_of(src), name)
    started = time.monotonic()
    rec = run_release(src, clone, work, reference, fail_on=entry["set"] == "gate",
                      timeout=FIXTURE_TIMEOUT if entry.get("fixture") else MAIN_TIMEOUT, env_extra=env_extra)
    rec.update(read_outputs(rec))
    if rec["status"] == "ok" and entry["set"] in ("development", "holdout") and not entry.get("fixture"):
        labels = labels_for(entry, None, labels_dir) if entry.get("labels") else None
        if entry.get("labels") and labels is None:
            rec["ranking"] = {"error": "labels not found"}
        else:
            rec["ranking"] = rank_repo(src, entry, clone, rec["out"], reference, os.path.join(root, "logs", name + ".txt"), labels)
    rec["measure_seconds"] = round(time.monotonic() - started, 1)
    for k in ("out", "report"):
        rec.pop(k, None)
    return rec

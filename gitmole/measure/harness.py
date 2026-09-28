"""Run one release of gitmole over one corpus entry and measure it.

A release is its own source, extracted with `git archive` (or the working tree), run with the same
interpreter under PYTHONPATH, so every release is judged by its own code. What a release produces is
then scored by THIS tree's definitions, which stay fixed across the history: the outcome at a cut-off
is the current evaluate.fixed_between (or the corpus labels), over a change log exported the current way.
So a difference between two releases is a difference in the releases, not in the yardstick."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time

from .. import evaluate, maat, run, szz
from . import claims, consistency, corpus, metrics
from . import labels as hand_labels   # `labels` is the ApacheJIT dict below

HERE = os.path.dirname(os.path.realpath(__file__))
TOP = 15
HORIZON = 6
WINDOWS = 6
STABILITY_COMMITS = 50
MAIN_TIMEOUT = 3600
FIXTURE_TIMEOUT = 600


def rev_at(repo: str, date: str):
    """The harness's "tree as of `date`": the last commit on HEAD's first-parent chain dated up to the
    start of the day (git's --before is inclusive, so a commit stamped exactly T00:00:00 counts; the
    day's other commits belong to the future being scored), or None when the history starts later.
    First parents only, since by date alone a side branch merged afterwards, or a history merged in
    whole (the React Compiler's inside react), can carry the latest commit before the date. The pinned
    corpus clones check their commit out on a `measure` branch, so HEAD's chain is the pin's.

    The same choice as the product's trend.rev_before (end_of_day=False), which the release's backtest
    and so ranking_at use, so the harness has one definition of the tree at a cut-off.

    Raises RuntimeError with git's own message when git fails: an unreadable repository is not the same
    answer as a history that does not reach back that far."""
    proc = subprocess.run(["git", "rev-list", "-1", "--first-parent", f"--before={date}T00:00:00+00:00", "HEAD"],
                          cwd=repo, capture_output=True, text=True)
    if proc.returncode != 0:
        err = (proc.stderr or "").strip().splitlines()
        raise RuntimeError(err[0] if err else f"git rev-list --first-parent --before={date} exited {proc.returncode}")
    return proc.stdout.strip() or None


SOURCE_STAMP = ".gitmole-source-commit"


def source(ref: str, root: str) -> str:
    """The release's source tree: `worktree` is this checkout, anything else a git ref extracted into
    src/<ref>. The commit it was extracted from is stamped beside it, and a ref that has since moved (a
    branch, where a tag never does) is extracted again, so a candidate is never judged on stale source."""
    if ref == "worktree":
        return corpus.ROOT
    commit = subprocess.run(["git", "rev-parse", "--verify", ref + "^{commit}"], cwd=corpus.ROOT, check=True,
                            capture_output=True, text=True).stdout.strip()
    dest = os.path.join(root, "src", ref)
    base = os.path.realpath(os.path.join(root, "src"))
    if not os.path.realpath(dest).startswith(base + os.sep):
        raise ValueError(f"ref {ref!r} would extract outside {base}")
    stamp = os.path.join(dest, SOURCE_STAMP)
    fresh = os.path.isfile(os.path.join(dest, "gitmole", "__init__.py")) and os.path.isfile(stamp) and open(stamp).read().strip() == commit
    if not fresh:
        shutil.rmtree(dest, ignore_errors=True)   # our own extraction under the workspace, never a checkout
        os.makedirs(dest, exist_ok=True)
        archive = subprocess.run(["git", "archive", commit], cwd=corpus.ROOT, check=True, capture_output=True).stdout
        subprocess.run(["tar", "-x", "-C", dest], input=archive, check=True)
        with open(stamp, "w") as fh:
            fh.write(commit + "\n")
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


# Variables that decide whether rich treats the report's stdout as a terminal. Every record from 0.2.0 to 0.30.0
# was made with a forced terminal (the banner printed, 80 columns, whatever COLUMNS says), so the harness sets that
# itself instead of inheriting it from whoever started the run: without it the same release prints 11 lines fewer.
_TTY_VARS = ("FORCE_COLOR", "TTY_COMPATIBLE", "TTY_INTERACTIVE", "CLICOLOR_FORCE")


def _env(src: str, reference: str, extra: dict = None) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in _TTY_VARS}
    env.update(PYTHONPATH=src, GITMOLE_NOW=reference, COLUMNS="100", TERM="dumb", NO_COLOR="1", PYTHONDONTWRITEBYTECODE="1", FORCE_COLOR="1")
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


def read_outputs(rec: dict, clone: str = None) -> dict:
    """What the run's own files say: findings by severity and rule, step statuses and timings, coverage,
    and whether the findings agree with the rest of the report (with `clone`, with git too)."""
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
    out["shown"] = sum(1 for f in found if not f.get("summary"))   # what the default report spells out
    out["claims"] = claims.over(found)   # does each finding's text agree with its own numbers
    one = consistency.over(data, clone)   # does it agree with the other findings and the facts the run collected
    out["consistency"] = {"checked": one["checked"], "clean": one["clean"], "by_check": consistency.by_check(one["complaints"]), "clone": one["clone"]}
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
    the same pool, ROC-AUC over the whole ordering, recall at 20% of the codebase's lines, Popt over
    the whole ordering, and the initial false alarms before the first file that was fixed."""
    pool = rank["pool"]
    positives = outcome.intersection(pool)
    churn = sorted(pool, key=lambda f: (-rank["revs"].get(f, 0), f))
    # ManualUp: the smallest file first. Fu and Menzies (FSE 2017) verify this is the model Yang et al.'s
    # twelve unsupervised predictors all generalise. A control, not a candidate — it takes a lines budget
    # by naming tiny files, which is exactly what its IFA beside it is for.
    manualup = sorted(pool, key=lambda f: (rank["lines"].get(f, 0), f))
    # size alone, the largest file first: the other simple list the watch list has to beat (validation.md)
    size = sorted(pool, key=lambda f: (-rank["lines"].get(f, 0), f))
    h, ch = metrics.hits(pool, positives, top), metrics.hits(churn, positives, top)
    # The 2025 effort-aware critique (arXiv 2504.19181): these measures are size-aware, and the verdict
    # can change when the effort driver is not lines. scc's per-file complexity is the second driver.
    cplx, cplx_total = rank.get("complexity") or {}, rank.get("total_complexity")

    def by_complexity(ordering):
        return metrics.recall_at_effort(ordering, cplx, positives, total=cplx_total) if cplx_total else None

    # Popt on a lines budget pays for cheap files as much as for order: its optimal ordering is the outcome's
    # files cheapest first, so a size-blind list gains on it the way ManualUp does. Three drivers, then: lines
    # (what the papers report), scc's complexity (the 2025 critique's alternative), and uniform cost, under
    # which Popt is a pure rank measure and so the size control. The false alarms are recorded uncapped too:
    # capped at the top, a list whose first hit is at rank 40 reads the same as one whose first hit is at 15.
    uniform = {f: 1 for f in pool}

    def popt_complexity(ordering):
        return metrics.popt(ordering, cplx, positives) if cplx_total else None

    exp, most = metrics.expected(len(pool), len(positives), top), metrics.best(len(pool), len(positives), top)
    return {"pool": len(pool), "positives": len(positives), "hits": h, "expected": round(exp, 3), "best": most, "churn_hits": ch,
            "auc": metrics.auc(pool, positives), "churn_auc": metrics.auc(churn, positives),
            "recall20": metrics.recall_at_effort(pool, rank["lines"], positives, total=rank.get("total_code")),
            "churn_recall20": metrics.recall_at_effort(churn, rank["lines"], positives, total=rank.get("total_code")),
            "popt": metrics.popt(pool, rank["lines"], positives),
            "churn_popt": metrics.popt(churn, rank["lines"], positives),
            "ifa": metrics.ifa(pool, positives, top),
            "churn_ifa": metrics.ifa(churn, positives, top),
            "manualup_hits": metrics.hits(manualup, positives, top),
            "manualup_auc": metrics.auc(manualup, positives),
            "manualup_recall20": metrics.recall_at_effort(manualup, rank["lines"], positives, total=rank.get("total_code")),
            "manualup_popt": metrics.popt(manualup, rank["lines"], positives),
            "manualup_ifa": metrics.ifa(manualup, positives, top),
            "recall20_complexity": by_complexity(pool),
            "churn_recall20_complexity": by_complexity(churn),
            "manualup_recall20_complexity": by_complexity(manualup),
            "popt_complexity": popt_complexity(pool), "churn_popt_complexity": popt_complexity(churn), "manualup_popt_complexity": popt_complexity(manualup),
            "popt_uniform": metrics.popt(pool, uniform, positives), "churn_popt_uniform": metrics.popt(churn, uniform, positives),
            "manualup_popt_uniform": metrics.popt(manualup, uniform, positives),
            "ifa_all": metrics.ifa(pool, positives), "churn_ifa_all": metrics.ifa(churn, positives), "manualup_ifa_all": metrics.ifa(manualup, positives),
            "size_hits": metrics.hits(size, positives, top), "size_auc": metrics.auc(size, positives),
            "size_recall20": metrics.recall_at_effort(size, rank["lines"], positives, total=rank.get("total_code")),
            "size_popt": metrics.popt(size, rank["lines"], positives), "size_ifa": metrics.ifa(size, positives, top),
            # the files scored, as a set: a candidate compared later is scored on this pool, and a pool that
            # has since moved (the classifier changed) is a different comparison, which the digest shows
            "pool_digest": hashlib.sha256("\n".join(sorted(pool)).encode("utf-8", "surrogateescape")).hexdigest()[:16],
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


def cutoff_windows(entry: dict, commits: list, labels: dict = None) -> list:
    """[(cut-off, outcome)] for one repository: the six cut-offs the history reaches back to, and the files
    fixed (or labelled) in the horizon after each. The releases' rankings and a candidate's comparison take
    their dates and outcomes from here, so the two cannot drift apart."""
    if not commits:
        return []
    last = entry.get("end") or max(c["date"] for c in commits)[:10]
    earliest = min(c["date"] for c in commits)[:10]
    out = []
    for t in evaluate.cutoffs(last, WINDOWS, HORIZON):
        if t <= earliest:
            continue
        end = evaluate.months_after(t, HORIZON)
        out.append((t, evaluate.labelled_between(commits, labels, t, end) if labels is not None else evaluate.fixed_between(commits, t, end)))
    return out


def rank_repo(src: str, entry: dict, clone: str, out: str, reference: str, cache: str, labels: dict = None) -> dict:
    """The six cut-offs, the stability pair and the findings backtest for one repository."""
    commits = canonical_log(clone, cache)
    if not commits:
        return {"cutoffs": []}
    last = entry.get("end") or max(c["date"] for c in commits)[:10]
    earliest = min(c["date"] for c in commits)[:10]
    rows, magnets = [], []
    for t, outcome in cutoff_windows(entry, commits, labels):
        rank = ranking_at(src, clone, out, t, reference)
        if "error" in rank:
            rows.append({"cutoff": t, "error": rank["error"]})
            continue
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


def run_entry(src: str, entry: dict, root: str, reference: str, env_extra: dict = None) -> dict:
    """The timed half of measuring one entry: the release run on the clone, and what its files say.
    Its wall time and peak memory are the record's, so it runs alone — never beside another run, and
    never beside anyone's ranking."""
    clone = corpus.clone(entry, root)
    work = os.path.join(root, "runs", version_of(src), entry["name"])
    started = time.monotonic()
    rec = run_release(src, clone, work, reference, fail_on=entry["set"] == "gate",
                      timeout=FIXTURE_TIMEOUT if entry.get("fixture") else MAIN_TIMEOUT, env_extra=env_extra)
    rec.update(read_outputs(rec, clone))
    rec["measure_seconds"] = round(time.monotonic() - started, 1)
    rec["clone"] = clone
    return rec


def needs_ranking(entry: dict, rec: dict) -> bool:
    return rec.get("status") == "ok" and entry["set"] in ("development", "large", "well-kept", "holdout") and not entry.get("fixture")


def rank_entry(src: str, entry: dict, root: str, reference: str, rec: dict, labels_dir: str = None) -> dict:
    """The untimed half: the ranking at cut-offs and the finding ids, read off the files the timed run
    left. Nothing here is measured, so entries' rankings may run side by side; each works in its own
    run directory and log cache."""
    name = entry["name"]
    started = time.monotonic()
    clone = rec.pop("clone", None) or corpus.clone(entry, root)
    if needs_ranking(entry, rec):
        labels = labels_for(entry, None, labels_dir) if entry.get("labels") else None
        if entry.get("labels") and labels is None:
            rec["ranking"] = {"error": "labels not found"}
        else:
            rec["ranking"] = rank_repo(src, entry, clone, rec["out"], reference, os.path.join(root, "logs", name + ".txt"), labels)
    if entry["set"] in hand_labels.LABELLED_SETS and rec.get("report"):   # for the actionable share, from the labels at report time
        rec["finding_ids"] = [{k: row[k] for k in ("id", "rule", "summary")} for row in hand_labels.id_rows(name, entry.get("commit"), rec["report"])]
    rec["measure_seconds"] = round((rec.get("measure_seconds") or 0) + time.monotonic() - started, 1)
    for k in ("out", "report"):
        rec.pop(k, None)
    return rec

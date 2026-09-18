#!/usr/bin/env python3
"""How the watch list would have done at several cut-off dates, next to the factor products it
replaced (computed here, over the rows watch.risks returns) and the simpler baselines.

A development tool, not a pipeline step: `python -m gitmole.evaluate REPO OUT_DIR [--windows 6]
[--horizon 6] [--top 15]`, where OUT_DIR is a finished gitmole output directory for REPO (its log.txt
and meta.json are read). For each cut-off T, counted back from the last commit in steps of `horizon`
months, the change analysis is rebuilt from the commits before T, scc measures the tree at T, every
variant names its `top` files, and the source files a fix commit touched in [T, T + horizon) are the
outcome. A fix is a commit whose subject says so (maat.is_fix): a proxy, not a bug tracker, and the
table is only as good as the repository's commit subjects. Prints Markdown: one row per variant, one
column per cut-off, and the total; then how many commits `--all` adds to HEAD's."""
from __future__ import annotations

import argparse
import bisect
import calendar
import datetime as dt
import os
import subprocess
import sys

from . import backtest, filetypes, identity, load, maat, szz, trend, watch


def cutoffs(last_date: str, windows: int, horizon: int) -> list:
    """The cut-off dates, oldest first: the last commit's date less one, two, ... horizons."""
    return sorted(maat.months_before(last_date, horizon * k) for k in range(1, windows + 1))


def months_after(date: str, months: int) -> str:
    """The ISO date `months` whole months after `date`, day clamped to the month's length."""
    d = dt.date.fromisoformat(date)
    years, month = divmod(d.month - 1 + months, 12)
    y, m = d.year + years, month + 1
    return dt.date(y, m, min(d.day, calendar.monthrange(y, m)[1])).isoformat()


def fixed_between(commits: list, start: str, end: str) -> set:
    """Source files a fix commit touched on or after `start` and before `end`. Test files change with
    every fix; an oversized fix (over the whole history's 99th percentile of lines) is tangled by size."""
    big = {c["hash"] for c in maat.oversized(commits)}
    return {p for c in maat.in_window(commits, start, end) if maat.is_fix(c.get("subject", "")) and c["hash"] not in big
            for p, _, _ in c["files"] if not filetypes.is_test_path(p)}


def induced_between(repo: str, commits: list, start: str, end: str, exclude=None) -> set:
    """Source files a commit before `start` made buggy, by R-SZZ over the fixes landing on or after
    `start` and before `end`: the outcome is defect insertion the list could have known about, not
    fix locality. A fix whose bug-inducing commit is inside the horizon is not counted, since no
    list drawn before `start` could have named it."""
    out = set()
    for c in maat.in_window(maat.fix_commits(commits), start, end):
        found = szz.bug_inducing(repo, c["hash"], exclude)
        if found and found["date"] < start:
            out.update(p for p in found["files"] if not filetypes.is_test_path(p))
    return out


def labelled_between(commits: list, labels: dict, start: str, end: str) -> set:
    """Source files an independently labelled bug-inducing commit touched on or after `start` and
    before `end` (ApacheJIT, Defectors: see szz.read_labels): the paths the label names, or every
    source file the commit touched. Either side may be abbreviated."""
    out = set()
    for c in maat.in_window(commits, start, end):
        paths = next((v for k, v in labels.items() if k.startswith(c["hash"]) or c["hash"].startswith(k)), "none")
        if paths == "none":
            continue
        out.update(p for p in (paths if paths is not None else [p for p, _, _ in c["files"]]) if not filetypes.is_test_path(p))
    return out


def report_at(commits: list, t: str, size: dict, meta: dict, generated: list, vendored: list, ignored: set = frozenset()) -> dict:
    """The report watch.risks reads, from the commits before `t` (less the sweeps and the declared, as
    the pipeline leaves them out), scc's listing of the tree at `t`, and that tree's own generated and
    vendored files (snapshot_at classified the cut-off, not HEAD). No coupling and no functions: neither
    enters the score, and the pipeline's own backtest has no functions either."""
    past = maat.analysed(maat.in_window(commits, until=t), ignored)
    bots = {b["name"] for b in meta.get("bots") or []}
    ownership = [r for r in maat.entity_ownership(past) if r["author"] not in bots and not identity.is_bot(r["author"])]
    return {"meta": {"now": t, "generated": generated, "vendored": vendored}, "size": size, "revisions": maat.revisions(past),
            "plumbing": maat.plumbing(past), "authors": maat.authors(past), "ownership": ownership,
            "fixes": maat.fixes(past, now=t), "coupling": [], "functions": [],
            "entropy": maat.entropy(past, now=t)}


SOLO_WEIGHT = 1.5       # how much single ownership lifts a factor product


def _by_max(values: list, inclusive: bool):
    """x as a share of the largest value: the scaling gitmole 0.7 shipped. One outlier moves everyone;
    inclusive is ignored here, since a share of the largest value has no edge to choose."""
    top = max(values)
    return lambda x: x / top if top else 0.0


def _by_rank(values: list, inclusive: bool):
    """x as the share of the scored files at or below it (inclusive), or strictly below it. Churn is
    inclusive, so the most-changed file is 1 and no file is 0; fixes and complexity are strict, so a
    file with none of either gets no lift, as under _by_max. An outlier is one more file, not a new
    scale."""
    ordered = sorted(values)
    cut = bisect.bisect_right if inclusive else bisect.bisect_left
    return lambda x: cut(ordered, x) / len(ordered)


SCALINGS = {"max": _by_max, "rank": _by_rank}


def factor_scores(rows: list, scaling: str) -> dict:
    """file -> churn × (1 + recent fixes) × (1 + complexity) × (1.5 if single-owned), what the watch
    list ranked by before 0.8, over the rows watch.risks returns. Kept here, not in watch.py, because
    only this comparison still needs it."""
    if not rows:
        return {}
    scale = SCALINGS[scaling]
    churn = scale([r["revs"] for r in rows], True)
    fixed = scale([r["recent_fixes"] for r in rows], False)
    cplx = scale([r["complexity"] for r in rows], False)
    return {r["file"]: churn(r["revs"]) * (1 + fixed(r["recent_fixes"])) * (1 + cplx(r["complexity"])) * (SOLO_WEIGHT if r["solo"] else 1)
            for r in rows}


def factor_product(rows: list, scaling: str) -> list:
    """File names by factor_scores, best first; ties by revisions, then by name, as the list itself breaks them."""
    scores = factor_scores(rows, scaling)
    return [r["file"] for r in sorted(rows, key=lambda r: (-scores[r["file"]], -r["revs"], r["file"]))]


def variants(report: dict) -> dict:
    """variant -> file names, best first, every one drawn from the pool the watch list draws from. The
    factor products it used to be ranked by are computed here, next to the watch list's own ranking."""
    rows = watch.risks(report)
    out = {"watch list (hotspot)": [r["file"] for r in rows],
           "factor product (max-scaled)": factor_product(rows, "max"),
           "factor product (rank-scaled)": factor_product(rows, "rank")}
    for name, key in watch.BASELINES.items():
        out[name] = watch.ranked_by(rows, key)
    out["recent fixes"] = watch.ranked_by(rows, lambda r: (r["recent_fixes"], r["revs"]))
    hcm = {e["entity"]: e["hcm"] for e in report.get("entropy") or []}
    out["change entropy (HCM)"] = watch.ranked_by(rows, lambda r: (hcm.get(r["file"], 0.0), r["revs"]))   # Hassan's decayed HCM, the one metric with published evidence of beating churn
    return out


def score(report: dict, fixed: set, top: int) -> dict:
    """variant -> how many of its first `top` files were fixed, plus what a random `top` of the pool would name."""
    lists = variants(report)
    pool = lists["churn"]
    out = {name: len(fixed.intersection(files[:top])) for name, files in lists.items()}
    out["random (expected)"] = round(min(top, len(pool)) * len(fixed.intersection(pool)) / len(pool), 1) if pool else 0.0
    return out


def table(results: list, noun: str = "fixed") -> str:
    """results: [(t, files fixed that were in the pool, pool size, {variant: hits})], oldest first -> Markdown.
    `noun` says what the outcome is: fixed, bug-inducing (R-SZZ) or labelled."""
    names = list(results[0][3]) if results else []
    head = "| variant | " + " | ".join(f"{t} ({fixed} of {pool} {noun})" for t, fixed, pool, _ in results) + " | total |"
    rule = "|---|" + "---:|" * (len(results) + 1)
    rows = []
    for name in names:
        cells = [hits[name] for _, _, _, hits in results]
        total = round(sum(cells), 1) if any(isinstance(c, float) for c in cells) else sum(cells)
        rows.append(f"| {name} | " + " | ".join(str(c) for c in cells) + f" | {total} |")
    return "\n".join([head, rule, *rows])


def ref_spread(repo: str) -> dict:
    """Commits and fix commits reachable from every ref (what `git log --all` exports: remote release
    branches with their backports, unmerged work, the stash) against those reachable from HEAD."""
    def subjects(*revs):
        out = subprocess.run([*filetypes.GIT, "log", *revs, "--format=%s"], cwd=repo, check=True, capture_output=True).stdout
        return out.decode("utf-8", "replace").split("\n")[:-1]
    everything, head = subjects("--all"), subjects("HEAD")
    return {"all": len(everything), "head": len(head), "fix_all": sum(map(maat.is_fix, everything)), "fix_head": sum(map(maat.is_fix, head))}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("repo")
    p.add_argument("out")
    p.add_argument("--windows", type=int, default=6)
    p.add_argument("--horizon", type=int, default=6, metavar="MONTHS")
    p.add_argument("--top", type=int, default=watch.WATCH_TOP)
    p.add_argument("--szz", action="store_true", help="also score against R-SZZ bug-inducing commits (one git blame per fix and file: minutes)")
    p.add_argument("--labels", metavar="CSV", help="also score against independent bug-inducing labels (ApacheJIT's CSV, Defectors' file rows, or one hash per line)")
    args = p.parse_args(argv)
    meta = load._read_json(args.out, "meta.json", {})
    log_path = os.path.join(args.out, "log.txt")
    if not meta.get("last_date") or not os.path.exists(log_path):
        print("evaluate: a finished output directory is needed (meta.json with last_date, and log.txt)", file=sys.stderr)
        return 2
    types = filetypes.parse(meta.get("file_types"))
    aliases = maat.aliases_from_meta(os.path.join(args.out, "meta.json")) if "aliases" in meta else None
    with open(log_path, encoding="utf-8", errors="replace", newline="") as fh:
        commits = maat.parse_log(fh.read(), aliases, types)
    from . import run
    declared = maat.read_ignore_revs(run.ignore_revs_files(args.repo))
    ignored = {c["hash"] for c in commits if declared and maat.is_ignored(c["hash"], declared)}
    labels = szz.read_labels(args.labels) if args.labels else None
    if args.labels and not labels:
        print(f"evaluate: no bug-inducing commits read from {args.labels}", file=sys.stderr)
        return 2
    results, induced_results, labelled_results = [], [], []
    for t in cutoffs(meta["last_date"], args.windows, args.horizon):
        rev = trend.rev_before(args.repo, t, end_of_day=False)
        if not rev:
            continue                      # the history does not reach back this far
        size_json, generated, vendored = backtest.snapshot_at(args.repo, rev, args.out)
        size = load.parse_scc(size_json, types)
        report = report_at(commits, t, size, meta, generated, vendored, ignored)
        end = months_after(t, args.horizon)
        fixed = fixed_between(commits, t, end)
        pool = set(variants(report)["churn"])
        results.append((t, len(fixed & pool), len(pool), score(report, fixed, args.top)))
        if args.szz:
            vendor = tuple(vendored)
            induced = induced_between(args.repo, commits, t, end, exclude=lambda p: p in generated or filetypes.is_vendored(p, vendor) or filetypes.is_sample_path(p))
            induced_results.append((t, len(induced & pool), len(pool), score(report, induced, args.top)))
        if labels:
            marked = labelled_between(commits, labels, t, end)
            labelled_results.append((t, len(marked & pool), len(pool), score(report, marked, args.top)))
        print(f"evaluate: {t} done", file=sys.stderr)
    if not results:
        print("evaluate: no cut-off falls inside the history", file=sys.stderr)
        return 2
    spread = ref_spread(args.repo)
    print(f"### {meta.get('name', args.repo)}, top {args.top}, {args.horizon}-month horizon\n")
    print(table(results))
    if induced_results:
        print(f"\nAgainst the files a commit before the cut-off made buggy, by R-SZZ over the fixes that followed (the most recent commit each fix's removed lines blame to):\n")
        print(table(induced_results, noun="bug-inducing"))
    if labelled_results:
        print(f"\nAgainst the files the bug-inducing commits labelled in {os.path.basename(args.labels)} touched inside each window:\n")
        print(table(labelled_results, noun="labelled"))
    print(f"\n`--all` exports {spread['all']:,} commits ({spread['fix_all']:,} fixes); HEAD reaches {spread['head']:,} ({spread['fix_head']:,} fixes).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

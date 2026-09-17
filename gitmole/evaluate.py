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

from . import backtest, filetypes, identity, load, maat, trend, watch


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
    """Source files a fix commit touched on or after `start` and before `end`. Test files change with every fix."""
    return {p for c in maat.in_window(commits, start, end) if maat.is_fix(c.get("subject", ""))
            for p, _, _ in c["files"] if not filetypes.is_test_path(p)}


def report_at(commits: list, t: str, size: dict, meta: dict) -> dict:
    """The report watch.risks reads, from the commits before `t` and scc's listing of the tree at `t`.
    No coupling and no functions: neither enters the score, and the pipeline's own backtest has no functions either."""
    past = maat.in_window(commits, until=t)
    bots = {b["name"] for b in meta.get("bots") or []}
    ownership = [r for r in maat.entity_ownership(past) if r["author"] not in bots and not identity.is_bot(r["author"])]
    return {"meta": {"now": t, "generated": meta.get("generated") or []}, "size": size, "revisions": maat.revisions(past),
            "plumbing": maat.plumbing(past), "authors": maat.authors(past), "ownership": ownership,
            "fixes": maat.fixes(past, now=t), "coupling": [], "functions": []}


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
    factor products it used to be ranked by are computed here, next to watch list's own ranking."""
    rows = watch.risks(report)
    out = {"watch list (hotspot)": [r["file"] for r in rows],
           "factor product (max-scaled)": factor_product(rows, "max"),
           "factor product (rank-scaled)": factor_product(rows, "rank")}
    for name, key in watch.BASELINES.items():
        out[name] = watch.ranked_by(rows, key)
    out["recent fixes"] = watch.ranked_by(rows, lambda r: (r["recent_fixes"], r["revs"]))
    return out


def score(report: dict, fixed: set, top: int) -> dict:
    """variant -> how many of its first `top` files were fixed, plus what a random `top` of the pool would name."""
    lists = variants(report)
    pool = lists["churn"]
    out = {name: len(fixed.intersection(files[:top])) for name, files in lists.items()}
    out["random (expected)"] = round(min(top, len(pool)) * len(fixed.intersection(pool)) / len(pool), 1) if pool else 0.0
    return out


def table(results: list) -> str:
    """results: [(t, files fixed that were in the pool, pool size, {variant: hits})], oldest first -> Markdown."""
    names = list(results[0][3]) if results else []
    head = "| variant | " + " | ".join(f"{t} ({fixed} of {pool} fixed)" for t, fixed, pool, _ in results) + " | total |"
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
    results = []
    for t in cutoffs(meta["last_date"], args.windows, args.horizon):
        rev = trend.rev_before(args.repo, t, end_of_day=False)
        if not rev:
            continue                      # the history does not reach back this far
        size = load.parse_scc(backtest.size_at(args.repo, rev, args.out), types)
        report = report_at(commits, t, size, meta)
        fixed = fixed_between(commits, t, months_after(t, args.horizon))
        pool = set(variants(report)["churn"])
        results.append((t, len(fixed & pool), len(pool), score(report, fixed, args.top)))
        print(f"evaluate: {t} done", file=sys.stderr)
    if not results:
        print("evaluate: no cut-off falls inside the history", file=sys.stderr)
        return 2
    spread = ref_spread(args.repo)
    print(f"### {meta.get('name', args.repo)}, top {args.top}, {args.horizon}-month horizon\n")
    print(table(results))
    print(f"\n`--all` exports {spread['all']:,} commits ({spread['fix_all']:,} fixes); HEAD reaches {spread['head']:,} ({spread['fix_head']:,} fixes).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

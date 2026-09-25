"""The hook's coupling warning swept over support and confidence, the way ROSE was evaluated
(Zimmermann et al., TSE 2005, sections 7.5 and 7.6): for every threshold pair, precision, recall,
feedback and top-3 likelihood from the leave-one-out experiment and the closure false alarm rate,
over the same anchors, commits and shipped code path (logical changesets, scored source companions)
as `extras`' replay. A development-set tool: the shipped thresholds are maat.COMPANION_CONFIDENCE and
maat.COMPANION_SHARED, and moving them is a change to what the hook says, measured here first.

    python -m gitmole.measure.companions [--set development] [--confidence 30,50,70,90] [--support 5,10,20]

Prints JSON: per repository, per "confidence/support" cell, the counts and rates; then a Markdown
table of the medians over the repositories on stderr."""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys

from .. import maat, watch
from . import corpus, extras

CONFIDENCE = (30, 50, 70, 90)
SUPPORT = (5, 10, 20)


def cells(confidence=CONFIDENCE, support=SUPPORT) -> list:
    return [(c, s) for c in confidence for s in support]


def filtered(pairs: list, confidence: int, support: int) -> list:
    """maat.companions' rows at the loosest thresholds, cut to one cell: the same table the shipped code
    would have built at those thresholds, since confidence and shared are per pair."""
    return [p for p in pairs if p["confidence"] >= confidence and p["shared"] >= support]


def sweep(clone: str, cache: str, out: str, grid: list, anchors: int = 3, window_months: int = 2, max_files: int = 20) -> dict:
    """{ "confidence/support": rates } for one repository, every cell over the same anchors and queries."""
    counts = {f"{c}/{s}": None for c, s in grid}
    least = min(s for _, s in grid)
    for report, history, window in extras.hook_anchors(clone, cache, out, anchors, window_months):
        every = maat.companions(history, min_confidence=1, min_shared=least)
        for c, s in grid:
            key = f"{c}/{s}"
            report["companions"] = filtered(every, c, s)
            counts[key] = extras.replay(report, watch.risks(report), window, counts[key], max_files)
    return {key: extras.rates(v or {"queries": 0, "warned": 0, "correct": 0, "top": 0, "complete_commits": 0, "closure_alarms": 0}) for key, v in counts.items()}


def medians(results: dict, grid: list) -> str:
    """Markdown: one row per cell, the median over repositories of each rate, and the pooled precision."""
    rows = ["| confidence / support | precision | recall | feedback | top-3 | complete commits alarmed | warnings |", "|---|---:|---:|---:|---:|---:|---:|"]
    for c, s in grid:
        key = f"{c}/{s}"
        per = [r[key] for r in results.values() if r.get(key)]

        def med(k):
            vals = [x[k] for x in per if x.get(k) is not None]
            return f"{statistics.median(vals):.2f}" if vals else "-"
        warned = sum(x["warned"] for x in per)
        mark = " (shipped)" if (c, s) == (maat.COMPANION_CONFIDENCE, maat.COMPANION_SHARED) else ""
        rows.append(f"| {c}% / {s}{mark} | {med('precision')} | {med('recall')} | {med('feedback')} | {med('top3')} | {med('closure_false_alarm_rate')} | {warned:,} |")
    return "\n".join(rows)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m gitmole.measure.companions", description=__doc__.split("\n\n")[0])
    p.add_argument("--set", default="development", choices=("development", "holdout"))
    p.add_argument("--confidence", default=",".join(map(str, CONFIDENCE)), help="percent, comma-separated")
    p.add_argument("--support", default=",".join(map(str, SUPPORT)), help="shared changesets, comma-separated")
    p.add_argument("--only", action="append", default=[], help="only these corpus entries")
    args = p.parse_args(argv)
    grid = cells([int(x) for x in args.confidence.split(",")], [int(x) for x in args.support.split(",")])
    root, manifest = corpus.workspace(), corpus.load()
    results = {}
    for e in [e for e in manifest["repos"] if e["set"] == args.set and not e.get("fixture") and e["name"] != "gitmole"]:
        if args.only and e["name"] not in args.only:
            continue
        results[e["name"]] = sweep(corpus.clone(e, root), os.path.join(root, "logs", e["name"] + ".txt"), os.path.join(root, "hook", e["name"]), grid)
        print(e["name"], {k: v["precision"] for k, v in results[e["name"]].items()}, file=sys.stderr, flush=True)
    json.dump(results, sys.stdout, indent=1)
    print()
    print(medians(results, grid), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Candidate rankings against the watch list and churn, over the same pool at the same six cut-offs
(docs/validation.md, "What the ranking is for"). Explore on the development set; the holdout is read
once, for the one variant chosen there, and never to pick between variants.

    python -m gitmole.measure.signals --release 0.27.0 --set development
    python -m gitmole.measure.signals --release 0.26.0 --set holdout --variant "revs 12m x lines"

Reads the run outputs a release left in the workspace (`run` or `history` first). Each variant ranks
the watch list's pool; the outcome is fix locality on development and the ApacheJIT labels on the
holdout, as in the harness. Prints each repository's top-15 hits, and the medians of ROC-AUC and of
recall at 20% of the pool's lines."""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from datetime import date

from .. import backtest, evaluate, load, maat, trend, watch
from . import corpus, harness, metrics


def _days(a: str, b: str) -> int:
    return (date.fromisoformat(b[:10]) - date.fromisoformat(a[:10])).days


def variants(report: dict, commits: list, t: str) -> tuple:
    """Every candidate's order of the pool at `t`, and the pool's lines."""
    rows = watch.risks(report)
    pool = [r["file"] for r in rows]
    lines = {f: ((report["size"]["files"].get(f) or {}).get("code") or 0) for f in pool}
    revs = {r["file"]: r["revs"] for r in rows}
    window, decay = {6: {}, 12: {}, 24: {}}, {6: {}, 12: {}}
    for c in maat.in_window(maat.analysed(commits), None, t):
        age = _days(c["date"], t)
        for p, _, _ in c["files"]:
            for m, d in window.items():
                if c["date"] >= maat.months_before(t, m):
                    d[p] = d.get(p, 0) + 1
            for h, d in decay.items():
                d[p] = d.get(p, 0.0) + 0.5 ** (age / (h * 30.44))
    hcm = {e["entity"]: e["hcm"] for e in report.get("entropy") or []}

    def order(key):
        return sorted(pool, key=lambda f: (-key(f), f))
    out = {"watch list": pool, "churn": order(lambda f: revs[f]), "size": order(lambda f: lines[f]),
           "entropy": order(lambda f: hcm.get(f, 0.0))}
    for m, d in window.items():
        out[f"revs {m}m x lines"] = order(lambda f, d=d: d.get(f, 0) * lines[f])
    for h, d in decay.items():
        out[f"decay {h}m x lines"] = order(lambda f, d=d: d.get(f, 0.0) * lines[f])
    return out, lines


def measure(entry: dict, release: str, root: str, labels, keep: set) -> dict:
    name = entry["name"]
    out, clone = os.path.join(root, "runs", release, name, "out"), os.path.join(root, "clones", name)
    meta = load._read_json(out, "meta.json", {})
    with open(os.path.join(out, "log.txt"), encoding="utf-8", errors="replace", newline="") as fh:
        commits = maat.parse_log(fh.read(), maat.aliases_from_meta(os.path.join(out, "meta.json")))
    earliest = min((c["date"] for c in commits), default="")[:10]
    per = {}
    for t in evaluate.cutoffs(entry.get("end") or meta["last_date"], harness.WINDOWS, harness.HORIZON):
        rev = trend.rev_before(clone, t, end_of_day=False) if t > earliest else None
        if not rev:
            continue
        size_json, generated, vendored = backtest.snapshot_at(clone, rev, out)
        report = evaluate.report_at(commits, t, load.parse_scc(size_json, None), meta, generated, vendored)
        ranked, lines = variants(report, commits, t)
        end = evaluate.months_after(t, harness.HORIZON)
        outcome = (evaluate.labelled_between(commits, labels, t, end) if labels is not None else evaluate.fixed_between(commits, t, end)) & set(ranked["watch list"])
        for v, order in ranked.items():
            if keep and v not in keep:
                continue
            d = per.setdefault(v, {"hits": 0, "auc": [], "recall20": []})
            d["hits"] += metrics.hits(order[:harness.TOP], outcome)
            d["auc"].append(metrics.auc(order, outcome))
            d["recall20"].append(metrics.recall_at_effort(order, lines, outcome, total=sum(lines.values())))
    return {v: {"hits": d["hits"], "auc": _median(d["auc"]), "recall20": _median(d["recall20"])} for v, d in per.items()}


def _median(values):
    values = [v for v in values if v is not None]
    return round(statistics.median(values), 3) if values else None


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m gitmole.measure.signals", description=__doc__.split("\n\n")[0])
    p.add_argument("--release", required=True, help="whose run outputs to read, e.g. 0.27.0")
    p.add_argument("--set", default="development", choices=("development", "holdout"))
    p.add_argument("--variant", action="append", default=[], help="only this variant, beside the watch list and churn (the holdout's one reading)")
    args = p.parse_args(argv)
    root, manifest = corpus.workspace(), corpus.load()
    keep = set(args.variant) | {"watch list", "churn"} if args.variant else set()
    labels_dir = os.environ.get("GITMOLE_LABELS_DIR") or ""
    results = {}
    for entry in [e for e in manifest["repos"] if e["set"] == args.set and not e.get("fixture")]:
        labels = harness.labels_for(entry, manifest, labels_dir) if entry.get("labels") else None
        if entry.get("labels") and labels is None:
            print(f"signals: {entry['name']}: labels not found under GITMOLE_LABELS_DIR", file=sys.stderr)
            return 2
        results[entry["name"]] = measure(entry, args.release, root, labels, keep)
        print(entry["name"], {v: r["hits"] for v, r in results[entry["name"]].items()}, file=sys.stderr, flush=True)
    json.dump(results, sys.stdout, indent=1)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())

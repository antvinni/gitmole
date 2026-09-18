"""One release's records reduced to the dashboard of docs/measurement.md, and the history of releases.

A release that crashed (or timed out) on any development repository is marked `crashed` with a note:
its summary values are left empty and the history draws it at the bottom of every graph, since a
number averaged over the repositories it survived would flatter it."""
from __future__ import annotations

import json
import os
import re

from . import metrics


def _repo_ranking(rec: dict):
    rows = [r for r in ((rec.get("ranking") or {}).get("cutoffs") or []) if "error" not in r]
    if not rows:
        return None
    h, e, b, ch = (sum(r[k] for r in rows) for k in ("hits", "expected", "best", "churn_hits"))
    mean = lambda k: metrics.median([r[k] for r in rows])   # noqa: E731
    return {"cutoffs": len(rows), "hits": h, "expected": round(e, 2), "best": b, "churn_hits": ch,
            "headroom": metrics.headroom(h, e, b), "churn_headroom": metrics.headroom(ch, e, b),
            "auc": mean("auc"), "churn_auc": mean("churn_auc"), "recall20": mean("recall20"), "churn_recall20": mean("churn_recall20"),
            "wins": sum(r["hits"] > r["churn_hits"] for r in rows), "losses": sum(r["hits"] < r["churn_hits"] for r in rows),
            "ties": sum(r["hits"] == r["churn_hits"] for r in rows)}


def _round(x, n=3):
    return None if x is None else round(x, n)


def summarise(record: dict) -> dict:
    """The dashboard numbers for one release, from its per-repository records."""
    repos = record["repos"]
    dev = {n: r for n, r in repos.items() if r.get("set") == "development"}
    crashed = {n: r.get("note") or r["status"] for n, r in dev.items() if r["status"] in ("crashed", "timeout")}
    out = {"crashed": crashed or None}
    ranked = {n: _repo_ranking(r) for n, r in dev.items()}
    ranked = {n: v for n, v in ranked.items() if v}
    per = {n: [v["headroom"]] for n, v in ranked.items()}
    out["headroom"] = _round(metrics.median([v["headroom"] for v in ranked.values()]))
    out["headroom_ci"] = [_round(x) for x in (metrics.bootstrap(per, metrics.median) or [])] or None
    out["churn_headroom"] = _round(metrics.median([v["churn_headroom"] for v in ranked.values()]))
    out["wins_losses_ties"] = [sum(v[k] for v in ranked.values()) for k in ("wins", "losses", "ties")] if ranked else None
    for k in ("auc", "churn_auc", "recall20", "churn_recall20"):
        out[k] = _round(metrics.median([v[k] for v in ranked.values()]))
    stab = [((r.get("ranking") or {}).get("stability") or {}) for r in dev.values()]
    out["stability_top15"] = _round(metrics.median([s.get("top_jaccard") for s in stab]))
    out["stability_spearman"] = _round(metrics.median([s.get("spearman") for s in stab]))
    mags = [m for r in dev.values() for m in ((r.get("ranking") or {}).get("magnets") or [])]
    named, nf = sum(m["named"] for m in mags), sum(m["named_fixed"] for m in mags)
    matched, mf = sum(m["matched"] for m in mags), sum(m["matched_fixed"] for m in mags)
    out["bug_magnets_ratio"] = _round((nf / named) / (mf / matched)) if named and matched and mf else None
    ok = [r for r in dev.values() if r["status"] == "ok"]
    out["findings_median"] = metrics.median([r.get("findings") for r in ok])
    out["findings_p90"] = _round(metrics.percentile([r.get("findings") for r in ok], 0.9), 1)
    out["report_lines"] = metrics.median([r.get("report_lines") for r in ok])
    out["scored_share"] = _round(metrics.median([r.get("scored_share") for r in ok]))
    out["seconds"] = _round(sum(r.get("seconds") or 0 for r in ok), 1) if ok else None
    out["peak_mb"] = max((r.get("peak_mb") or 0 for r in ok), default=None)
    steps = {}
    for r in ok:
        for k, v in (r.get("step_seconds") or {}).items():
            steps.setdefault(k, []).append(v)
    out["step_seconds"] = {k: _round(metrics.median(v), 1) for k, v in sorted(steps.items())} or None
    runs = [r for r in repos.values()]
    robust = [r["status"] in ("ok", "refused") and not r.get("steps_failed") for r in runs]
    out["robust"] = [sum(robust), len(robust)]
    gate = [r for r in runs if r.get("set") == "gate"]
    out["gate_caught"] = [sum(bool(r.get("gate_fired")) for r in gate), len(gate)] if gate else None
    kept = [r for r in runs if r.get("set") == "well-kept" and r["status"] == "ok"]
    if kept:
        out["well_kept_with_critical"] = [sum(1 for r in kept if (r.get("severity") or {}).get("critical")), len(kept)]
    hold = {n: _repo_ranking(r) for n, r in repos.items() if r.get("set") == "holdout"}
    hold = {n: v for n, v in hold.items() if v}
    if hold:
        out["holdout_headroom"] = _round(metrics.median([v["headroom"] for v in hold.values()]))
        out["holdout_headroom_ci"] = [_round(x) for x in (metrics.bootstrap({n: [v["headroom"]] for n, v in hold.items()}, metrics.median) or [])] or None
        out["holdout_wins_losses_ties"] = [sum(v[k] for v in hold.values()) for k in ("wins", "losses", "ties")]
        out["holdout_recall20"] = _round(metrics.median([v["recall20"] for v in hold.values()]))
    return out


def per_repo(record: dict) -> dict:
    return {n: _repo_ranking(r) for n, r in record["repos"].items()}


def _key(version: str):
    return tuple(int(x) for x in re.findall(r"\d+", version))


def load_history(directory: str) -> list:
    """Every release record in `directory`, oldest first."""
    out = []
    for name in os.listdir(directory):
        if name.endswith(".json") and re.match(r"^\d+\.\d+\.\d+\.json$", name):
            with open(os.path.join(directory, name), encoding="utf-8") as fh:
                out.append(json.load(fh))
    return sorted(out, key=lambda r: _key(r["version"]))


def moved(prev: dict, cur: dict, key: str = "headroom") -> str:
    """'up' or 'down' when the release's value leaves the previous release's interval, else ''."""
    ci = (prev or {}).get(key + "_ci")
    v = (cur or {}).get(key)
    if not ci or v is None:
        return ""
    return "up" if v > ci[1] else "down" if v < ci[0] else ""

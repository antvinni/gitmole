"""One release's records reduced to the dashboard of docs/measurement.md, and the history of releases.

A release that crashed (or timed out) on any development or large repository is marked `crashed` with a
note: its summary values are left empty and the history draws it at the bottom of every graph, since a
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
    # size alone is stored per cut-off from 0.38.0 on; a record without it at every cut-off has none, not zero
    sh = sum(r["size_hits"] for r in rows) if all(r.get("size_hits") is not None for r in rows) else None
    return {"cutoffs": len(rows), "hits": h, "expected": round(e, 2), "best": b, "churn_hits": ch,
            "headroom": metrics.headroom(h, e, b), "churn_headroom": metrics.headroom(ch, e, b),
            "size_stored": sh is not None, "size_headroom": None if sh is None else metrics.headroom(sh, e, b),
            "auc": mean("auc"), "churn_auc": mean("churn_auc"), "recall20": mean("recall20"), "churn_recall20": mean("churn_recall20"),
            "wins": sum(r["hits"] > r["churn_hits"] for r in rows), "losses": sum(r["hits"] < r["churn_hits"] for r in rows),
            "ties": sum(r["hits"] == r["churn_hits"] for r in rows)}


def _carryover(rec: dict):
    """The mean overlap (Jaccard) of the top fifteen between consecutive cut-offs, six months apart: 50
    commits say the list does not thrash; this says whether it answers to half a year of change. None
    for a record from before the tops were kept."""
    tops = [r["top"] for r in ((rec.get("ranking") or {}).get("cutoffs") or []) if "error" not in r and r.get("top")]
    pairs = [j for j in (metrics.jaccard(a, b) for a, b in zip(tops, tops[1:])) if j is not None]
    return sum(pairs) / len(pairs) if pairs else None


def _round(x, n=3):
    return None if x is None else round(x, n)


SATURATED = 0.5   # half the pool or more fixed at a cut-off: flagged here and by candidate.py, never excluded
MEASURED = ("development", "large")   # the sets a release round ranks; the development set alone carries the cost ceilings
RANKED = (*MEASURED, "well-kept")   # well-kept adds to the effectiveness numbers only: chosen by an outside criterion, never tuned on


def summarise(record: dict, only=None) -> dict:
    """The dashboard numbers for one release, from its per-repository records. The cost keys (findings,
    report lines, wall time, memory, scored share) are the development set's, which the fast loop
    measures whole, so a loop can be held to them. The effectiveness keys (headroom, AUC, recall,
    stability, carry-over, magnets) span development and large, since the large repositories are the
    ranking's hard cases, and the well-kept set where it was ranked (release rounds after 28 September 2026); a
    well-kept crash is not a release crash, as before. With `only`, the like-for-like series the long graphs draw: every key over
    those repositories, whichever of the two sets holds them."""
    repos = record["repos"]
    if only is None:
        pop = {n: r for n, r in repos.items() if r.get("set") in RANKED}
        cost = {n: r for n, r in pop.items() if r.get("set") == "development"}
    else:
        pop = cost = {n: r for n, r in repos.items() if r.get("set") in MEASURED and n in only}
    crashed = {n: r.get("note") or r["status"] for n, r in pop.items() if r["status"] in ("crashed", "timeout") and r.get("set") in MEASURED}
    out = {"crashed": crashed or None}
    ranked = {n: _repo_ranking(r) for n, r in pop.items()}
    ranked = {n: v for n, v in ranked.items() if v}
    per = {n: [v["headroom"]] for n, v in ranked.items()}
    out["headroom"] = _round(metrics.median([v["headroom"] for v in ranked.values()]))
    out["headroom_ci"] = [_round(x) for x in (metrics.bootstrap(per, metrics.median) or [])] or None
    out["churn_headroom"] = _round(metrics.median([v["churn_headroom"] for v in ranked.values()]))
    # over the same repositories as churn alone, or not at all: a median over the few that stored it would not compare
    sized = bool(ranked) and all(v["size_stored"] for v in ranked.values())
    out["size_headroom"] = _round(metrics.median([v["size_headroom"] for v in ranked.values()])) if sized else None
    out["wins_losses_ties"] = [sum(v[k] for v in ranked.values()) for k in ("wins", "losses", "ties")] if ranked else None
    for k in ("auc", "churn_auc", "recall20", "churn_recall20"):
        out[k] = _round(metrics.median([v[k] for v in ranked.values()]))
    stab = [((r.get("ranking") or {}).get("stability") or {}) for r in pop.values()]
    out["stability_top15"] = _round(metrics.median([s.get("top_jaccard") for s in stab]))
    out["stability_spearman"] = _round(metrics.median([s.get("spearman") for s in stab]))
    out["carryover_top15"] = _round(metrics.median([_carryover(r) for r in pop.values()]))
    mags = [m for r in pop.values() for m in ((r.get("ranking") or {}).get("magnets") or [])]
    named, nf = sum(m["named"] for m in mags), sum(m["named_fixed"] for m in mags)
    matched, mf = sum(m["matched"] for m in mags), sum(m["matched_fixed"] for m in mags)
    out["bug_magnets_ratio"] = _round((nf / named) / (mf / matched)) if named and matched and mf else None
    # information, never a decision (measurement.md, "Is a candidate better?"): how far the list sits above
    # the better simple list at each cut-off, and how many cut-offs had half their pool or more fixed
    cuts = [c for r in pop.values() for c in ((r.get("ranking") or {}).get("cutoffs") or []) if "hits" in c]
    lift = [c["hits"] - max(c["churn_hits"], c["size_hits"]) for c in cuts if c.get("size_hits") is not None]
    out["simple_lift"] = sum(lift) if lift else None
    out["simple_wins_losses_ties"] = [sum(x > 0 for x in lift), sum(x < 0 for x in lift), sum(x == 0 for x in lift)] if lift else None
    out["saturated_cutoffs"] = [sum(1 for c in cuts if c.get("pool") and c["positives"] / c["pool"] >= SATURATED), len(cuts)] if cuts else None
    ok = [r for r in cost.values() if r["status"] == "ok"]
    out["findings_median"] = metrics.median([r.get("findings") for r in ok])
    out["findings_p90"] = _round(metrics.percentile([r.get("findings") for r in ok], 0.9), 1)
    out["shown_median"] = metrics.median([r.get("shown") for r in ok])   # spelled out in the default report; None before 0.28.0's backfill
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
    # every set, not only development: the fixtures are where a rule that rarely fires says its piece
    claimed = [r.get("claims") for r in runs if isinstance(r.get("claims"), dict)]
    if claimed:
        out["claims_clean"] = [sum(c.get("clean") or 0 for c in claimed), sum(c.get("checked") or 0 for c in claimed)]
    consistent = [r.get("consistency") for r in runs if isinstance(r.get("consistency"), dict)]
    if consistent:   # every complaint is a contradiction between a finding and the report's own facts; the number to want is zero
        by = {}
        for c in consistent:
            for k, v in (c.get("by_check") or {}).items():
                by[k] = by.get(k, 0) + v
        out["contradictions"] = sum(by.values())
        out["contradictions_by_check"] = dict(sorted(by.items()))
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
    large = [r for r in repos.values() if r.get("set") == "large" and r["status"] == "ok"]
    if only is None and large:
        out["large_seconds"] = _round(sum(r.get("seconds") or 0 for r in large), 1)
        out["large_peak_mb"] = max((r.get("peak_mb") or 0 for r in large), default=None)
        out["large_findings_median"] = metrics.median([r.get("findings") for r in large])
    if only is None:
        acted = _remediation(cost.values())   # the development set only: REMEDIATION_SETS
        if acted:
            out["remediation"] = acted
    return out


def _remediation(recs) -> dict:
    """The share acted on per rule, its outcome counts summed over the repositories and the cut-offs
    (remediation.pooled), and the mechanical and structural bands; None when no record carries it. It is
    remediation's lower bound as it stands: subjects named at several cut-offs count at each, and a file
    moved or renamed counts as left the tree."""
    from . import remediation
    rows = [r["remediation"]["rules"] for r in recs if isinstance(r.get("remediation"), dict) and r["remediation"].get("rules") is not None]
    if not rows:
        return None
    rules = remediation.pooled(rows)
    cutoffs = [c for r in recs for c in ((r.get("remediation") or {}).get("cutoffs") or [])]
    return {"repos": len(rows), "cutoffs": [sum(1 for c in cutoffs if "error" not in c), len(cutoffs)],
            "rules": rules, "bands": remediation.bands(rules)}


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

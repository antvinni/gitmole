"""The watch list: where the next bug is most likely, from every per-file signal gitmole has.

Each source file that is still in the tree and changed more than once gets a score of
churn × (1 + recent fixes) × (1 + complexity) × (1.5 if single-owned), churn, fixes and
complexity each scaled to the worst file in the repo, plus a list of reasons in plain
words. Churn is the base because a file nobody changes is not where the next bug lands;
ownership is the weakest of the four predictors, so it weighs the least. Complexity is
scc's per-file total, which exists for every file on one scale; lizard's most complex
function in the file is named in the reasons but does not enter the score, since lizard
has no reader for shell, Terraform, Makefiles and the like."""
from __future__ import annotations

from collections import Counter, defaultdict

try:
    from . import filetypes, hotspots
except ImportError:  # pragma: no cover - not run as a script, but keep the package pattern
    import filetypes
    import hotspots

CCN_FLOOR = 10          # lizard's own "complex" threshold: below it a function is not worth naming
SOLO_SHARE = 0.9        # one author wrote at least this much of the file: single ownership
SOLO_WEIGHT = 1.5       # how much single ownership lifts the score
COMPANION_DEGREE = 50   # a coupling worth mentioning
COMPANION_REVS = 5      # ...over enough shared revisions to be a pattern


def _times(n: int) -> str:
    return {1: "once", 2: "twice"}.get(n, f"{n} times")


def _owners(report: dict) -> dict:
    per = defaultdict(Counter)
    for r in report.get("ownership") or []:
        if r.get("added", 0) > 0:
            per[r["entity"]][r["author"]] += r["added"]
    return per


def _companions(report: dict) -> dict:
    """entity -> [(other, degree)] for couplings strong and frequent enough to be a pattern, test files left out."""
    out = defaultdict(list)
    for p in report.get("coupling") or []:
        if p["degree"] < COMPANION_DEGREE or p["average-revs"] < COMPANION_REVS:
            continue
        if filetypes.is_test_path(p["entity"]) or filetypes.is_test_path(p["coupled"]):
            continue
        out[p["entity"]].append((p["coupled"], p["degree"]))
        out[p["coupled"]].append((p["entity"], p["degree"]))
    for v in out.values():
        v.sort(key=lambda t: (-t[1], t[0]))
    return out


def _worst_function(report: dict) -> dict:
    worst = {}
    for f in report.get("functions") or []:
        if f["file"] not in worst or f["ccn"] > worst[f["file"]]["ccn"]:
            worst[f["file"]] = f
    return worst


def risks(report: dict, min_revs: int = 2) -> list:
    owners = _owners(report)
    companions = _companions(report)
    worst = _worst_function(report)
    fixes = {f["entity"]: f for f in report.get("fixes") or []}
    n_authors = {a["entity"]: a["n-authors"] for a in report.get("authors") or []}

    rows = []
    for h in hotspots.ranked(report):
        if h["code"] is None or h["revs"] < min_revs or filetypes.is_test_path(h["entity"]):
            continue
        fx = fixes.get(h["entity"], {})
        own = owners.get(h["entity"]) or Counter()
        owner, owner_lines = (own.most_common(1)[0] if own else (None, 0))
        share = owner_lines / sum(own.values()) if own else 0.0
        fn = worst.get(h["entity"])
        rows.append({"file": h["entity"], "revs": h["revs"], "recent_fixes": fx.get("recent-fixes", 0), "fixes": fx.get("n-fixes", 0),
                     "authors": n_authors.get(h["entity"]), "owner": owner, "owner_share": share,
                     "complexity": h["complexity"] or 0,
                     "function": fn, "companions": companions.get(h["entity"], [])})
    if not rows:
        return []

    max_revs = max(r["revs"] for r in rows)
    max_fix = max(r["recent_fixes"] for r in rows)
    max_cplx = max(r["complexity"] for r in rows)
    for r in rows:
        solo = r["authors"] == 1 or r["owner_share"] >= SOLO_SHARE
        r["solo"] = solo
        r["score"] = (r["revs"] / max_revs) * (1 + (r["recent_fixes"] / max_fix if max_fix else 0)) \
            * (1 + (r["complexity"] / max_cplx if max_cplx else 0)) * (SOLO_WEIGHT if solo else 1)
        r["reasons"] = _reasons(r)
    rows.sort(key=lambda r: (-r["score"], -r["revs"], r["file"]))
    return rows


def why_empty(report: dict, min_revs: int = 2) -> str:
    """Why risks() came back empty, for the report's one-line note: the honest reason, since
    "nothing changed" above a hotspots table full of revisions would be a lie."""
    churned = [h for h in hotspots.ranked(report) if h["revs"] >= min_revs]
    if not churned:
        return "nothing changed more than once"
    if all(filetypes.is_test_path(h["entity"]) for h in churned):
        return "only test files changed more than once"
    if not (report.get("size") or {}).get("files"):
        return "no size data for the files that changed"
    return "the files that changed more than once are no longer in the tree"


def _reasons(r: dict) -> list:
    out = [f"changed {_times(r['revs'])}"]
    if r["recent_fixes"]:
        out.append(f"fixed {_times(r['recent_fixes'])} in six months")
    elif r["fixes"]:
        out.append(f"fixed {_times(r['fixes'])}")
    if r["authors"] == 1:
        out.append(f"only {r['owner']} has touched it" if r["owner"] else "one author only")
    elif r["owner_share"] >= SOLO_SHARE and r["owner"]:
        out.append(f"{r['owner']} wrote {round(100 * r['owner_share'])}% of it")
    fn = r["function"]
    if fn and fn["ccn"] >= CCN_FLOOR:
        out.append(f"{fn['function']}() complexity {fn['ccn']}")
    if r["companions"]:
        other, degree = r["companions"][0]
        more = len(r["companions"]) - 1
        tail = f" and {more} other{'s' if more != 1 else ''}" if more else ""
        out.append(f"changes with {other} ({degree}%){tail}")
    return out


WATCH_TOP = 15   # the same cap the report's --full watch list uses


def change_risk(report: dict, files: list) -> dict:
    """The watch score of each touched file, and their sum. Files the watch list never scored get 0
    and one reason saying why."""
    ranked = risks(report)
    by_file = {r["file"]: r for r in ranked}
    watched = {r["file"] for r in ranked[:WATCH_TOP]}
    in_tree = (report.get("size") or {}).get("files") or {}
    revisions_dict = {r["entity"]: r.get("n-revs", 0) for r in (report.get("revisions") or [])}
    rows = []
    for f in files:
        r = by_file.get(f)
        if r:
            rows.append({"file": f, "score": r["score"], "reasons": r["reasons"], "watched": f in watched})
        elif filetypes.is_test_path(f):
            rows.append({"file": f, "score": 0, "reasons": ["test file"], "watched": False})
        elif revisions_dict.get(f) == 1:
            rows.append({"file": f, "score": 0, "reasons": ["changed once"], "watched": False})
        elif f not in in_tree:
            rows.append({"file": f, "score": 0, "reasons": ["new file"], "watched": False})
        else:
            rows.append({"file": f, "score": 0, "reasons": ["changed once"], "watched": False})
    rows.sort(key=lambda r: (-r["score"], r["file"]))
    return {"files": rows, "total": float(sum(r["score"] for r in rows)), "watched": sum(r["watched"] for r in rows),
            "max_score": max((r["score"] for r in rows), default=0.0)}

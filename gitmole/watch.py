"""The watch list: the source files most likely to be fixed next, and what else counts against each.

Each source file that is still in the tree and changed more than once is ranked by revisions × lines
of code, the product the Hotspots table uses: measured at six cut-offs on three repositories
(docs/validation.md), that product named more of the files fixed in the following six months than
any weighting of fixes, complexity and ownership did. Those signals are the reasons printed beside
each file: how often it was fixed lately, who alone owns it, its most complex function, how much its
complexity grew in the last year, what it always changes with. A file's score is its share, in
percent, of all scored files' revisions × lines of code, so the scores of the whole list add up to
100 and a change's `--risk` total is the share of that mass the change touches; one enormous file
takes a large share, as it should, and lowers the others' only by what it adds to the whole. The
factor products the list used to rank by live in gitmole.evaluate, which still compares them with it.
Complexity is scc's per-file total, which exists for every file on one scale; lizard's most complex
function in the file is what the reasons name, since lizard has no reader for shell, Terraform,
Makefiles and the like."""
from __future__ import annotations

from collections import Counter, defaultdict

from . import filetypes, hotspots, textfmt, trend

CCN_FLOOR = 10          # lizard's own "complex" threshold: below it a function is not worth naming
SOLO_SHARE = 0.9        # one author wrote at least this much of the file: single ownership
COMPANION_DEGREE = 50   # a coupling worth mentioning
COMPANION_REVS = 5      # ...over enough shared revisions to be a pattern


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
    """The most complex function per file, passing over spans the function step marked as likely
    mis-parsed: a swallowed span's complexity is not the file's."""
    worst = {}
    for f in report.get("functions") or []:
        if not f.get("suspect") and (f["file"] not in worst or f["ccn"] > worst[f["file"]]["ccn"]):
            worst[f["file"]] = f
    return worst


def risks(report: dict, min_revs: int = 2) -> list:
    """The watch list: every scored file with its reasons, worst first. A file's score is its
    percentage share of the pool's revisions × lines of code."""
    owners = _owners(report)
    companions = _companions(report)
    worst = _worst_function(report)
    fixes = {f["entity"]: f for f in report.get("fixes") or []}
    n_authors = {a["entity"]: a["n-authors"] for a in report.get("authors") or []}
    series = (report.get("trend") or {}).get("files") or {}
    last = (report.get("meta") or {}).get("last_date") or ""

    plumb, derived = filetypes.plumbing_paths(report), hotspots.derived(report)
    rows = []
    for h in hotspots.ranked(report):
        if (h["code"] is None or h["revs"] < min_revs or filetypes.is_test_path(h["entity"]) or filetypes.is_release(h["entity"], plumb)
                or h["entity"] in derived):
            continue   # a version file, a manifest or a build output changes for reasons that say nothing about its quality
        fx = fixes.get(h["entity"], {})
        own = owners.get(h["entity"]) or Counter()
        owner, owner_lines = (own.most_common(1)[0] if own else (None, 0))
        share = owner_lines / sum(own.values()) if own else 0.0
        fn = worst.get(h["entity"])
        rows.append({"file": h["entity"], "revs": h["revs"], "recent_fixes": fx.get("recent-fixes", 0), "fixes": fx.get("n-fixes", 0),
                     "authors": n_authors.get(h["entity"]), "owner": owner, "owner_share": share,
                     "complexity": h["complexity"] or 0, "code": h["code"],
                     "function": fn, "companions": companions.get(h["entity"], []),
                     "trend": trend.change_over_year(series[h["entity"]], last) if last and h["entity"] in series else None})
    if not rows:
        return []

    pool = sum(r["revs"] * r["code"] for r in rows)
    for r in rows:
        r["solo"] = r["authors"] == 1 or r["owner_share"] >= SOLO_SHARE
        r["score"] = 100 * (r["revs"] * r["code"]) / pool if pool else 0.0
        r["reasons"] = _reasons(r)
    rows.sort(key=lambda r: (-r["score"], -r["revs"], r["file"]))
    return rows


def why_empty(report: dict, min_revs: int = 2) -> str:
    """Why risks() came back empty, for the report's one-line note: the honest reason, since files
    can well have changed even though none of them scored, and a flat "nothing changed" would be
    a lie about them."""
    churned = [h for h in hotspots.ranked(report) if h["revs"] >= min_revs]
    if not churned:
        return "nothing changed more than once"
    if all(filetypes.is_test_path(h["entity"]) for h in churned):
        return "only test files changed more than once"
    if not (report.get("size") or {}).get("files"):
        return "no size data for the files that changed"
    return "the files that changed more than once are no longer in the tree"


def _reasons(r: dict) -> list:
    out = [f"changed {textfmt.times(r['revs'])}"]
    if r["recent_fixes"]:
        out.append(f"fixed {textfmt.times(r['recent_fixes'])} in six months")
    elif r["fixes"]:
        out.append(f"fixed {textfmt.times(r['fixes'])}")
    if r["authors"] == 1:
        out.append(f"only {r['owner']} has touched it" if r["owner"] else "one author only")
    elif r["owner_share"] >= SOLO_SHARE and r["owner"]:
        out.append(f"{r['owner']} wrote {round(100 * r['owner_share'])}% of it")
    fn = r["function"]
    if fn and fn["ccn"] >= CCN_FLOOR:
        named = f"the function at line {fn['start']}" if fn.get("anonymous") else f"{fn['function']}()"
        out.append(f"{named} complexity {fn['ccn']}")
    grown = r.get("trend") or ""
    if grown.startswith("+") and int(grown[1:-1]) >= trend.GROWTH_FLOOR:
        out.append(f"complexity {grown} in a year")   # the Hotspots table's trend column, which the default report no longer shows
    if r["companions"]:
        other, degree = r["companions"][0]
        more = len(r["companions"]) - 1
        tail = f" and {more} other{'s' if more != 1 else ''}" if more else ""
        out.append(f"changes with {other} ({degree}%){tail}")
    return out


WATCH_TOP = 15   # the same cap the report's --full watch list uses


def change_risk(report: dict, files: list) -> dict:
    """The watch score of each touched file, and their sum: that total is a percentage of the
    repository's revisions × lines of code. Files the watch list never scored get 0 and one reason
    saying why."""
    ranked = risks(report)
    by_file = {r["file"]: r for r in ranked}
    watched = {r["file"] for r in ranked[:WATCH_TOP]}
    in_tree = (report.get("size") or {}).get("files") or {}
    revs = {r["entity"]: r["n-revs"] for r in report.get("revisions") or []}
    rows = []
    for f in files:
        r = by_file.get(f)
        if r:
            rows.append({"file": f, "score": r["score"], "reasons": r["reasons"], "watched": f in watched})
        elif filetypes.is_test_path(f):
            rows.append({"file": f, "score": 0, "reasons": ["test file"], "watched": False})
        elif f not in in_tree:
            rows.append({"file": f, "score": 0, "reasons": ["new file"], "watched": False})
        elif revs.get(f) == 1:
            rows.append({"file": f, "score": 0, "reasons": ["changed once"], "watched": False})
        else:
            rows.append({"file": f, "score": 0, "reasons": ["not scored"], "watched": False})
    rows.sort(key=lambda r: (-r["score"], r["file"]))
    return {"files": rows, "total": float(sum(r["score"] for r in rows)), "watched": sum(r["watched"] for r in rows),
            "max_score": float(ranked[0]["score"]) if ranked and rows else 0.0}


# What a simpler list would rank by. Churn alone is the one to beat: a file's past changes predict
# its next fix better than most of what can be measured about its contents. Their product is the
# list itself.
BASELINES = {"churn": lambda r: r["revs"], "size": lambda r: r["code"]}


def ranked_by(rows: list, key) -> list:
    """File names, the highest `key` first, ties by file name."""
    return [r["file"] for r in sorted(sorted(rows, key=lambda r: r["file"]), key=key, reverse=True)]


def backtest(report: dict, top: int = WATCH_TOP):
    """How the watch list as of the cut-off T (report["backtest"]) did against the fixes that came after.
    Expected value is a random pick of listed files from the same pool the list draws from; `baselines`
    is what the same number of files ranked by churn alone and by size alone would have named."""
    past = report.get("backtest")
    if not past or not (past.get("size") or {}).get("files"):
        return None
    t = (past.get("meta") or {}).get("now")
    if not t:
        return None                       # a sub-report without its cut-off cannot be scored
    rows = risks(past)
    pool = [r["file"] for r in rows]
    listed = pool[:top]
    fixed = {f["entity"] for f in report.get("fixes") or [] if f.get("last-fix", "") > t and not filetypes.is_test_path(f["entity"])}
    expected = round(len(listed) * len(fixed.intersection(pool)) / len(pool), 1) if pool else 0.0
    baselines = {name: len(fixed.intersection(ranked_by(rows, key)[:top])) for name, key in BASELINES.items()}
    return {"t": t, "pool": len(pool), "listed": len(listed), "fixed": len(fixed), "hits": len(fixed.intersection(listed)),
            "expected": expected, "baselines": baselines}

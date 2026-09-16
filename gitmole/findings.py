"""Heuristics that turn a loaded report into a short list of flagged findings."""
from __future__ import annotations

import re

from . import knowledge

SEVERITIES = ["critical", "warning", "info"]

PLACEHOLDER_NAMES = {"your name", "unknown", "root", "user"}
PLACEHOLDER_EMAIL = re.compile(r"(@example\.(com|org|net)$|^you@|^user@|^root@|@localhost$)")


def _f(severity: str, title: str, detail: str) -> dict:
    return {"severity": severity, "title": title, "detail": detail}


def _pct(part, whole) -> str:
    return f"{round(100 * part / whole)}%" if whole else "0%"


def secrets_found(report: dict) -> list:
    secrets = report.get("secrets") or []
    if not secrets:
        return []
    sample = ", ".join(f"{s['rule']} in {s['file']} ({s['commit']})" for s in secrets[:3])
    more = f" and {len(secrets) - 3} more" if len(secrets) > 3 else ""
    return [_f("critical", f"{len(secrets)} secret(s) in history", f"{sample}{more}. Rotate them; deleting the file does not remove them from git.")]


def _all_identities(report: dict):
    """Every identity row plus its aliases, flattened."""
    for i in report["meta"].get("identities") or []:
        yield i
        for a in i.get("aliases") or []:
            yield a


def placeholder_identity(report: dict) -> list:
    total = sum(i["commits"] for i in report["meta"].get("identities") or [])
    out = []
    for i in _all_identities(report):
        if i["name"].strip().lower() in PLACEHOLDER_NAMES or PLACEHOLDER_EMAIL.search(i["email"].lower()):
            out.append(_f("warning", "Unconfigured git identity",
                          f"\"{i['name']} <{i['email']}>\" made {i['commits']} commits ({_pct(i['commits'], total)}). Set user.name and user.email; consider a .mailmap for history."))
    return out


def bus_factor(report: dict, threshold: float = 0.7) -> list:
    shares = report.get("theseus_authors") or {}
    total = sum(shares.values())
    if not total:
        return []
    name, lines = max(shares.items(), key=lambda kv: kv[1])
    if lines / total <= threshold:
        return []
    return [_f("warning", "Bus factor of one",
               f"{name} wrote {_pct(lines, total)} of the code that survives today.")]


def sizer_concerns(report: dict) -> list:
    out = []
    for row in report.get("sizer") or []:
        sev = "warning" if row["concern"] >= 2 else "info"
        where = f" at {row['ref']}" if row.get("ref") else ""
        out.append(_f(sev, "Repo health", f"{row['name']} is {row['value']}{where}. git-sizer level of concern {row['concern']}."))
    return out


def hotspot_dominance(report: dict, ratio: float = 2.0, minimum: int = 20) -> list:
    revs = sorted(report.get("revisions") or [], key=lambda r: -r["n-revs"])
    if len(revs) < 2 or revs[0]["n-revs"] < minimum or revs[0]["n-revs"] < ratio * revs[1]["n-revs"]:
        return []
    top, nxt = revs[0], revs[1]
    return [_f("info", "One file dominates the churn",
               f"{top['entity']} changed {top['n-revs']} times, versus {nxt['n-revs']} for the next file ({nxt['entity']}).")]


def tight_coupling(report: dict, min_degree: int = 80, min_revs: int = 5) -> list:
    pairs = [p for p in report.get("coupling") or [] if p["degree"] >= min_degree and p["average-revs"] >= min_revs]
    if not pairs:
        return []
    pairs.sort(key=lambda p: (-p["degree"], -p["average-revs"]))
    top = "; ".join(f"{p['entity']} + {p['coupled']} ({p['degree']}%)" for p in pairs[:3])
    count = f"{len(pairs)} pair changes" if len(pairs) == 1 else f"{len(pairs)} pairs change"
    return [_f("info", "Files that always change together",
               f"{count} together at least {min_degree}% of the time, e.g. {top}. Usually a shared layout or a hidden dependency.")]


def stale_files(report: dict, months: int = 12, share: float = 0.3) -> list:
    age = report.get("age") or []
    if not age:
        return []
    stale = [a for a in age if a["age-months"] >= months]
    if len(stale) / len(age) <= share:
        return []
    return [_f("info", "A large share of files is untouched",
               f"{_pct(len(stale), len(age))} of files ({len(stale)}) have not changed in {months} months or more.")]


def duplicate_identities(report: dict) -> list:
    out = []
    for i in report["meta"].get("identities") or []:
        aliases = i.get("aliases") or []
        if not aliases:
            continue
        names = ", ".join(f"{a['name']} <{a['email']}>" for a in aliases)
        out.append(_f("info", "One person under several identities",
                      f"{names} merged into {i['name']} <{i['email']}> by name and email similarity. Add a .mailmap to make it permanent."))
    return out


_TEST_PATH = re.compile(r"(^|/)(tests?|spec|specs|__tests__|testing)(/|$)|(^|/)(test_[^/]*|[^/]*_test\.[^/]+|[^/]*\.spec\.[^/]+|[^/]*\.test\.[^/]+)$", re.I)


def bug_magnets(report: dict, min_recent: int = 3, warn_at: int = 5) -> list:
    """Source files with a run of recent fix commits. Test files are left out: they change with every fix."""
    hot = [f for f in report.get("fixes") or [] if f["recent-fixes"] >= min_recent and not _TEST_PATH.search(f["entity"])]
    if not hot:
        return []
    hot.sort(key=lambda f: (-f["recent-fixes"], -f["n-fixes"], f["entity"]))
    sev = "warning" if hot[0]["recent-fixes"] >= warn_at else "info"
    listed = "; ".join(f"{f['entity']} ({f['recent-fixes']} recent, {f['n-fixes']} total)" for f in hot[:5])
    more = f" and {len(hot) - 5} more" if len(hot) > 5 else ""
    return [_f(sev, "Bug magnets",
               f"{len(hot)} file(s) were fixed {min_recent}+ times in the last six months: {listed}{more}. Expect the next bug there too.")]


def knowledge_islands(report: dict, min_lines: int = 200, min_share: float = 0.9) -> list:
    areas = knowledge.areas(report.get("ownership") or [])
    islands = knowledge.islands(areas, min_lines=min_lines, min_share=min_share)
    if not islands:
        return []
    total = sum(a["lines"] for a in areas)
    covered = sum(i["lines"] for i in islands)
    sev = "warning" if total and covered / total > 0.5 else "info"
    listed = "; ".join(f"{i['area']} ({i['owner']} {i['share']}%)" for i in islands[:5])
    more = f" and {len(islands) - 5} more" if len(islands) > 5 else ""
    return [_f(sev, "Knowledge islands",
               f"{len(islands)} area(s) with at least {min_lines} lines were written almost entirely by one person: {listed}{more}. "
               f"That is {_pct(covered, total)} of all lines added. Pair or review across them before that person is unavailable.")]


def _hot_files(report: dict, n: int = 10) -> set:
    revs = sorted(report.get("revisions") or [], key=lambda r: -r["n-revs"])
    return {r["entity"] for r in revs[:n]}


def brain_methods(report: dict, min_ccn: int = 15, min_lines: int = 100) -> list:
    """Functions that are both long and complex. A warning when one sits in a hotspot."""
    big = [f for f in report.get("functions") or [] if f["ccn"] >= min_ccn and f["nloc"] >= min_lines]
    if not big:
        return []
    big.sort(key=lambda f: (-f["ccn"], -f["nloc"]))
    hot = _hot_files(report)
    sev = "warning" if any(f["file"] in hot for f in big) else "info"
    listed = "; ".join(f"{f['function']} ({f['file']}) complexity {f['ccn']}, {f['nloc']} lines, {f['params']} params" for f in big[:5])
    more = f" and {len(big) - 5} more" if len(big) > 5 else ""
    return [_f(sev, "Brain methods",
               f"{len(big)} function(s) are both long and complex: {listed}{more}. Split them before the next change lands there.")]


def duplication(report: dict, min_lines: int = 30) -> list:
    dup = report.get("duplicates") or {}
    blocks = [b for b in dup.get("blocks") or [] if b["lines"] >= min_lines]
    if not blocks:
        return []
    blocks.sort(key=lambda b: -b["lines"])
    def place(b):
        return " and ".join(f"{p}:{start}" for p, start, _ in b["places"][:3])
    listed = "; ".join(f"{b['lines']} lines in {place(b)}" for b in blocks[:3])
    more = f" and {len(blocks) - 3} more" if len(blocks) > 3 else ""
    rate = f" Overall {dup['rate']}% of lines are duplicated." if dup.get("rate") is not None else ""
    return [_f("info", "Duplicated code", f"{len(blocks)} block(s) of {min_lines}+ duplicated lines: {listed}{more}.{rate} Extract the shared part.")]


RULES = [secrets_found, placeholder_identity, bus_factor, sizer_concerns, hotspot_dominance, bug_magnets, brain_methods, tight_coupling,
         duplication, stale_files, duplicate_identities, knowledge_islands]


def evaluate(report: dict) -> list:
    found = []
    for rule in RULES:
        found.extend(rule(report))
    found.sort(key=lambda f: SEVERITIES.index(f["severity"]))
    return found
